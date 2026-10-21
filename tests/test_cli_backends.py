"""Adapter contracts: no provider access or credentials needed."""
import asyncio
import json
import io
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import (AgySwarmBackend, ClaudeCodeSwarmBackend, CodexSwarmBackend,
                     OpenCodeSwarmBackend, SwarmResult, SwarmTask, create_swarm_backend,
                     disposable_cli_env)
from task_graph import Blackboard, TaskGraph, TaskNode, TaskStatus
from install import copy_skill_tree, get_project_targets
import mimir
from jarvis_memory import JarvisMemory
from research_scout import IntelligenceBrief, ResearchItem


class BackendContracts(unittest.IsolatedAsyncioTestCase):
    async def test_codex_failed_exit_is_never_success_and_stdin_isolated(self):
        backend = CodexSwarmBackend(codex_path="codex", default_model="worker")
        async def run(cmd, prompt=None, env=None):
            self.assertIn("--ephemeral", cmd)
            self.assertIn("read-only", cmd)
            self.assertEqual(cmd[-1], "-")
            self.assertIn("objective", prompt)
            Path(cmd[cmd.index("-o") + 1]).write_text("partial", encoding="utf-8")
            return 1, "partial", "failure"
        backend._run_cli = run
        result = await backend.spawn("objective")
        self.assertEqual(result.status, "ERROR")

    async def test_agy_each_call_has_unique_storage_removed_on_error(self):
        backend = AgySwarmBackend(agy_path="agy")
        roots = []
        async def run(cmd, prompt=None, env=None):
            self.assertIn("--sandbox", cmd)
            self.assertIn("--disable-slash-commands", cmd)
            roots.append(Path(env["HOME"]))
            (roots[-1] / "fake-session").write_text("session")
            return 1, "", "failed"
        backend._run_cli = run
        with tempfile.TemporaryDirectory() as home, patch.object(Path, "home", return_value=Path(home)):
            await backend.parallel([SwarmTask("one", "one"), SwarmTask("two", "two")])
        self.assertEqual(len(set(roots)), 2)
        self.assertTrue(all(not root.exists() for root in roots))

    async def test_claude_result_envelope_and_non_persistence(self):
        backend = ClaudeCodeSwarmBackend(claude_path="claude")
        async def run(cmd, prompt=None, env=None):
            self.assertIn("--no-session-persistence", cmd)
            self.assertNotIn("--effort", cmd)  # Haiku has no effort control
            self.assertIn("--strict-mcp-config", cmd)
            return 0, json.dumps({"subtype": "success", "result": '{"answer": 42}'}), ""
        backend._run_cli = run
        result = await backend.spawn("objective")
        self.assertEqual(result.data, {"answer": 42})
        async def error(*args, **kwargs):
            return 0, json.dumps({"is_error": True, "result": "partial"}), ""
        backend._run_cli = error
        self.assertEqual((await backend.spawn("objective")).status, "ERROR")

    async def test_opencode_events_storage_and_variant(self):
        backend = OpenCodeSwarmBackend("provider/worker", opencode_path="opencode")
        roots = []
        async def run(cmd, prompt=None, env=None):
            self.assertEqual(cmd[cmd.index("--variant") + 1], "low")
            self.assertNotIn("--attach", cmd)
            roots.append(Path(env["HOME"]))
            config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
            self.assertEqual(config["share"], "disabled")
            return 0, json.dumps({"type": "text", "part": {"text": '{"ok": true}'}}), ""
        backend._run_cli = run
        with tempfile.TemporaryDirectory() as home, patch.object(Path, "home", return_value=Path(home)):
            result = await backend.spawn("objective")
        self.assertEqual(result.data, {"ok": True})
        self.assertFalse(roots[0].exists())
        async def failed(cmd, **kwargs):
            self.assertNotIn("--variant", cmd)
            return 0, json.dumps({"type": "error", "error": {"message": "failed"}}), ""
        backend._run_cli = failed
        self.assertEqual((await backend.spawn("objective", effort="none")).status, "ERROR")

    async def test_timeout_kills_worker_before_return(self):
        backend = CodexSwarmBackend(codex_path="codex")
        backend.timeout_seconds = .01
        class Process:
            returncode = None
            killed = False
            async def communicate(self, data=None):
                if not self.killed:
                    await asyncio.sleep(10)
                return b"", b""
            def kill(self):
                self.killed = True
                self.returncode = -1
        process = Process()
        async def spawn(*args, **kwargs):
            return process
        with patch("asyncio.create_subprocess_exec", spawn):
            result = await backend.spawn("objective")
        self.assertTrue(process.killed)
        self.assertEqual(result.status, "ERROR")

    async def test_graph_keeps_dependency_results_and_failure_cascade(self):
        backend = CodexSwarmBackend(codex_path="codex", default_model="worker")
        graph = TaskGraph("objective")
        graph.add_node(TaskNode("a", "Analyst", "first", "first"))
        graph.add_node(TaskNode("b", "Critic", "second", "second", dependencies={"a"}))
        graph.add_node(TaskNode("c", "Synthesizer", "third", "third", dependencies={"b"}))
        async def worker(prompt, role, **kwargs):
            if role == "Critic":
                self.assertIn("first-result", prompt)
                return SwarmResult(role, "ERROR", None, "failed")
            return SwarmResult(role, "SUCCESS", "first-result", "first-result")
        backend.spawn = worker
        results = await backend.execute_graph(graph, Blackboard("test"))
        self.assertEqual(set(results), {"a"})
        self.assertEqual(graph.nodes["b"].status, TaskStatus.FAILED)
        self.assertEqual(graph.nodes["c"].status, TaskStatus.CANCELLED)

    def test_disposable_login_copy_excludes_sessions_and_normal_home_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            authdir = home / ".local/share/opencode"
            authdir.mkdir(parents=True)
            (authdir / "auth.json").write_text("{}")
            (authdir / "opencode.db").write_text("private-sessions")
            with patch.object(Path, "home", return_value=home), patch.dict(os.environ, {}, clear=True):
                with disposable_cli_env("opencode") as env:
                    disposable = Path(env["XDG_DATA_HOME"]) / "opencode"
                    self.assertTrue((disposable / "auth.json").exists())
                    self.assertFalse((disposable / "opencode.db").exists())
                self.assertEqual((authdir / "opencode.db").read_text(), "private-sessions")

    def test_factory_config_and_cli_only_discovery(self):
        with patch.dict(os.environ, {"MIMIR_BACKEND": "claude", "MIMIR_CLAUDE_MODEL": "haiku", "MIMIR_EFFORT": "low"}, clear=True), patch("shutil.which", return_value="claude"):
            self.assertIsInstance(create_swarm_backend("auto"), ClaudeCodeSwarmBackend)
            self.assertIsInstance(create_swarm_backend("anthropic"), __import__("backend").AnthropicSwarmBackend)
        with self.assertRaises(ValueError):
            OpenCodeSwarmBackend(opencode_path="opencode")

    def test_installed_skill_is_self_contained_for_each_project_target(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            for name, target in get_project_targets(Path(directory)):
                copy_skill_tree(repo, target)
                self.assertTrue((target / "scripts/mimir.py").exists(), name)
                self.assertTrue((target / "prompts/HARNESS_EXECUTION.md").exists(), name)

    async def test_five_phase_engine_through_cli_adapter_and_artifacts(self):
        """Exercise skill entrypoint behavior without spending model tokens."""
        backend = ClaudeCodeSwarmBackend(claude_path="claude", default_effort="low")
        calls = []
        progress = io.StringIO()
        async def run(cmd, prompt=None, env=None):
            if "--help" in cmd:
                return 0, " ".join(backend.required_flags), ""
            calls.append(prompt)
            if "Mimir-Decomposer" in prompt:
                result = {"tasks": [
                    {"id": "a", "role": "Domain-Analyst", "title": "Analyze", "objective": "Inspect", "dependencies": []},
                    {"id": "b", "role": "Formal-Modeler", "title": "Model", "objective": "Model", "dependencies": ["a"]},
                    {"id": "c", "role": "Red-Team-Critic", "title": "Critique", "objective": "Challenge", "dependencies": ["b"]},
                    {"id": "d", "role": "Executive-Synthesizer", "title": "Synthesize", "objective": "Combine", "dependencies": ["c"]},
                ]}
            elif "GEPA-Evolver" in prompt:
                result = {"hardened_solution": "Completed fixture synthesis", "reflection": "Fixture critique addressed"}
            else:
                self.assertIn("required constraint", prompt)
                # The host can see queued work before awaiting the CLI response.
                events = [json.loads(line) for line in progress.getvalue().splitlines()]
                self.assertIn("task_submitted", [event["event"] for event in events])
                result = {"finding": "Fixture result"}
            return 0, json.dumps({"subtype": "success", "result": json.dumps(result)}), ""
        backend._run_cli = run
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.md"
            memory = JarvisMemory(str(Path(directory) / "LEARNINGS.md"))
            with patch.object(mimir, "create_swarm_backend", return_value=backend), patch.object(mimir, "JarvisMemory", return_value=memory), redirect_stdout(progress):
                await mimir.run_mimir("Design with required constraint", str(report), backend="claude", skip_web=True, enable_jev=False, progress_format="jsonl")
            artifact = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(len(artifact["task_results"]), 4)
            self.assertEqual(artifact["hardened_solution"], "Completed fixture synthesis")
            self.assertEqual(artifact["worker_effort"], "low")
            self.assertEqual(memory.get_summary_stats()["entries"], 1)
        self.assertEqual(len(calls), 6)  # decomposer, four nodes, reflection
        events = [json.loads(line) for line in progress.getvalue().splitlines()]
        self.assertEqual([event["phase"] for event in events if event["event"] == "phase_started"], [1, 2, 3, 4, 5])
        self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))
        self.assertEqual(events[-1]["event"], "run_completed")
        self.assertEqual(len([event for event in events if event["event"] == "task_completed"]), 4)
        self.assertFalse(events[0]["web_enabled"])
        self.assertFalse(events[0]["jev_enabled"])
        self.assertNotIn("required constraint", progress.getvalue())  # no raw goal/prompt dump

    async def test_failed_worker_does_not_publish_or_learn(self):
        backend = ClaudeCodeSwarmBackend(claude_path="claude")
        graph = TaskGraph("objective")
        graph.add_node(TaskNode("failed", "Analyst", "Fail", "Fail"))
        async def check():
            return {"model_configured": True}
        async def fail(*args, **kwargs):
            return SwarmResult("Analyst", "ERROR", None, "authentication failed")
        async def decompose(*args, **kwargs):
            return graph
        backend.check_cli = check
        backend.spawn = fail
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.md"
            memory = JarvisMemory(str(Path(directory) / "LEARNINGS.md"))
            progress = io.StringIO()
            with patch.object(mimir, "create_swarm_backend", return_value=backend), patch.object(mimir, "JarvisMemory", return_value=memory), patch.object(mimir.RecursiveDecomposer, "decompose_goal", decompose), redirect_stdout(progress):
                with self.assertRaisesRegex(RuntimeError, "Swarm incomplete"):
                    await mimir.run_mimir("objective", str(report), backend="claude", skip_web=True, enable_jev=False, progress_format="jsonl")
            self.assertFalse(report.exists())
            self.assertEqual(memory.get_summary_stats()["entries"], 0)
            events = [json.loads(line) for line in progress.getvalue().splitlines()]
            self.assertEqual(events[-1]["event"], "run_failed")
            self.assertIn("task_failed", [event["event"] for event in events])
            self.assertNotIn("run_completed", [event["event"] for event in events])

    def test_progress_lines_are_flushed_immediately(self):
        class Capture(io.StringIO):
            flush_count = 0
            def flush(self):
                self.flush_count += 1
        stream = Capture()
        with redirect_stdout(stream):
            ui = mimir.MimirConsole(progress_format="jsonl")
            ui.print_phase(2, "Dissektion", "Decomposition")
        self.assertEqual(stream.flush_count, 1)
        self.assertEqual(json.loads(stream.getvalue())["event"], "phase_started")

        term_stream = Capture()
        with redirect_stdout(term_stream):
            ui_term = mimir.MimirConsole(progress_format="terminal")
            ui_term.print_phase(2, "Dissektion", "Decomposition")
        self.assertGreaterEqual(term_stream.flush_count, 1)
        self.assertIn("Phase 2", term_stream.getvalue())

    def test_research_and_terminal_modes_report_actual_state(self):
        brief = IntelligenceBrief(topic="fixture")
        brief.items.append(ResearchItem(channel="spec", title="Reference", url="https://example.org/spec", summary="Fixture"))
        stream = io.StringIO()
        with redirect_stdout(stream):
            ui = mimir.MimirConsole(progress_format="jsonl")
            ui.display_intel(brief)
        event = json.loads(stream.getvalue())
        self.assertEqual(event["source_count"], 1)
        self.assertEqual(event["sources"][0]["url"], "https://example.org/spec")
        stream = io.StringIO()
        with patch.object(mimir, "HAS_RICH", False), redirect_stdout(stream):
            ui = mimir.MimirConsole()
            ui.print_phase(1, "Spaning", "Scouting")
        self.assertIn("PHASE 1", stream.getvalue())
        self.assertNotIn('"schema_version"', stream.getvalue())

    def test_cli_progress_failure_is_machine_readable(self):
        env = os.environ.copy()
        for key in ("MIMIR_MODEL", "MIMIR_CODEX_MODEL"):
            env.pop(key, None)
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run([sys.executable, "-B", str(Path(mimir.__file__)), "objective",
                                      "--backend", "codex", "--progress", "jsonl"], cwd=directory,
                                     capture_output=True, text=True, encoding="utf-8", env=env, timeout=20)
        self.assertNotEqual(process.returncode, 0)
        event = json.loads(process.stdout)
        self.assertEqual(event["event"], "run_failed")
        self.assertIn("Mimir failed:", process.stderr)


if __name__ == "__main__":
    unittest.main()
