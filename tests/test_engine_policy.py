"""End-to-end engine policy, evidence and recovery with isolated fake runtimes."""
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import BaseSwarmBackend, SwarmResult, WorkerFailure
from mimir_config import ConfigurationRequired


SOURCE = "https://example.test/primary"


def finding(gaps=()):
    return {"answer": f"The primary reference describes the behavior: {SOURCE}.",
            "sources": [{"id": "primary", "locator": SOURCE, "retrieval_type": "primary_document",
                         "retrieved_at": "2026-10-22T12:00:00Z", "support_excerpt": "Explicit supported behavior."}],
            "claims": [{"text": "The behavior is described.", "source_ids": ["primary"],
                        "support_status": "supported", "rationale": "The primary source explicitly describes it."}],
            "gaps": list(gaps)}


class FixtureBackend(BaseSwarmBackend):
    def __init__(self, *, failures=(), cleanup_failure=False, **settings):
        super().__init__(settings.get("model") or "fixture", settings.get("max_concurrency") or 4)
        self.default_effort = settings.get("effort") or "low"
        self.calls = []
        self.failures = set(failures)
        self.cleanup_failure = cleanup_failure
        self.closed = False

    async def spawn(self, prompt, role="Micro-Worker", **kwargs):
        self.calls.append({"role": role, "prompt": prompt, **kwargs})
        if role in self.failures:
            await asyncio.sleep(.02)  # allow an independent result to checkpoint
            return SwarmResult(role, "ERROR", None, "HTTP 429 provider rate limit", tokens_used=7)
        value = {"reflection": "No unsupported promotion; source and gaps retained.",
                 "hardened_solution": f"Review supported by {SOURCE}."} if role == "GEPA-Evolver" else finding()
        return SwarmResult(role, "SUCCESS", value, json.dumps(value), duration_seconds=.001, tokens_used=11)

    async def aclose(self):
        self.closed = True
        if self.cleanup_failure:
            raise OSError("fixture cleanup failure")


class EnginePolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.checkpoint = self.root / "checkpoint.json"
        self.report = self.root / "report.md"
        self.memory = self.root / "guidance" / "LEARNINGS.md"
        self.events = []
        self.instances = []

    def tearDown(self):
        self.temporary.cleanup()

    def factory(self, **kwargs):
        backend = FixtureBackend(**kwargs)
        self.instances.append(backend)
        return backend

    async def run_engine(self, **kwargs):
        options = {"backend": "codex", "model": "fixture", "effort": "low", "worker_transport": "native",
                   "skip_web": True, "state_file": str(self.checkpoint), "output_path": str(self.report),
                   "memory_path": str(self.memory), "progress_format": "events", "event_sink": self.events.append,
                   "worker_factory": self.factory}
        options.update(kwargs)
        with patch.dict(os.environ, {}, clear=True):
            return await engine.run_mimir(**options)

    async def test_single_is_one_call_and_default_read_does_not_write_memory(self):
        state = await self.run_engine(goal="Resolve the focused question", mode="single")
        self.assertEqual(state["phase"], "synthesized")
        self.assertEqual([c["role"] for c in self.instances[0].calls], ["Domain-Analyst"])
        self.assertFalse(self.memory.exists())
        self.assertFalse(self.memory.parent.exists())
        self.assertTrue(self.instances[0].closed)
        payload = json.loads(self.report.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(payload["memory_mode"], "read")
        self.assertEqual(payload["research"]["coverage"], "reported")
        self.assertFalse(payload["research"]["independently_verified"])
        self.assertEqual(payload["research"]["claims"][0]["source_ids"], ["research:primary"])
        self.assertEqual(payload["usage"]["model_calls"], 1)
        self.assertEqual(payload["usage"]["known_tokens"], 11)
        self.assertEqual(self.events[-1]["event"], "run_completed")

    async def test_partial_execution_reuses_completed_tasks_without_repeat_calls(self):
        def failing_factory(**kwargs):
            backend = FixtureBackend(failures={"Code-Architect"}, **kwargs)
            self.instances.append(backend)
            return backend
        await self.run_engine(goal="Review the implementation", phase="plan")
        self.assertFalse(self.instances[-1].calls)
        with self.assertRaises(WorkerFailure):
            await self.run_engine(phase="execute", worker_factory=failing_factory)
        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "executing")
        self.assertEqual(set(state["completed_data"]), {"evidence"})
        retained = state["completed_data"]["evidence"]
        await self.run_engine(phase="execute")
        self.assertEqual([c["role"] for c in self.instances[-1].calls], ["Code-Architect", "Red-Team-Critic"])
        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(state["completed_data"]["evidence"], retained)
        self.assertEqual(state["phase"], "executed")

    async def test_synthesis_rejects_mutated_result_before_runtime_or_model_call(self):
        await self.run_engine(goal="Resolve question", mode="single", phase="plan")
        await self.run_engine(phase="execute")
        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        state["completed_data"]["research"]["result"]["answer"] = "Tampered false certainty"
        self.checkpoint.write_text(json.dumps(state), encoding="utf-8")
        previous_instances = len(self.instances)
        with self.assertRaisesRegex(ConfigurationRequired, "identity changed"):
            await self.run_engine(phase="synthesize")
        self.assertEqual(len(self.instances), previous_instances)
        self.assertFalse(self.report.exists())

    async def test_late_cleanup_failure_has_no_success_and_recovery_does_not_republish(self):
        def cleanup_factory(**kwargs):
            backend = FixtureBackend(cleanup_failure=True, **kwargs)
            self.instances.append(backend)
            return backend
        with self.assertRaisesRegex(OSError, "cleanup"):
            await self.run_engine(goal="Resolve question", mode="single", worker_factory=cleanup_factory)
        self.assertNotIn("run_completed", [e["event"] for e in self.events])
        hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.report, self.report.with_suffix(".json"))]
        self.events.clear()
        await self.run_engine(phase="synthesize")
        self.assertFalse(self.instances[-1].calls)
        self.assertEqual(hashes, [hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.report, self.report.with_suffix(".json"))])
        self.assertEqual(self.events[-1]["event"], "run_completed")
        self.assertFalse(self.memory.exists())

    async def test_context_admission_fails_without_truncating_or_calling_runtime(self):
        goal = "Required evidence suffix " + "x" * 2000 + " RETAIN THIS SUFFIX"
        await self.run_engine(goal=goal, mode="single", phase="plan", max_context_chars=1000)
        with self.assertRaisesRegex((ConfigurationRequired, WorkerFailure), "context|Context"):
            await self.run_engine(phase="execute", max_context_chars=1000)
        self.assertFalse(self.instances[-1].calls)
        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertIn("RETAIN THIS SUFFIX", state["graph"]["nodes"]["research"]["prompt"])
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
