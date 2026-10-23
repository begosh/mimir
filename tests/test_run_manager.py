"""Public run lifecycle with in-process workers and real durable storage."""
import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_manager import RunManager, RunBusyError
from run_locks import ownership
import engine
from backend import BaseSwarmBackend, SwarmResult, WorkerFailure
from jarvis_memory import JarvisMemory
from mimir_config import ConfigurationRequired


async def completed_runner(**options):
    phase = options["phase"]
    target = Path(options["state_file"])
    target.write_text(json.dumps({"phase": {"plan": "planned", "execute": "executed", "synthesize": "synthesized"}[phase]}))
    if phase == "synthesize":
        Path(options["output_path"]).write_text("Report with sources", encoding="utf-8")
        Path(options["output_path"]).with_suffix(".json").write_text('{"sources": []}', encoding="utf-8")
    options["event_sink"]({"sequence": 1, "event": "phase_started"})
    options["event_sink"]({"sequence": 2, "event": {"plan": "plan_completed", "execute": "execute_completed", "synthesize": "run_completed"}[phase]})


class ManagedRuns(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = RunManager(self.root, runner=completed_runner)

    async def asyncTearDown(self):
        await self.manager.aclose()
        self.temp.cleanup()

    async def settle(self, run_id):
        for _ in range(30):
            if self.manager.status(run_id)["status"] not in {"queued", "running", "cancelling"}:
                return
            await asyncio.sleep(0.01)
        self.fail("Run did not settle")

    async def test_phases_cursors_results_and_restart(self):
        started = await self.manager.start(goal="Analyze sources", backend="codex", model="agreed")
        identity = started["run_id"]
        await self.settle(identity)
        page = self.manager.status(identity, limit=1)
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_sequence"], 1)
        with self.assertRaises(ValueError):
            self.manager.result(identity)
        for phase in ("execute", "synthesize"):
            await self.manager.start(run_id=identity, phase=phase)
            await self.settle(identity)
        status = self.manager.status(identity)
        self.assertEqual(status["status"], "completed")
        self.assertEqual([e["sequence"] for e in status["events"]], list(range(1, 7)))
        self.assertEqual([e["invocation"] for e in status["events"]], [1, 1, 2, 2, 3, 3])
        first = self.manager.result(identity, limit=6)
        second = self.manager.result(identity, offset=first["next_offset"])
        self.assertEqual(first["content"] + second["content"], "Report with sources")
        restarted = RunManager(self.root)
        try:
            self.assertEqual(restarted.result(identity)["content"], "Report with sources")
        finally:
            await restarted.aclose()

    async def test_cancel_waits_for_worker_cleanup_including_immediate_cancel(self):
        entered = asyncio.Event()
        cleaned = asyncio.Event()
        async def blocked(**options):
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.01)
                cleaned.set()
        self.manager.runner = blocked
        run = await self.manager.start(goal="private", skip_web=True)
        result = await self.manager.cancel(run["run_id"])
        self.assertTrue(cleaned.is_set())
        self.assertEqual(result["status"], "cancelled")
        with self.assertRaises(ValueError):
            self.manager.result(run["run_id"])

    async def test_active_owner_prevents_other_hosts_recovery_and_cancel(self):
        async def blocked(**options):
            await asyncio.Event().wait()
        self.manager.runner = blocked
        run = await self.manager.start(goal="private")
        await asyncio.sleep(0)
        other = RunManager(self.root)
        try:
            self.assertEqual(other.status(run["run_id"])["status"], "running")
            with self.assertRaises(RunBusyError):
                await other.cancel(run["run_id"])
            with self.assertRaises(RunBusyError):
                await other.start(run_id=run["run_id"], phase="execute")
        finally:
            await other.aclose()

    async def test_crash_recovery_and_missing_completion_do_not_publish_success(self):
        run = await self.manager.start(goal="private")
        identity = run["run_id"]
        await self.settle(identity)
        path = self.root / identity / "run.json"
        value = json.loads(path.read_text())
        value["status"] = "running"
        path.write_text(json.dumps(value))
        self.assertEqual(self.manager.status(identity)["status"], "interrupted")
        async def no_completion(**options):
            return {}
        self.manager.runner = no_completion
        await self.manager.start(run_id=identity, phase="execute")
        await self.settle(identity)
        self.assertEqual(self.manager.status(identity)["status"], "failed")
        with self.assertRaises(ValueError):
            self.manager.result(identity)

    async def test_paths_validation_and_sanitized_failure(self):
        for bad in ("../secrets", "a" * 31, "Z" * 32):
            with self.assertRaises(ValueError):
                self.manager.status(bad)
        async def fails(**options):
            raise RuntimeError("SECRET-KEY must never appear")
        self.manager.runner = fails
        run = await self.manager.start(goal="private")
        await self.settle(run["run_id"])
        self.assertNotIn("SECRET-KEY", json.dumps(self.manager.status(run["run_id"])))
        with self.assertRaises(ValueError):
            await self.manager.start(goal="private", max_concurrency=True)
        with self.assertRaises(ValueError):
            await self.manager.start(goal="private", worker_timeout=float("nan"))

    async def test_actionable_typed_worker_error_retains_environment_name_only(self):
        async def fails(**options):
            raise WorkerFailure("Codex SDK", 'PRIVATE prompt sk-secret\nMissing environment variable "AZURE_OPENAI_API_KEY"')
        self.manager.runner = fails
        run = await self.manager.start(goal="private")
        await self.settle(run["run_id"])
        status = self.manager.status(run["run_id"])
        self.assertIn("AZURE_OPENAI_API_KEY", status["error"])
        self.assertIn("worker process", status["error"])
        self.assertNotIn("PRIVATE", json.dumps(status))
        self.assertNotIn("sk-secret", json.dumps(status))

    async def test_configuration_requirement_keeps_owned_context_action(self):
        message = "Worker context exceeds --max-context-chars; evidence was retained without truncation. Raise the explicit limit or narrow the objective."
        async def fails(**options):
            options["event_sink"]({"sequence": 1, "event": "configuration_required", "message": message})
            raise ConfigurationRequired(message)
        self.manager.runner = fails
        run = await self.manager.start(goal="private")
        await self.settle(run["run_id"])
        self.assertEqual(self.manager.status(run["run_id"])["error"], message)

    async def test_old_configuration_event_cannot_supply_retry_error(self):
        message = "Configure --max-context-chars and run --doctor before retrying."
        async def first_failure(**options):
            Path(options["state_file"]).write_text(json.dumps({"phase": "planned"}))
            options["event_sink"]({"sequence": 1, "event": "configuration_required", "message": message})
            raise ConfigurationRequired(message)
        self.manager.runner = first_failure
        run = await self.manager.start(goal="private")
        identity = run["run_id"]
        await self.settle(identity)
        self.assertEqual(self.manager.status(identity)["error"], message)
        async def second_failure(**options):
            raise ConfigurationRequired("PRIVATE provider body from a malformed caller")
        self.manager.runner = second_failure
        await self.manager.start(run_id=identity, phase="execute")
        await self.settle(identity)
        error = self.manager.status(identity)["error"]
        self.assertNotEqual(error, message)
        self.assertNotIn("PRIVATE", error)

    async def test_status_observation_does_not_repair_metadata_or_journal(self):
        run = await self.manager.start(goal="private")
        identity = run["run_id"]
        await self.settle(identity)
        directory = self.root / identity
        record = json.loads((directory / "run.json").read_text())
        record.update(sequence=1, status="running")
        (directory / "run.json").write_text(json.dumps(record))
        with (directory / "events.jsonl").open("a") as stream:
            stream.write('{"sequence":3,"event":')
        before = {name: (directory / name).read_bytes() for name in ("run.json", "events.jsonl")}
        self.assertEqual(self.manager.status(identity)["status"], "interrupted")
        self.assertEqual({name: (directory / name).read_bytes() for name in before}, before)
        (directory / "owner.lock").unlink()
        self.assertEqual(self.manager.status(identity)["status"], "interrupted")
        self.assertFalse((directory / "owner.lock").exists())
        await self.manager.start(run_id=identity, phase="execute")
        await self.settle(identity)
        self.assertEqual([event["sequence"] for event in self.manager.status(identity)["events"]], [1, 2, 3, 4])

    async def test_late_cleanup_failure_requires_retry_before_result_is_available(self):
        run = await self.manager.start(goal="private")
        identity = run["run_id"]
        await self.settle(identity)
        await self.manager.start(run_id=identity, phase="execute")
        await self.settle(identity)
        calls = []

        async def publication_then_failure(**options):
            calls.append(options["phase"])
            await completed_runner(**options)
            options["event_sink"]({"sequence": 3, "event": "run_failed",
                "message": "Worker cleanup failed; verify the local runtime before retrying."})
            raise OSError("PRIVATE process path")

        self.manager.runner = publication_then_failure
        await self.manager.start(run_id=identity, phase="synthesize")
        await self.settle(identity)
        status = self.manager.status(identity)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["recoverable_phases"], ["synthesize"])
        self.assertIn("cleanup failed", status["error"])
        with self.assertRaises(ValueError):
            self.manager.result(identity)

        async def cleanup_retry(**options):
            checkpoint = json.loads(Path(options["state_file"]).read_text())
            self.assertEqual(checkpoint["phase"], "synthesized")
            # Simulate the engine publication reuse path: no inference/write.
            options["event_sink"]({"sequence": 1, "event": "publication_reused"})
            options["event_sink"]({"sequence": 2, "event": "run_completed"})

        self.manager.runner = cleanup_retry
        await self.manager.start(run_id=identity, phase="synthesize")
        await self.settle(identity)
        self.assertEqual(calls, ["synthesize"])
        self.assertEqual(self.manager.result(identity)["content"], "Report with sources")
        with self.assertRaises(ValueError):
            await self.manager.start(run_id=identity, phase="synthesize")

    async def test_execution_recovery_admits_incremental_checkpoint_and_preserves_controls(self):
        received = []
        async def incomplete(**options):
            received.append(options)
            Path(options["state_file"]).write_text(json.dumps({"phase": "executing"}))
            raise WorkerFailure("Codex SDK", "HTTP 429 provider rate limit")
        run = await self.manager.start(goal="private")
        identity = run["run_id"]
        await self.settle(identity)
        self.manager.runner = incomplete
        await self.manager.start(run_id=identity, phase="execute", mode="single", max_tasks=1,
            memory_mode="off", memory_path=str(self.root / "learning.md"), max_context_chars=10000)
        await self.settle(identity)
        self.assertEqual(self.manager.status(identity)["recoverable_phases"], ["execute"])
        self.assertEqual(received[-1]["memory_mode"], "off")
        self.assertEqual(received[-1]["mode"], "single")
        self.manager.runner = completed_runner
        await self.manager.start(run_id=identity, phase="execute")
        await self.settle(identity)
        self.assertEqual(self.manager.status(identity)["status"], "completed")

    async def test_cleanup_retry_cannot_reuse_previous_invocation_completion_event(self):
        run = await self.manager.start(goal="private")
        identity = run["run_id"]
        await self.settle(identity)
        await self.manager.start(run_id=identity, phase="execute")
        await self.settle(identity)

        async def late_failure(**options):
            await completed_runner(**options)
            raise OSError("Cleanup failed before another event could be emitted")

        self.manager.runner = late_failure
        await self.manager.start(run_id=identity, phase="synthesize")
        await self.settle(identity)
        self.assertEqual(self.manager.status(identity)["status"], "failed")

        async def returns_without_events(**options):
            return {}

        self.manager.runner = returns_without_events
        await self.manager.start(run_id=identity, phase="synthesize")
        await self.settle(identity)
        self.assertEqual(self.manager.status(identity)["status"], "failed")
        with self.assertRaises(ValueError):
            self.manager.result(identity)

    async def test_crashed_journal_ahead_of_metadata_and_partial_tail_resume(self):
        run = await self.manager.start(goal="private")
        identity = run["run_id"]
        await self.settle(identity)
        directory = self.root / identity
        record = json.loads((directory / "run.json").read_text())
        record.update(sequence=1, status="running")
        (directory / "run.json").write_text(json.dumps(record))
        with (directory / "events.jsonl").open("a") as stream:
            stream.write('{"sequence":3,"event":')
        self.assertEqual(self.manager.status(identity)["status"], "interrupted")
        await self.manager.start(run_id=identity, phase="execute")
        await self.settle(identity)
        events = self.manager.status(identity)["events"]
        self.assertEqual([e["sequence"] for e in events], [1, 2, 3, 4])
        self.assertEqual([e["sequence"] for e in self.manager.status(identity, after_sequence=2)["events"]], [3, 4])

    async def test_repeated_cancel_preserves_cancelling_until_cleanup_settles(self):
        cleaning = asyncio.Event()
        release = asyncio.Event()
        async def blocked(**options):
            try:
                await asyncio.Event().wait()
            finally:
                options["event_sink"]({"sequence": 1, "event": "run_cancelled"})
                cleaning.set()
                await release.wait()
        self.manager.runner = blocked
        run = await self.manager.start(goal="private")
        await asyncio.sleep(0)
        one = asyncio.create_task(self.manager.cancel(run["run_id"]))
        await cleaning.wait()
        two = asyncio.create_task(self.manager.cancel(run["run_id"]))
        await asyncio.sleep(0)
        self.assertEqual(self.manager.status(run["run_id"])["status"], "cancelling")
        self.assertFalse(one.done())
        self.assertFalse(two.done())
        release.set()
        results = await asyncio.gather(one, two)
        self.assertEqual([r["status"] for r in results], ["cancelled", "cancelled"])

    async def test_os_lease_releases_on_actual_process_death(self):
        target = self.root / "process.lock"
        code = "from pathlib import Path; import sys; from run_locks import ownership; lease=ownership(Path(sys.argv[1])); lease.__enter__(); print('READY',flush=True); sys.stdin.readline()"
        process = await asyncio.create_subprocess_exec(sys.executable, "-u", "-c", code, str(target),
                    cwd=str(Path(engine.__file__).parent), stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            self.assertEqual(await process.stdout.readline(), b"READY\n" if os.name != "nt" else b"READY\r\n")
            with self.assertRaises(RunBusyError):
                with ownership(target):
                    pass
            process.kill()
            await process.wait()
            with ownership(target):
                pass
        finally:
            if process.returncode is None:
                process.kill()
            await process.communicate()

    async def test_shutdown_cancels_all_work_and_blocks_new_runs(self):
        closed = []
        async def blocked(**options):
            try:
                await asyncio.Event().wait()
            finally:
                closed.append(options["state_file"])
        self.manager.runner = blocked
        await self.manager.start(goal="one")
        await self.manager.start(goal="two")
        await self.manager.aclose()
        self.assertEqual(len(closed), 2)
        with self.assertRaises(RuntimeError):
            await self.manager.start(goal="three")

    async def test_real_engine_runs_through_same_interface_without_stdout(self):
        class Worker(BaseSwarmBackend):
            def __init__(self):
                super().__init__("agreed")
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                if role == "Mimir-Decomposer":
                    data = {"tasks": [{"id": "a", "role": "Analyst", "title": "Inspect", "prompt": "Examine source", "dependencies": [], "jev_score": 1.0}]}
                elif role == "Mimir-Final-Checker":
                    data = {"verdict":"PASS","issues":[]}
                elif role == "Mimir-Synthesizer":
                    data = {"answer": "Report with explicit gaps", "limitations": []}
                else:
                    data = {"answer": "Source result with limitations", "sources": [], "claims": [], "gaps": []}
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
        def factory(**kwargs):
            return Worker()
        async def runner(**kwargs):
            return await engine.run_mimir(**kwargs, worker_factory=factory)
        self.manager.runner = runner
        stream = io.StringIO()
        with patch.object(engine, "JarvisMemory", return_value=JarvisMemory(str(self.root / "lessons.md"))), patch("sys.stdout", stream):
            run = await self.manager.start(goal="Local objective", backend="codex", model="agreed", skip_web=True, enable_jev=False)
            identity = run["run_id"]
            await self.settle(identity)
            self.assertEqual(self.manager.status(identity)["status"], "completed", self.manager.status(identity))
            for phase in ("execute", "synthesize"):
                await self.manager.start(run_id=identity, phase=phase)
                await self.settle(identity)
                self.assertEqual(self.manager.status(identity)["status"], "completed", self.manager.status(identity))
        self.assertEqual(stream.getvalue(), "")
        self.assertIn("Report with explicit gaps", self.manager.result(identity)["content"])
        checkpoint = json.loads((self.root / identity / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["worker_transport"], "hybrid")
