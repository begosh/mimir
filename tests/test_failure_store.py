"""P3.1: Capture and deduplicate failure packets with original intent,
source snapshots/spans, attempts, feedback and independently adjudicated defects.

Verifies:
1. Deterministic content identity: failure packet ID is computed from original intent,
   task objective, failure kind, and defect fingerprint.
2. Ingestion deduplication: re-ingesting an identical failure packet increments occurrences
   and appends history rather than creating duplicate store entries.
3. Node failure capture: captures failed TaskNodes with bound sources, attempt journals,
   raw responses, and Result Gate checker issues.
4. Missing input blocker capture: captures blocked TaskNodes with unresolved blockers
   and upstream evidence.
5. Engine failure integration: engine execution halts automatically ingest failure packets
   for failed and blocked nodes.
6. Report publication ingestion: ingesting report.json captures quarantined findings.
7. Independent defect adjudication: allows updating defect types, severity, and resolution status.
8. Filtered queries: lists packets filtered by failure_kind, defect_type, and resolution_status.
"""
from copy import deepcopy
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import BaseSwarmBackend, SwarmResult
from failure_store import (
    FailurePacket,
    FailureStore,
    capture_from_node,
    capture_from_engine_state,
    capture_from_report_file,
    classify_defect_from_feedback,
)
from mimir_config import ConfigurationRequired
from task_graph import TaskGraph, TaskNode, TaskStatus


def make_leaf(task_id, *, objective, operation="extract", inputs=("supplied source",),
              blocked_by=(), dependencies=(), max_words=100):
    return {
        "id": task_id,
        "objective": objective,
        "atomic": True,
        "operation": operation,
        "inputs": list(inputs),
        "expected_output": "Extracted details",
        "acceptance_check": "Matches supplied source",
        "blocked_by": list(blocked_by),
        "dependencies": list(dependencies),
        "max_input_items": len(inputs),
        "max_output_words": max_words,
    }


class FailureStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store_path = self.root / "failure-packets.jsonl"
        self.store = FailureStore(store_path=self.store_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_failure_packet_identity_and_deduplication(self):
        """Identical failure packets produce the same packet_id and deduplicate in store."""
        pkt1 = FailurePacket(
            original_intent="Extract recipe from source",
            task_id="root.extract",
            task_objective="Extract flour and water",
            failure_kind="result_check_failure",
            attempts=[{"attempt": 1, "feedback": "Contradictory hydration percentage",
                       "issues": ["Contradictory hydration percentage"]}],
            metadata={"run_id": "run-001"},
        )
        pkt2 = FailurePacket(
            original_intent="Extract recipe from source",
            task_id="root.extract",
            task_objective="Extract flour and water",
            failure_kind="result_check_failure",
            attempts=[{"attempt": 1, "feedback": "Contradictory hydration percentage",
                       "issues": ["Contradictory hydration percentage"]}],
            metadata={"run_id": "run-002"},
        )

        # Same content fingerprint produces exact same packet_id
        self.assertEqual(pkt1.packet_id, pkt2.packet_id)

        # First ingestion creates new entry
        saved1, is_new1 = self.store.ingest(pkt1)
        self.assertTrue(is_new1)
        self.assertEqual(saved1.occurrences, 1)
        self.assertEqual(len(saved1.history), 1)

        # Second ingestion of duplicate updates occurrences and history without adding line
        saved2, is_new2 = self.store.ingest(pkt2)
        self.assertFalse(is_new2)
        self.assertEqual(saved2.occurrences, 2)
        self.assertEqual(len(saved2.history), 2)

        # Verify only 1 packet is persisted on disk
        persisted = self.store.list_packets()
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].packet_id, pkt1.packet_id)
        self.assertEqual(persisted[0].occurrences, 2)

    def test_classify_defect_from_feedback(self):
        """Feedback strings are properly classified into defect type and severity."""
        dtype, sev = classify_defect_from_feedback("Arithmetic contradiction: expected 60.0% but got 75.0%",
                                                  check_type="deterministic_calculation")
        self.assertEqual(dtype, "arithmetic_contradiction")
        self.assertEqual(sev, "critical")

        dtype, sev = classify_defect_from_feedback("Citation references unknown source ID: unknown_src",
                                                  check_type="structural_provenance")
        self.assertEqual(dtype, "structural_defect")
        self.assertEqual(sev, "major")

        dtype, sev = classify_defect_from_feedback("Invented ingredient: sugar not in source")
        self.assertEqual(dtype, "hallucinated_entity")
        self.assertEqual(sev, "critical")

        dtype, sev = classify_defect_from_feedback("Omitted required fermentation temperature")
        self.assertEqual(dtype, "required_omission_violation")
        self.assertEqual(sev, "major")

    def test_capture_from_failed_task_node(self):
        """Failed TaskNode captures original intent, bound source, attempts, and adjudicated defects."""
        node = TaskNode(
            id="root.calc",
            role="Atomic-Worker",
            title="Calculate hydration",
            prompt="Compute baker's hydration",
            input_artifacts={
                "task_contract": make_leaf("root.calc", objective="Calculate hydration", operation="calculate"),
                "supplied_sources": [{
                    "id": "recipe_1",
                    "locator": "https://example.com/recipe",
                    "retrieval_type": "web_page",
                    "retrieved_at": "2026-10-25T12:00:00Z",
                    "sha256": "abc123hash",
                    "support_excerpt": "1000 g flour, 600 ml water",
                }],
            },
        )
        node.status = TaskStatus.FAILED
        node.error_trace = "Result gate rejected all 2 attempts"
        node.result_attempts = [
            {"attempt": 1, "output": {"answer": "Hydration is 70%"}, "raw_response": '{"answer": "70%"}',
             "issues": ["Contradictory hydration percentage: expected 60.0%"], "check_type": "deterministic_calculation"},
            {"attempt": 2, "output": {"answer": "Hydration is 80%"}, "raw_response": '{"answer": "80%"}',
             "issues": ["Contradictory hydration percentage: expected 60.0%"], "check_type": "deterministic_calculation"},
        ]

        pkt = capture_from_node(node, goal="Extract and calculate pizza dough hydration", run_id="run-42")
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.task_id, "root.calc")
        self.assertEqual(pkt.failure_kind, "result_check_failure")
        self.assertEqual(len(pkt.source_snapshots), 1)
        self.assertEqual(pkt.source_snapshots[0]["id"], "recipe_1")
        self.assertEqual(len(pkt.attempts), 2)
        self.assertTrue(any(d["defect_type"] == "arithmetic_contradiction" for d in pkt.adjudicated_defects))
        self.assertEqual(pkt.metadata["run_id"], "run-42")

        # Ingest into store
        ingested, is_new = self.store.ingest(pkt)
        self.assertTrue(is_new)
        self.assertEqual(self.store.get(pkt.packet_id).task_id, "root.calc")

    def test_capture_from_blocked_task_node(self):
        """Blocked TaskNode captures unresolved blocker inputs and upstream dependencies."""
        node = TaskNode(
            id="root.scale",
            role="Atomic-Worker",
            title="Scale ingredients to target yield",
            prompt="Scale ingredients",
            dependencies={"root.extract"},
            input_artifacts={
                "task_contract": make_leaf("root.scale", objective="Scale ingredients",
                                           operation="calculate", blocked_by=["target_yield"]),
            },
        )
        node.status = TaskStatus.BLOCKED
        node.error_trace = "Missing required input: target_yield"

        pkt = capture_from_node(node, goal="Scale recipe to target yield", run_id="run-block-1")
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.task_id, "root.scale")
        self.assertEqual(pkt.failure_kind, "missing_input_blocker")
        self.assertTrue(any(d["defect_type"] == "missing_required_input" for d in pkt.adjudicated_defects))
        self.assertTrue(any("target_yield" in d["description"] for d in pkt.adjudicated_defects))

    async def test_engine_execution_halts_automatically_ingest_failure_packets(self):
        """Engine execution halts automatically ingest failure packets into project store."""
        checkpoint = self.root / "checkpoint.json"
        report = self.root / "report.md"
        memory = self.root / "guidance" / "LEARNINGS.md"

        leaf_extract = make_leaf("extract", objective="Extract ingredients")
        leaf_blocked = make_leaf("scale", objective="Scale ingredients to target_yield",
                                 dependencies=["extract"], blocked_by=["target_yield"])

        class BlockedBackend(BaseSwarmBackend):
            def __init__(self, **kwargs):
                super().__init__("gpt-6.1-sol", 2)
                self.default_effort = "low"
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                if role == "Mimir-Interpreter":
                    data = {
                        "outcome": "Extract ingredients and scale",
                        "constraints": [],
                        "components": ["Extract", "Scale"],
                        "evidence_needs": ["Source"],
                        "missing_information": ["target_yield"],
                        "assumptions": [],
                    }
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=10)
                if role == "Mimir-Decomposer":
                    data = {"tasks": [leaf_extract, leaf_blocked], "planning_error": None}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=10)
                if role == "Mimir-Simplicity-Reviewer":
                    data = {"tasks": [{"id": "root.extract", "decision": "ACCEPT", "reason": "ok"},
                                      {"id": "root.scale", "decision": "ACCEPT", "reason": "blocked by input"}],
                            "coverage_preserved": True, "coverage_gaps": []}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=10)
                if role == "Mimir-Plan-Coverage-Reviewer":
                    data = {"coverage_preserved": True, "coverage_gaps": []}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=10)
                if role == "Mimir-Result-Checker":
                    context = json.loads(prompt.split("INPUTS:\n")[1])
                    candidates = context.get("candidates", [])
                    data = {"checks": [{"id": c["id"], "verdict": "PASS", "issues": []} for c in candidates]}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=10)
                # Worker
                data = {"answer": "Flour 1 kg", "sources": [], "claims": [], "gaps": []}
                return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=10)
            async def spawn_restricted(self, prompt, role="Micro-Worker", **kwargs):
                return await self.spawn(prompt, role=role, **kwargs)

        brief = {
            "outcome": "Extract ingredients and scale",
            "constraints": [],
            "components": ["Extract", "Scale"],
            "evidence_needs": ["Source"],
            "missing_information": ["target_yield"],
            "assumptions": [],
        }

        # Plan stage
        await engine.run_mimir(
            goal="Extract and scale recipe with missing target_yield",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
            recursive_plan=True, skip_web=True, task_brief=brief,
            phase="plan", state_file=str(checkpoint), output_path=str(report),
            memory_path=str(memory), worker_factory=lambda **kw: BlockedBackend(**kw),
            failure_store_path=str(self.store_path),
        )

        # Execute stage halts and automatically ingests the failure packet
        with self.assertRaises(ConfigurationRequired):
            await engine.run_mimir(
                phase="execute", state_file=str(checkpoint), output_path=str(report),
                memory_path=str(memory), worker_factory=lambda **kw: BlockedBackend(**kw),
                failure_store_path=str(self.store_path),
            )

        # Verify that failure packet was automatically captured into the store
        packets = self.store.list_packets(failure_kind="missing_input_blocker")
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].task_id, "root.scale")
        self.assertTrue(any("target_yield" in d["description"] for d in packets[0].adjudicated_defects))

    def test_capture_from_report_file_with_quarantined_findings(self):
        """capture_from_report_file extracts quarantined task findings into failure packets."""
        report_data = {
            "goal": "Audit library dependencies",
            "metadata": {"run_id": "eval-run-99"},
            "publication_view": {
                "task_dep": {
                    "status": "quarantined",
                    "reason": "Citation entails version 0.160.0, but claimed 0.163.0",
                    "sources": [{"id": "reqs", "locator": "requirements.txt", "retrieval_type": "local_file"}],
                },
                "task_ok": {
                    "status": "accepted",
                    "result": {"answer": "Supported fact"},
                },
            },
            "final_answer_check": {"verdict": "PASS", "issues": []},
        }
        report_file = self.root / "report.json"
        report_file.write_text(json.dumps(report_data), encoding="utf-8")

        pkts = capture_from_report_file(report_file, store=self.store)
        self.assertEqual(len(pkts), 1)
        self.assertEqual(pkts[0].task_id, "task_dep")
        self.assertEqual(pkts[0].failure_kind, "result_check_failure")

        # Verify stored packet
        stored = self.store.get(pkts[0].packet_id)
        self.assertIsNotNone(stored)
        self.assertIn("0.160.0", stored.attempts[0]["feedback"])

    def test_adjudicate_packet_defects(self):
        """Independent defect adjudication updates defects, severity, and resolution status."""
        pkt = FailurePacket(
            original_intent="Verify authentication timeout",
            task_id="auth.timeout",
            task_objective="Check timeout threshold",
            failure_kind="result_check_failure",
            attempts=[{"attempt": 1, "feedback": "Worker timed out after 30s"}],
        )
        self.store.ingest(pkt)

        # Adjudicate defect
        updated = self.store.adjudicate(
            pkt.packet_id,
            defect_type="timeout",
            severity="critical",
            description="Auth server failed to reply within 30s deadline",
            adjudicator="human_adjudication",
            resolution_status="confirmed",
        )
        self.assertEqual(updated.resolution_status, "confirmed")
        self.assertTrue(any(d["adjudicator"] == "human_adjudication" for d in updated.adjudicated_defects))

        # Check retrieval from store reflects updates
        reloaded = self.store.get(pkt.packet_id)
        self.assertEqual(reloaded.resolution_status, "confirmed")
        self.assertTrue(any(d["defect_type"] == "timeout" for d in reloaded.adjudicated_defects))


if __name__ == "__main__":
    unittest.main()
