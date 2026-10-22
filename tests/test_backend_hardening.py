"""Failure and data-flow regressions, with no provider calls or user config writes."""
import asyncio
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from fnmatch import fnmatchcase
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import (AgySwarmBackend, AnthropicSwarmBackend, ClaudeCodeSwarmBackend,
                     CodexSwarmBackend, OpenAISwarmBackend, OpenCodeSwarmBackend,
                     SwarmResult, SwarmTask, create_swarm_backend)
from backend import disposable_cli_env
from backend import WorkerCleanupError
from task_graph import Blackboard, TaskGraph, TaskNode, TaskStatus


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class BackendHardening(unittest.IsolatedAsyncioTestCase):
    async def test_missing_provider_environment_diagnostic_excludes_transcript(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        calls = []

        async def run(cmd, **kwargs):
            calls.append(cmd)
            # Real CLI failures print the prompt before the root cause.
            transcript = "user\n" + ("PRIVATE-PROMPT sk-secret-value\n" * 200)
            transcript += 'Error: Missing environment variable "AZURE_OPENAI_API_KEY"\n'
            return 1, "PRIVATE-STDOUT", transcript

        backend._run_cli = run
        result = await backend.spawn("PRIVATE-PROMPT")
        self.assertEqual(result.status, "ERROR")
        self.assertIn("Missing environment variable AZURE_OPENAI_API_KEY", result.raw_response)
        self.assertLess(len(result.raw_response), 240)
        self.assertNotIn("PRIVATE", result.raw_response)
        self.assertNotIn("sk-secret", result.raw_response)
        self.assertNotIn("model_provider", " ".join(calls[0]))
        self.assertFalse(Path(calls[0][calls[0].index("-o") + 1]).exists())

    async def test_codex_progress_without_final_answer_is_error(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")

        async def run(*args, **kwargs):
            return 0, "Starting task. tools ready. tokens used 234", ""

        backend._run_cli = run
        self.assertEqual((await backend.spawn("objective")).status, "ERROR")

    async def test_all_cli_error_envelopes_do_not_echo_private_output(self):
        workers = [
            (AgySwarmBackend(agy_path="agy"), '{"result": "PRIVATE"}'),
            (ClaudeCodeSwarmBackend(claude_path="claude"), '{"is_error": true, "result": "PRIVATE"}'),
            (OpenCodeSwarmBackend("provider/worker", opencode_path="opencode"),
             '{"type": "error", "error": {"message": "PRIVATE"}}'),
        ]
        async def run(*args, **kwargs):
            return 1, stdout, "PRIVATE key=secret"

        with tempfile.TemporaryDirectory() as home, patch.object(Path, "home", return_value=Path(home)):
            for worker, stdout in workers:
                worker._run_cli = run
                with self.subTest(worker=type(worker).__name__):
                    result = await worker.spawn("objective")
                    self.assertEqual(result.status, "ERROR")
                    self.assertNotIn("PRIVATE", result.raw_response)
                    self.assertNotIn("secret", result.raw_response)

    async def test_metadata_only_agy_and_blank_claude_responses_fail(self):
        workers = [(AgySwarmBackend(agy_path="agy"), '{"usage": {"total_tokens": 10}}'),
                   (ClaudeCodeSwarmBackend(claude_path="claude"), '{"subtype": "success", "result": "  "}')]
        with tempfile.TemporaryDirectory() as home, patch.object(Path, "home", return_value=Path(home)):
            for worker, stdout in workers:
                async def run(*args, **kwargs):
                    return 0, stdout, ""
                worker._run_cli = run
                self.assertEqual((await worker.spawn("objective")).status, "ERROR")

    async def test_malformed_cli_envelope_shapes_return_error(self):
        workers = [(ClaudeCodeSwarmBackend(claude_path="claude"), '{"result": "answer", "usage": null}'),
                   (OpenCodeSwarmBackend("provider/worker", opencode_path="opencode"), '["invalid event"]'),
                   (OpenCodeSwarmBackend("provider/worker", opencode_path="opencode"), '{"type":"text", "part":null}')]
        with tempfile.TemporaryDirectory() as home, patch.object(Path, "home", return_value=Path(home)):
            for worker, stdout in workers:
                async def run(*args, **kwargs):
                    return 0, stdout, ""
                worker._run_cli = run
                self.assertEqual((await worker.spawn("objective")).status, "ERROR")

    async def test_http_empty_and_error_responses_are_not_success(self):
        workers = [
            (OpenAISwarmBackend(api_key="fixture"), {"choices": [{"message": {"content": "  "}}]}),
            (OpenAISwarmBackend(api_key="fixture"), {"choices": [{"message": {"content": None}}]}),
            (OpenAISwarmBackend(api_key="fixture"), {"choices": [{"message": {"content": "null"}}]}),
            (OpenAISwarmBackend(api_key="fixture"), {"error": {"message": "PRIVATE"}}),
            (AnthropicSwarmBackend(api_key="fixture"), {"content": []}),
            (AnthropicSwarmBackend(api_key="fixture"), {"error": {"message": "PRIVATE"}}),
        ]
        for worker, response in workers:
            with self.subTest(worker=type(worker).__name__, response=response), \
                 patch("urllib.request.urlopen", return_value=Response(response)):
                result = await worker.spawn("objective")
                self.assertEqual(result.status, "ERROR")
                self.assertNotIn("PRIVATE", result.raw_response)

    async def test_http_success_preserves_result_and_configured_timeout(self):
        workers = [
            (OpenAISwarmBackend(api_key="fixture"), {"choices": [{"message": {"content": '{"answer":42}'}}]}),
            (AnthropicSwarmBackend(api_key="fixture"), {"content": [{"type": "text", "text": '{"answer":42}'}]}),
        ]
        for worker, response in workers:
            worker.timeout_seconds = 0.3
            with patch("urllib.request.urlopen", return_value=Response(response)) as request:
                result = await worker.spawn("objective")
                self.assertEqual(result.status, "SUCCESS")
                self.assertEqual(result.data, {"answer": 42})
                self.assertEqual(request.call_args.kwargs["timeout"], 0.3)

    async def test_nonempty_truncated_or_blocked_http_results_are_errors(self):
        cases = []
        for reason in (None, "length", "content_filter", "tool_calls", "unknown"):
            cases.append((OpenAISwarmBackend(api_key="fixture"),
                          {"choices": [{"finish_reason": reason, "message": {"content": "partial answer"}}]}))
        for reason in (None, "max_tokens", "pause_turn", "refusal", "tool_use", "unknown"):
            cases.append((AnthropicSwarmBackend(api_key="fixture"),
                          {"stop_reason": reason, "content": [{"type": "text", "text": "partial answer"}]}))
        for worker, response in cases:
            with self.subTest(response=response), patch("urllib.request.urlopen", return_value=Response(response)):
                result = await worker.spawn("objective")
                self.assertEqual(result.status, "ERROR")
                self.assertIsNone(result.data)
                self.assertNotIn("partial answer", result.raw_response)

    async def test_http_explicit_normal_completion_is_success(self):
        cases = [(OpenAISwarmBackend(api_key="fixture"),
                  {"choices": [{"finish_reason": "stop", "message": {"content": "complete answer"}}]}),
                 (AnthropicSwarmBackend(api_key="fixture"),
                  {"stop_reason": "end_turn", "content": [{"type": "text", "text": "complete answer"}]})]
        for worker, response in cases:
            with patch("urllib.request.urlopen", return_value=Response(response)):
                self.assertEqual((await worker.spawn("objective")).status, "SUCCESS")

    async def test_http_caller_deadline_bounds_slow_request(self):
        workers = [OpenAISwarmBackend(api_key="fixture"), AnthropicSwarmBackend(api_key="fixture")]
        for worker in workers:
            release = threading.Event()
            worker.timeout_seconds = 0.02

            def request(*args, **kwargs):
                release.wait(timeout=1)
                return Response({})

            try:
                with patch("urllib.request.urlopen", request):
                    start = asyncio.get_running_loop().time()
                    result = await worker.spawn("objective")
                    self.assertLess(asyncio.get_running_loop().time() - start, 0.2)
                    self.assertEqual(result.status, "ERROR")
                    self.assertIn("timed out", result.raw_response)
            finally:
                release.set()

    async def test_http_exception_urls_and_keys_are_not_exposed(self):
        error = urllib.error.HTTPError("https://example.org/?key=PRIVATE", 401, "PRIVATE", {}, None)
        with patch("urllib.request.urlopen", side_effect=error):
            result = await OpenAISwarmBackend(api_key="fixture").spawn("objective")
        error.close()
        self.assertIn("HTTP 401", result.raw_response)
        self.assertNotIn("PRIVATE", result.raw_response)
        self.assertNotIn("example.org", result.raw_response)

    def test_ollama_uses_local_model_and_endpoint_without_public_credentials(self):
        env = {"OPENAI_API_KEY": "PRIVATE", "OPENAI_BASE_URL": "https://api.openai.com/v1"}
        with patch.dict(os.environ, env, clear=True):
            backend = create_swarm_backend("ollama", model="qwen-local")
            self.assertEqual(backend.default_model, "qwen-local")
            self.assertEqual(backend.base_url, "http://localhost:11434/v1")
            self.assertNotEqual(backend.api_key, "PRIVATE")
            with self.assertRaisesRegex(ValueError, "installed local model"):
                create_swarm_backend("ollama")
            with patch.dict(os.environ, {"OLLAMA_HOST": "127.0.0.1:12345"}):
                self.assertEqual(create_swarm_backend("ollama", model="local").base_url,
                                 "http://127.0.0.1:12345/v1")

    def test_nonfinite_worker_timeouts_are_rejected(self):
        for timeout in (float("nan"), float("inf"), 0, -1):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                create_swarm_backend("openai", timeout_seconds=timeout)

    def test_opencode_specific_permission_grants_cannot_enable_mutations(self):
        inline = {"permission": {"*": "allow", "bash": "allow", "edit": "allow",
                                "custom_delete": "allow", "read": {"*": "allow", "private/*": "deny"}}}
        native = {"*": "allow", "bash": {"*": "allow"}, "edit": "allow", "custom_delete": "allow"}
        with tempfile.TemporaryDirectory() as home, patch.object(Path, "home", return_value=Path(home)), \
             patch.dict(os.environ, {"OPENCODE_CONFIG_CONTENT": json.dumps(inline)}, clear=True):
            with disposable_cli_env("opencode", native) as env:
                rules = dict(native)
                rules.update(json.loads(env["OPENCODE_CONFIG_CONTENT"])["permission"])
                for tool in ("bash", "edit", "custom_delete"):
                    matches = [value for pattern, value in rules.items() if fnmatchcase(tool, pattern)]
                    self.assertEqual(matches[-1], "deny", tool)
                self.assertEqual(rules["read"]["private/*"], "deny")
                self.assertEqual(json.loads(os.environ["OPENCODE_CONFIG_CONTENT"]), inline)

    async def test_parallel_exception_fails_one_worker_and_preserves_independent_result(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")

        async def spawn(prompt, role, **kwargs):
            if role == "broken":
                raise RuntimeError("PRIVATE arbitrary worker exception")
            await asyncio.sleep(0.01)
            return SwarmResult(role, "SUCCESS", "retained", "retained")

        backend.spawn = spawn
        results = await backend.parallel([SwarmTask("broken", "a"), SwarmTask("healthy", "b")])
        self.assertEqual([result.status for result in results], ["ERROR", "SUCCESS"])
        self.assertNotIn("PRIVATE", results[0].raw_response)

    async def test_parallel_cancellation_waits_for_worker_cleanup(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        started = asyncio.Event()
        cleanup_complete = asyncio.Event()

        async def spawn(*args, **kwargs):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                await asyncio.sleep(0.01)
                cleanup_complete.set()

        backend.spawn = spawn
        task = asyncio.create_task(backend.parallel([SwarmTask("a", "a")]))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleanup_complete.is_set())

    async def test_graph_preserves_all_dependency_results_without_fact_verification(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        graph = TaskGraph("objective")
        for index in range(6):
            graph.add_node(TaskNode(f"source-{index}", f"source-{index}", "Source", "Inspect"))
        graph.add_node(TaskNode("final", "final", "Synthesis", "Combine", dependencies=set(graph.nodes)))
        value = "important-detail" * 80
        contracts = []

        async def spawn(prompt, role, **kwargs):
            if role == "final":
                for index in range(6):
                    self.assertIn(f"source-{index}", prompt)
                self.assertIn(value, prompt)
            return SwarmResult(role, "SUCCESS", value, value)

        backend.spawn = spawn
        board = Blackboard("fixture")
        result = await backend.execute_graph(graph, board,
                     on_task_finish=lambda node, result, contract: contracts.append(contract))
        self.assertEqual(len(result), 7)
        self.assertTrue(all(contract.verification_passed is False for contract in contracts))
        self.assertEqual(graph.nodes["final"].output_data, value)

    async def test_graph_worker_exception_cascades_and_keeps_independent_result(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        graph = TaskGraph("objective")
        graph.add_node(TaskNode("broken", "broken", "broken", "broken"))
        graph.add_node(TaskNode("healthy", "healthy", "healthy", "healthy"))
        graph.add_node(TaskNode("dependent", "dependent", "dependent", "dependent", dependencies={"broken"}))

        async def spawn(prompt, role, **kwargs):
            if role == "broken":
                raise ValueError("private exception")
            return SwarmResult(role, "SUCCESS", "retained", "retained")

        backend.spawn = spawn
        results = await backend.execute_graph(graph, Blackboard("fixture"))
        self.assertEqual(set(results), {"healthy"})
        self.assertEqual(graph.nodes["broken"].status, TaskStatus.FAILED)
        self.assertEqual(graph.nodes["dependent"].status, TaskStatus.CANCELLED)

    async def test_graph_partial_completed_state_requires_explicit_rerun(self):
        graph = TaskGraph("objective")
        graph.add_node(TaskNode("done", "Analyst", "done", "done", status=TaskStatus.COMPLETED,
                                output_data="restored without raw provenance"))
        with self.assertRaisesRegex(ValueError, "partial execution resume"):
            await CodexSwarmBackend(default_model="worker", codex_path="codex").execute_graph(graph, Blackboard("fixture"))

    async def test_blackboard_rejected_provenance_fails_task(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        graph = TaskGraph("objective")
        graph.add_node(TaskNode("source", "Analyst", "source", "source"))
        graph.add_node(TaskNode("dependent", "Synthesis", "dependent", "dependent", dependencies={"source"}))

        async def spawn(*args, **kwargs):
            return SwarmResult("Analyst", "SUCCESS", "fixture", "fixture")

        backend.spawn = spawn
        board = Blackboard("fixture")
        board.commit_evidence = lambda **kwargs: False
        results = await backend.execute_graph(graph, board)
        self.assertFalse(results)
        self.assertEqual(graph.nodes["source"].status, TaskStatus.FAILED)
        self.assertEqual(graph.nodes["dependent"].status, TaskStatus.CANCELLED)

    async def test_graph_emits_each_completion_before_tier_barrier(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        graph = TaskGraph("objective")
        graph.add_node(TaskNode("slow", "duplicate-role", "Slow", "slow"))
        graph.add_node(TaskNode("fast", "duplicate-role", "Fast", "fast"))
        graph.add_node(TaskNode("dependent", "Synthesis", "Dependent", "dependent",
                                dependencies={"slow", "fast"}))
        release_slow = asyncio.Event()
        fast_finished = asyncio.Event()
        dependent_started = asyncio.Event()
        completions = []

        async def spawn(prompt, role, **kwargs):
            if prompt == "slow":
                await release_slow.wait()
                output = "slow result"
            elif prompt == "fast":
                output = "fast result"
            else:
                dependent_started.set()
                self.assertIn("slow result", prompt)
                self.assertIn("fast result", prompt)
                output = "combined result"
            return SwarmResult(role, "SUCCESS", output, output)

        def finish(node, result, contract):
            completions.append(node.id)
            if node.id == "fast":
                fast_finished.set()

        backend.spawn = spawn
        task = asyncio.create_task(backend.execute_graph(graph, Blackboard("fixture"),
                                                        on_task_finish=finish))
        try:
            await asyncio.wait_for(fast_finished.wait(), timeout=1)
            self.assertEqual(completions, ["fast"])
            self.assertEqual(graph.nodes["fast"].status, TaskStatus.COMPLETED)
            self.assertEqual(graph.nodes["slow"].status, TaskStatus.RUNNING)
            self.assertFalse(dependent_started.is_set())
        finally:
            release_slow.set()
        results = await asyncio.wait_for(task, timeout=1)
        self.assertEqual(completions, ["fast", "slow", "dependent"])
        self.assertEqual(results["fast"]["result"], "fast result")
        self.assertEqual(results["slow"]["result"], "slow result")

    async def test_graph_cancellation_waits_for_each_worker_cleanup(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        graph = TaskGraph("objective")
        graph.add_node(TaskNode("a", "Analyst", "a", "a"))
        graph.add_node(TaskNode("b", "Analyst", "b", "b"))
        both_started = asyncio.Event()
        started = []
        cleaned = []

        async def spawn(prompt, role, **kwargs):
            started.append(prompt)
            if len(started) == 2:
                both_started.set()
            try:
                await asyncio.sleep(10)
            finally:
                await asyncio.sleep(0.01)
                cleaned.append(prompt)

        backend.spawn = spawn
        task = asyncio.create_task(backend.execute_graph(graph, Blackboard("fixture")))
        await asyncio.wait_for(both_started.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(set(cleaned), {"a", "b"})

    async def test_cli_timeout_cleanup_does_not_wait_forever_on_retained_pipes(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        backend.timeout_seconds = 0.01
        backend.cleanup_timeout_seconds = 0.01

        class Process:
            returncode = None
            waited = False

            async def communicate(self, data=None):
                await asyncio.sleep(10)

            def kill(self):
                self.returncode = -1

            async def wait(self):
                self.waited = True
                return self.returncode

        process = Process()
        async def spawn(*args, **kwargs):
            return process

        with patch("asyncio.create_subprocess_exec", spawn):
            start = asyncio.get_running_loop().time()
            result = await backend.spawn("objective")
        self.assertLess(asyncio.get_running_loop().time() - start, 0.2)
        self.assertEqual(result.status, "ERROR")
        self.assertTrue(process.waited)

    @unittest.skipUnless(os.name == "nt", "Windows taskkill cleanup contract")
    async def test_windows_exited_parent_with_retained_pipes_reports_cleanup_gap(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        backend.timeout_seconds = backend.cleanup_timeout_seconds = 0.01
        commands = []

        class Parent:
            pid = 12345
            returncode = 0

            async def communicate(self, data=None):
                await asyncio.sleep(10)

            async def wait(self):
                return self.returncode

        class Killer:
            returncode = 1

            async def wait(self):
                return self.returncode

        async def spawn(*cmd, **kwargs):
            commands.append(cmd)
            return Killer() if cmd[0] == "taskkill" else Parent()

        with patch("asyncio.create_subprocess_exec", spawn):
            start = asyncio.get_running_loop().time()
            with self.assertRaises(WorkerCleanupError):
                await backend._run_cli(["fake-helper"])
        self.assertLess(asyncio.get_running_loop().time() - start, 0.2)
        self.assertEqual(commands[1], ("taskkill", "/PID", "12345", "/T", "/F"))

    @unittest.skipUnless(os.name != "nt", "POSIX process group cleanup contract")
    async def test_posix_exited_parent_still_kills_process_group(self):
        backend = CodexSwarmBackend(default_model="worker", codex_path="codex")
        backend.timeout_seconds = backend.cleanup_timeout_seconds = 0.01
        killed = asyncio.Event()

        class Parent:
            pid = 12345
            returncode = 0

            async def communicate(self, data=None):
                await killed.wait()
                return b"", b""

        async def spawn(*args, **kwargs):
            return Parent()

        with patch("asyncio.create_subprocess_exec", spawn), patch("os.killpg", side_effect=lambda *args: killed.set()) as kill:
            with self.assertRaises(asyncio.TimeoutError):
                await backend._run_cli(["fake-helper"])
        kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
