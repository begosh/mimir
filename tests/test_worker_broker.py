"""Targeted unit tests for WorkerBroker deep module."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from backend import BaseSwarmBackend, SwarmResult
from mimir_config import ConfigurationRequired
from task_graph import TaskNode
from worker_broker import BudgetExhausted, WorkerBroker, validate_budget


class FakeNativeBackend(BaseSwarmBackend):
    def __init__(self, max_concurrency: int = 4, default_model: str = "mock-model"):
        super().__init__(default_model=default_model, max_concurrency=max_concurrency)
        self.spawn_calls: list[dict] = []
        self.restricted_calls: list[dict] = []
        self.should_fail = False

    async def spawn(self, prompt: str, role: str = "Micro-Worker", **options) -> SwarmResult:
        self.spawn_calls.append({"prompt": prompt, "role": role, "options": options})
        if self.should_fail:
            raise RuntimeError("Fake child process failed: invalid api key")
        return SwarmResult(role, "SUCCESS", {"answer": "fake answer"}, "raw response", tokens_used=42)

    async def spawn_restricted(self, prompt: str, role: str = "Micro-Worker", **options) -> SwarmResult:
        self.restricted_calls.append({"prompt": prompt, "role": role, "options": options})
        if self.should_fail:
            raise RuntimeError("Fake restricted child process failed")
        return SwarmResult(role, "SUCCESS", {"answer": "restricted text answer"}, "raw restricted response", tokens_used=15)


class WorkerBrokerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.journal_file = self.root / ".operations.jsonl"
        self.native = FakeNativeBackend()

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_budget_defaults_and_bounds(self):
        defaults = validate_budget()
        self.assertEqual(defaults["max_attempts"], 64)
        self.assertEqual(defaults["max_seconds"], 1800)
        self.assertEqual(defaults["max_depth"], 1)

        # Rejects unknown fields
        with self.assertRaisesRegex(ValueError, "Unknown research budget fields"):
            validate_budget({"unrecognized_key": 123})

        # Rejects excessive depth
        with self.assertRaisesRegex(ValueError, "Recursive depth is at most 4"):
            validate_budget({"max_depth": 5})

    async def test_context_admission_defense_rejects_oversized_prompts(self):
        broker = WorkerBroker(self.native, max_context_chars=100)
        oversized_prompt = "A" * 105

        with self.assertRaisesRegex(ConfigurationRequired, "Worker context exceeds --max-context-chars"):
            await broker.invoke(oversized_prompt)

        # Verify zero calls reached the native adapter and zero attempts charged
        self.assertEqual(len(self.native.spawn_calls), 0)
        self.assertEqual(broker.attempts, 0)

    async def test_budget_exhaustion_on_attempts(self):
        broker = WorkerBroker(self.native, budget={"max_attempts": 2})
        res1 = await broker.invoke("Prompt 1")
        self.assertEqual(res1.status, "SUCCESS")
        self.assertEqual(broker.attempts, 1)

        res2 = await broker.invoke("Prompt 2")
        self.assertEqual(res2.status, "SUCCESS")
        self.assertEqual(broker.attempts, 2)

        # Third attempt exceeds budget
        with self.assertRaises(BudgetExhausted):
            await broker.invoke("Prompt 3")

    async def test_publication_reserve_protects_synthesizer_and_checker(self):
        broker = WorkerBroker(self.native, budget={"max_attempts": 3}, publication_reserve=2)

        # 1. Normal worker attempt 1 succeeds
        res1 = await broker.invoke("Normal worker prompt", role="Worker")
        self.assertEqual(res1.status, "SUCCESS")

        # 2. Normal worker attempt 2 is blocked by publication reserve (3 total - 2 reserved = 1 available for normal)
        with self.assertRaises(BudgetExhausted):
            await broker.invoke("Another normal worker prompt", role="Worker")

        # 3. Reserved publication roles are permitted through the reserve
        synth_res = await broker.invoke("Synthesis prompt", role="Mimir-Synthesizer")
        self.assertEqual(synth_res.status, "SUCCESS")

        checker_res = await broker.invoke("Final check prompt", role="Mimir-Final-Checker")
        self.assertEqual(checker_res.status, "SUCCESS")

        # 4. Now all 3 attempts are spent; further publication calls are also exhausted
        with self.assertRaises(BudgetExhausted):
            await broker.invoke("Overflow synthesis", role="Mimir-Synthesizer")

    async def test_deterministic_calculation_bypass_in_dispatch_task(self):
        broker = WorkerBroker(self.native)
        node = TaskNode(
            "calc_node",
            "Calculator",
            "Calculate ratio",
            "Calculate formula: (flour / water) * 100",
            input_artifacts={"task_contract": {"operation": "calculate", "formula": "(flour / water) * 100"}},
        )

        response = await broker.dispatch_task(
            node,
            prompt=node.prompt,
            dependency_data={"dep1": {"result": {"answer": "Flour: 600 g, Water: 300 g"}}},
        )
        self.assertEqual(response.status, "SUCCESS")
        # Native model was bypassed completely
        self.assertEqual(len(self.native.spawn_calls), 0)
        self.assertEqual(len(self.native.restricted_calls), 0)

    async def test_tool_policy_selection_routes_critique_to_restricted(self):
        broker = WorkerBroker(self.native)
        critic_node = TaskNode(
            "critique",
            "Red-Team-Critic",
            "Evaluate claims",
            "Critique finding",
        )

        response = await broker.dispatch_task(critic_node, prompt=critic_node.prompt)
        self.assertEqual(response.status, "SUCCESS")
        # Routed to spawn_restricted
        self.assertEqual(len(self.native.restricted_calls), 1)
        self.assertEqual(len(self.native.spawn_calls), 0)

    async def test_durable_journaling_and_crash_recovery_with_torn_lines(self):
        # Run 1: write 1 normal operation and simulate a torn trailing write from crash
        broker1 = WorkerBroker(self.native, budget={"max_attempts": 5}, journal=self.journal_file)
        await broker1.invoke("Prompt 1")
        self.assertEqual(broker1.attempts, 1)

        # Simulate torn partial JSON line appended during power loss
        with self.journal_file.open("a", encoding="utf-8") as f:
            f.write('{"operation_id": "attempt-2", "status": "inflight", "torn_json":')

        # Run 2: recover with recover=True
        broker2 = WorkerBroker(
            self.native,
            budget={"max_attempts": 5},
            journal=self.journal_file,
            recover=True,
        )
        # Broker repaired torn line and restored 1 successful operation
        self.assertEqual(broker2.attempts, 1)
        self.assertEqual(len(broker2.usage_calls), 1)
        self.assertEqual(broker2.usage_calls[0]["operation_id"], "attempt-1")

    async def test_diagnostic_sanitization_masks_process_failures(self):
        self.native.should_fail = True
        broker = WorkerBroker(self.native)
        node = TaskNode("worker_node", "Domain-Analyst", "Inspect", "Inspect prompt")

        response = await broker.dispatch_task(node, prompt=node.prompt)
        self.assertEqual(response.status, "ERROR")
        # Raw error ("Fake child process failed: API key invalid or expired") sanitized to template
        self.assertIn("authentication failed", response.raw_response.lower())
        self.assertNotIn("Fake child process failed", response.raw_response)


if __name__ == "__main__":
    unittest.main()
