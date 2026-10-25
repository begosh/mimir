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

    async def spawn_restricted(self, prompt, role="Micro-Worker", **kwargs):
        return await self.spawn(prompt, role=role, **kwargs)

    async def spawn(self, prompt, role="Micro-Worker", **kwargs):
        self.calls.append({"role": role, "prompt": prompt, **kwargs})
        if role in self.failures:
            await asyncio.sleep(.02)  # allow an independent result to checkpoint
            return SwarmResult(role, "ERROR", None, "HTTP 429 provider rate limit", tokens_used=7)
        if role == "Mimir-Result-Checker":
            context = json.loads(prompt.split("INPUTS:\n")[1])
            value = {"checks": [{"id": c["id"], "verdict": "PASS", "issues": []}
                                for c in context["candidates"]]}
            return SwarmResult(role, "SUCCESS", value, json.dumps(value), tokens_used=11)
        if role == "Mimir-Assembly-Repairer":
            value = {"answer": f"Review supported by {SOURCE}.", "limitations": [], "quarantined_tasks": []}
            return SwarmResult(role, "SUCCESS", value, json.dumps(value), tokens_used=11)
        value = {"reflection": "No unsupported promotion; source and gaps retained.",
                 "hardened_solution": f"Review supported by {SOURCE}."} if role == "GEPA-Evolver" else ({"answer": f"Review supported by {SOURCE}.", "limitations": []} if role == "Mimir-Synthesizer" else ({"verdict":"PASS","issues":[]} if role == "Mimir-Final-Checker" else finding()))
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

    async def test_single_is_one_worker_and_one_check_and_read_does_not_write_memory(self):
        state = await self.run_engine(goal="Resolve the focused question", mode="single")
        self.assertEqual(state["phase"], "synthesized")
        self.assertEqual([c["role"] for c in self.instances[0].calls], ["Domain-Analyst", "Mimir-Result-Checker"])
        self.assertFalse(self.memory.exists())
        self.assertFalse(self.memory.parent.exists())
        self.assertTrue(self.instances[0].closed)
        payload = json.loads(self.report.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(payload["memory_mode"], "read")
        self.assertEqual(payload["research"]["coverage"], "reported")
        self.assertFalse(payload["research"]["independently_verified"])
        self.assertEqual(payload["research"]["claims"][0]["source_ids"], ["research:primary"])
        self.assertEqual(payload["usage"]["model_calls"], 2)
        self.assertEqual(payload["usage"]["known_tokens"], 22)
        self.assertEqual(payload["budget_status"]["limits"]["max_attempts"], 64)
        self.assertEqual(payload["budget_status"]["attempts_used"], 2)
        self.assertEqual(payload["budget_status"]["publication_calls_remaining"], 0)
        self.assertTrue(self.checkpoint.with_suffix(".operations.jsonl").is_file())
        self.assertEqual(self.events[-1]["event"], "run_completed")

    async def test_phased_review_keeps_one_budget_and_publication_reserve(self):
        budget = {"max_attempts": 7, "max_seconds": 60}
        await self.run_engine(goal="Review bounded evidence", mode="review", phase="plan",
                              research_budget=budget)
        journal = self.checkpoint.with_suffix(".operations.jsonl")
        header = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
        state = await self.run_engine(phase="execute")
        self.assertEqual(len(state["usage_calls"]), 5)
        with self.assertRaisesRegex(ConfigurationRequired, "fixed by the plan"):
            await self.run_engine(phase="synthesize", research_budget={**budget, "max_attempts": 8})
        state = await self.run_engine(phase="synthesize")
        self.assertEqual(len(state["usage_calls"]), 7)
        payload = json.loads(self.report.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(payload["budget_status"]["deadline"], header["time"] + 60)
        self.assertEqual(payload["budget_status"]["publication_calls_remaining"], 0)
        self.assertEqual([c["role"] for c in state["usage_calls"] if c["publication_reserved"]],
                         ["Mimir-Synthesizer", "Mimir-Final-Checker"])

    async def test_exhausted_ordinary_run_retains_calls_and_cannot_retry_paid_work(self):
        await self.run_engine(goal="Resolve focused question", mode="single", phase="plan",
                              research_budget={"max_attempts": 1})
        with self.assertRaises((WorkerFailure, ConfigurationRequired)):
            await self.run_engine(phase="execute")
        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(len(state["usage_calls"]), 1)
        self.assertFalse(self.report.exists())
        with self.assertRaises((WorkerFailure, ConfigurationRequired)):
            await self.run_engine(phase="execute")
        self.assertEqual(self.instances[-1].calls, [])

    async def test_default_planning_preserves_long_goal_and_brief_without_search(self):
        goal = "Give me the best napoli pizza recipe. " + "A long constraint remains part of the question. " * 100
        brief = {"outcome": "A practical Neapolitan pizza recipe", "constraints": [],
                 "components": ["Dough", "Fermentation", "Toppings", "Baking"],
                 "evidence_needs": ["Authoritative dough method if retrieval is needed"],
                 "missing_information": ["Oven type and maximum temperature"]}
        with patch.object(engine.ResearchScout, "conduct_deep_scout", side_effect=AssertionError("No preliminary search")) as scout:
            state = await self.run_engine(goal=goal, mode="single", phase="plan", skip_web=False, task_brief=brief)
        scout.assert_not_called()
        self.assertEqual(state["goal"], goal)
        self.assertEqual(state["task_brief"], brief)
        self.assertEqual(state["task_brief_origin"], "host")
        self.assertEqual(state["retrieval_policy"], "interpret_then_retrieve")
        self.assertEqual(state["intel_brief"]["items"], [])
        prompt = state["graph"]["nodes"]["research"]["prompt"]
        self.assertIn(goal, prompt)
        self.assertIn("Before retrieving evidence", prompt)
        self.assertIn("Oven type", prompt)
        self.assertEqual(self.instances[0].calls, [])
        with self.assertRaisesRegex(ConfigurationRequired, "brief is fixed"):
            await self.run_engine(phase="execute", task_brief={**brief, "outcome": "Changed"})

    async def test_explicit_query_becomes_hint_without_network_call(self):
        with patch.object(engine.ResearchScout, "conduct_deep_scout", side_effect=AssertionError("No search")):
            state = await self.run_engine(goal="Pizza recipe", mode="single", phase="plan", skip_web=False,
                                          search_query="Neapolitan dough method")
        self.assertEqual(state["retrieval_hints"]["candidate_public_query"], "Neapolitan dough method")
        self.assertIn("NOT RETRIEVED EVIDENCE", state["graph"]["nodes"]["research"]["prompt"])

    async def test_recursive_planning_persists_interpretation_and_blocks_missing_user_input(self):
        brief = {"outcome": "Dough recipe", "constraints": [], "components": ["Recipe"],
                 "evidence_needs": [], "missing_information": ["Oven temperature"]}
        leaf = {"id": "oven", "objective": "Clarify oven temperature", "atomic": True,
                "operation": "clarify", "inputs": ["Original question"], "expected_output": "one temperature",
                "acceptance_check": "user supplies temperature", "blocked_by": ["Oven temperature"],
                "dependencies": [], "max_input_items": 1, "max_output_words": 40}
        class PlannerFixture(FixtureBackend):
            async def spawn_restricted(self, prompt, role="Micro-Worker", **kwargs):
                self.calls.append({"role": role, "prompt": prompt, **kwargs})
                field = kwargs["json_schema"]["required"][0]
                value = (brief if role == "Mimir-Interpreter" else
                         {"tasks": [{"id": "root.oven", "decision": "ACCEPT", "reason": "One user choice"}],
                          "coverage_preserved": True, "coverage_gaps": []} if role == "Mimir-Simplicity-Reviewer" else {"tasks": [leaf]})
                if role == "Mimir-Decomposer":
                    value.setdefault("planning_error", None)
                data = value
                return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=11)
        def factory(**kwargs):
            instance = PlannerFixture(**kwargs)
            self.instances.append(instance)
            return instance
        state = await self.run_engine(goal="Pizza dough", mode="swarm", phase="plan", recursive_plan=True,
                                      worker_factory=factory)
        self.assertEqual(state["task_brief"], brief)
        self.assertEqual(state["planning_trace"]["status"], "planned")
        self.assertTrue(self.checkpoint.with_suffix(".planning.json").exists())
        self.assertEqual(len(self.instances[0].calls), 3)
        self.assertTrue(all(c["tool_policy"] == "text_only" for c in state["usage_calls"]))
        with self.assertRaisesRegex(ConfigurationRequired, "unresolved required inputs"):
            await self.run_engine(mode="swarm", phase="execute", worker_factory=factory)
        self.assertEqual(self.instances[-1].calls, [])

    async def test_review_synthesis_gets_critique_once_and_uses_restricted_runtime(self):
        class RestrictedFixture(FixtureBackend):
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                result = await super().spawn(prompt, role=role, **kwargs)
                if role == "Red-Team-Critic":
                    result.data["answer"] = "UNIQUE CRITIQUE EVIDENCE"
                    result.raw_response = json.dumps(result.data)
                return result
            async def spawn_restricted(self, prompt, role="Micro-Worker", **kwargs):
                self.restricted_role = role
                return await self.spawn(prompt, role=role, **kwargs)
        def factory(**kwargs):
            backend = RestrictedFixture(**kwargs)
            self.instances.append(backend)
            return backend
        await self.run_engine(goal="Review bounded evidence", worker_factory=factory)
        backend = self.instances[0]
        self.assertEqual(backend.restricted_role, "Mimir-Final-Checker")
        synthesis = next(c["prompt"] for c in backend.calls if c["role"] == "Mimir-Synthesizer")
        self.assertEqual(synthesis.count("UNIQUE CRITIQUE EVIDENCE"), 1)
        self.assertIn(SOURCE, synthesis)
        payload = json.loads(self.report.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(payload["final_answer_check"]["verdict"], "PASS")
        self.assertEqual(payload["usage"]["calls"][-1]["tool_policy"], "text_only")
        self.assertTrue(all(c["model"] == "fixture" and c["effort"] == "low" for c in payload["usage"]["calls"]))

    async def test_oversized_result_is_retained_but_never_admitted_or_retried(self):
        class Oversized(FixtureBackend):
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                reply = await super().spawn(prompt, role=role, **kwargs)
                if role == "Domain-Analyst":
                    reply.data["answer"] = "word " * 251
                    reply.raw_response = json.dumps(reply.data)
                return reply
        def factory(**kwargs):
            instance = Oversized(**kwargs)
            self.instances.append(instance)
            return instance
        with self.assertRaises(WorkerFailure):
            await self.run_engine(goal="Review bounded evidence", worker_factory=factory)
        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        rejected = state["graph"]["nodes"]["evidence"]["rejected_output"]
        self.assertEqual(len(rejected["result"]["answer"].split()), 251)
        self.assertEqual(rejected["tokens_used"], 11)
        self.assertNotIn("evidence", state["completed_data"])
        self.assertEqual([c["role"] for c in self.instances[0].calls], ["Domain-Analyst", "Code-Architect", "Mimir-Result-Checker"])
        self.assertFalse(self.report.exists())

    async def test_oversized_synthesis_is_retained_without_publishing(self):
        class Oversized(FixtureBackend):
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                reply = await super().spawn(prompt, role=role, **kwargs)
                if role == "Mimir-Synthesizer":
                    reply.data["answer"] = "word " * 301
                    reply.raw_response = json.dumps(reply.data)
                return reply
        def factory(**kwargs):
            instance = Oversized(**kwargs)
            self.instances.append(instance)
            return instance
        with self.assertRaisesRegex(ValueError, "compact word"):
            await self.run_engine(goal="Review bounded evidence", worker_factory=factory)
        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        call = state["usage_calls"][-1]
        self.assertEqual(call["status"], "ERROR")
        self.assertEqual(len(call["rejected_output"]["result"]["answer"].split()), 301)
        self.assertEqual(len(self.instances[0].calls), 6)
        self.assertFalse(self.report.exists())

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
        self.assertEqual([c["role"] for c in self.instances[-1].calls],
                         ["Code-Architect", "Mimir-Result-Checker", "Red-Team-Critic", "Mimir-Result-Checker"])
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
