"""E4: Preserve E1 as a regression.

Tests:
1. Exact checkpoint-loading completeness guards in _load_state and run_mimir(phase="synthesize"):
   - Rejects missing completed_data with "Synthesis requires results for every planned task."
   - Rejects partial completed_data (missing planned task) with "Synthesis requires results for every planned task."
   - Rejects non-dict completed_data with "Synthesis requires results for every planned task."
   - Rejects malformed results with "Invalid persisted task results."
   - Rejects unusable worker output with "Synthesis requires usable output for every planned task."
   - Rejects uncompleted task status with "Synthesis requires every planned task to be completed."
   - Rejects missing identity records (result_hash, evidence_hash, input_fingerprint).
   - Rejects tampered result_hash or evidence_hash before runtime or model dispatch.
   - Rejects phase execute with missing retained result for completed task.
   - Rejects phase execute with retained result not subset of graph.
   - Rejects invalid phase transitions.
2. End-to-end repository review regression (E1 run 7eacc84b92a44c51b92bffa8a4e71cdd):
   - Overreaching worker claim ("incomplete legacy state could publish") softened by critic.
   - Checkpoint-loading completeness verified so incomplete state fails closed.
   - Publication view quarantines the overreaching claim, preventing uncorrected appendix leakage.
3. Versioned regression suite integration:
   - Registers E1 failure packet as versioned RegressionCase with preserved lineage.
   - Validates family isolation across train/dev and held-out splits.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import SwarmResult, WorkerFailure
from failure_store import FailurePacket, FailureStore
from publication_view import build_publication_view
from regression_suite import (
    DataLeakageError,
    RegressionCase,
    RegressionStore,
    convert_failure_to_regression,
    validate_split_isolation,
)
from task_graph import TaskGraph, TaskNode, TaskStatus
from test_engine_policy import FixtureBackend


def _make_valid_task_result(answer: str, raw: str = "raw evidence text") -> dict:
    result_dict = {
        "answer": answer,
        "sources": [{"id": "s1", "locator": "scripts/engine.py", "retrieval_type": "local_file", "support_excerpt": "def _load_state"}],
        "claims": [{"text": answer, "source_ids": ["s1"], "support_status": "supported", "rationale": "Direct code evidence"}],
        "gaps": [],
    }
    content = json.dumps(result_dict, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    result_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    evidence_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    fingerprint = hashlib.sha256(b"input_fingerprint").hexdigest()
    return {
        "result": result_dict,
        "raw_response": raw,
        "result_hash": result_hash,
        "evidence_hash": evidence_hash,
        "input_fingerprint": fingerprint,
    }


def _make_base_state(graph: TaskGraph, phase: str = "executed", mode: str = "review") -> dict:
    return {
        "version": 1,
        "goal": "Determine atomic admission, single/review publication and incomplete-graph behaviour",
        "phase": phase,
        "mode": mode,
        "graph": graph.to_dict(),
        "tasks": [t.id for t in graph.nodes.values()],
        "completed_data": {},
    }


class CheckpointLoadingGuardsTests(unittest.TestCase):
    """Verifies all deterministic completeness and integrity guards in _load_state."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.state_file = self.root / "state.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _write_state(self, state: dict):
        self.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def test_synthesize_rejects_missing_completed_data(self):
        """_load_state for phase=synthesize requires completed_data to be a valid dict."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executed")
        state.pop("completed_data", None)
        self._write_state(state)

        with self.assertRaisesRegex(ValueError, "Synthesis requires results for every planned task."):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_synthesize_rejects_partial_completed_data(self):
        """_load_state for phase=synthesize rejects checkpoints missing results for any planned task."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        graph.add_node(TaskNode("t2", "Code-Architect", "Task 2", "prompt 2", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executed")
        state["completed_data"] = {"t1": _make_valid_task_result("Result 1")}
        self._write_state(state)

        with self.assertRaisesRegex(ValueError, "Synthesis requires results for every planned task."):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_synthesize_rejects_non_dict_completed_data(self):
        """_load_state for phase=synthesize rejects non-dict completed_data structures."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executed")
        state["completed_data"] = ["not", "a", "dict"]
        self._write_state(state)

        with self.assertRaisesRegex(ValueError, "Synthesis requires results for every planned task."):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_synthesize_rejects_invalid_result_structure(self):
        """_load_state for phase=synthesize rejects tasks whose result is not a dictionary."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executed")
        state["completed_data"] = {"t1": "not-a-dict"}
        self._write_state(state)

        with self.assertRaisesRegex(ValueError, "Invalid persisted task results."):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_synthesize_rejects_unusable_worker_output(self):
        """_load_state for phase=synthesize rejects tasks whose result has no usable output."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executed")
        state["completed_data"] = {"t1": {"result": {}}}
        self._write_state(state)

        with self.assertRaisesRegex(ValueError, "Synthesis requires usable output for every planned task."):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_synthesize_rejects_uncompleted_task_status(self):
        """_load_state for phase=synthesize rejects checkpoints where a planned task is not COMPLETED."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.FAILED))
        state = _make_base_state(graph, phase="executed", mode="review")
        state["completed_data"] = {"t1": _make_valid_task_result("Result 1")}
        self._write_state(state)

        with self.assertRaisesRegex(engine.ConfigurationRequired, "Synthesis requires every planned task to be completed."):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_synthesize_rejects_missing_identity_records(self):
        """_load_state for phase=synthesize rejects tasks without identity records."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executed", mode="review")
        res = _make_valid_task_result("Result 1")
        del res["result_hash"]
        state["completed_data"] = {"t1": res}
        self._write_state(state)

        with self.assertRaisesRegex(engine.ConfigurationRequired, "Retained task is missing its identity records"):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_synthesize_rejects_tampered_result_hash(self):
        """_load_state for phase=synthesize detects modified result payload vs result_hash."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executed", mode="review")
        res = _make_valid_task_result("Original answer")
        res["result"]["answer"] = "Tampered unauthorized claim"
        state["completed_data"] = {"t1": res}
        self._write_state(state)

        with self.assertRaisesRegex(engine.ConfigurationRequired, "Retained result identity changed"):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_synthesize_rejects_tampered_evidence_hash(self):
        """_load_state for phase=synthesize detects modified raw_response vs evidence_hash."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executed", mode="review")
        res = _make_valid_task_result("Original answer", raw="original raw text")
        res["raw_response"] = "altered raw text without hash update"
        state["completed_data"] = {"t1": res}
        self._write_state(state)

        with self.assertRaisesRegex(engine.ConfigurationRequired, "Retained raw evidence identity changed"):
            engine._load_state(str(self.state_file), phase="synthesize")

    def test_execute_phase_rejects_missing_retained_result_for_completed_task(self):
        """_load_state for phase=execute rejects checkpoints where a COMPLETED task has no retained result."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executing", mode="review")
        state["completed_data"] = {}
        self._write_state(state)

        with self.assertRaisesRegex(ValueError, "Completed task is missing its retained result."):
            engine._load_state(str(self.state_file), phase="execute")

    def test_execute_phase_rejects_retained_results_outside_graph(self):
        """_load_state for phase=execute rejects completed_data keys that are not nodes in the graph."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1", status=TaskStatus.COMPLETED))
        state = _make_base_state(graph, phase="executing", mode="review")
        state["completed_data"] = {"t1": _make_valid_task_result("Result 1"), "unplanned_task": _make_valid_task_result("Unplanned")}
        self._write_state(state)

        with self.assertRaisesRegex(ValueError, "Invalid retained task results."):
            engine._load_state(str(self.state_file), phase="execute")

    def test_invalid_phase_transition_rejected(self):
        """_load_state rejects illegal phase transitions (e.g. synthesize from planned state)."""
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Task 1", "prompt 1"))
        state = _make_base_state(graph, phase="planned")
        self._write_state(state)

        with self.assertRaisesRegex(ValueError, "Cannot synthesize state in phase 'planned'."):
            engine._load_state(str(self.state_file), phase="synthesize")


class RunMimirIncompleteCheckpointRejectionTests(unittest.IsolatedAsyncioTestCase):
    """Verifies that run_mimir fails closed before executing workers or synthesizers when checkpoint is incomplete."""

    async def test_run_mimir_synthesize_fails_closed_without_worker_or_synthesis_dispatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_file = root / "checkpoint.json"
            report_file = root / "report.md"

            graph = TaskGraph("E1 Repository Review")
            graph.add_node(TaskNode("evidence", "Domain-Analyst", "Inspect evidence", "Prompt 1", status=TaskStatus.COMPLETED))
            graph.add_node(TaskNode("architecture", "Code-Architect", "Inspect architecture", "Prompt 2", status=TaskStatus.PENDING))

            state = _make_base_state(graph, phase="executed", mode="review")
            state["completed_data"] = {"evidence": _make_valid_task_result("Evidence result")}
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            backend = FixtureBackend()
            with patch.object(engine, "create_swarm_backend", return_value=backend):
                with self.assertRaisesRegex(ValueError, "Synthesis requires results for every planned task."):
                    await engine.run_mimir(
                        phase="synthesize",
                        state_file=str(state_file),
                        output_path=str(report_file),
                        worker_factory=lambda **kw: backend,
                    )

            # Assert zero backend calls were made (no synthesizer, no checker)
            self.assertEqual(len(backend.calls), 0)
            self.assertFalse(report_file.exists())
            self.assertFalse(report_file.with_suffix(".json").exists())


class E1RepositoryReviewRegressionTests(unittest.TestCase):
    """End-to-end regression covering E1 run 7eacc84b92a44c51b92bffa8a4e71cdd.

    Scenario:
    - Evidence specialist asserts an overreaching claim: "incomplete legacy state could publish".
    - Critic points out that _load_state completeness enforcement rejects incomplete checkpoints.
    - Publication view marks/quarantines the uncorrected claim, preserving truthful status.
    """

    def test_e1_overreaching_claim_softened_by_critic_and_quarantined_in_publication(self):
        source_file = str(Path(__file__).resolve().parents[1] / "scripts" / "engine.py")
        code_excerpt = 'if not isinstance(results, dict) or set(results) != set(graph.nodes):\n    raise ValueError("Synthesis requires results for every planned task.")'

        # Evidence specialist claims incomplete legacy state could publish (overreaching defect)
        evidence_bad_finding = {
            "answer": "Incomplete legacy state could publish without completing all planned tasks.",
            "sources": [{"id": "eng", "locator": source_file, "retrieval_type": "local_file", "support_excerpt": code_excerpt}],
            "claims": [{
                "text": "Incomplete legacy state could publish without completing all planned tasks.",
                "source_ids": ["eng"],
                "support_status": "supported",
                "rationale": "Specialist assumed omission in graph completeness checks",
            }],
            "gaps": ["Did not verify _load_state synthesis entrypoint"],
        }

        # Architecture specialist observes accurate node completion behavior
        architecture_finding = {
            "answer": "Phased execution requires nodes to reach COMPLETED status before execution terminates.",
            "sources": [{"id": "eng", "locator": source_file, "retrieval_type": "local_file", "support_excerpt": code_excerpt}],
            "claims": [{
                "text": "Phased execution requires nodes to reach COMPLETED status before execution terminates.",
                "source_ids": ["eng"],
                "support_status": "supported",
                "rationale": "Direct engine.py inspection",
            }],
            "gaps": [],
        }

        # Critic softens the evidence worker's overreaching claim
        critique_finding = {
            "answer": "Critique: The evidence claim that incomplete legacy state can publish is incorrect. _load_state strictly rejects incomplete checkpoints with 'Synthesis requires results for every planned task.'",
            "sources": [{"id": "eng", "locator": source_file, "retrieval_type": "local_file", "support_excerpt": code_excerpt}],
            "claims": [{
                "text": "_load_state rejects incomplete checkpoints before synthesis phase can execute.",
                "source_ids": ["eng"],
                "support_status": "supported",
                "rationale": "engine.py line 665 enforcement",
            }],
            "gaps": [],
        }

        # Context matching engine and publication view schema
        context = {
            "findings": {
                "evidence": evidence_bad_finding,
                "architecture": architecture_finding,
            },
            "checks": {
                "critic_findings": {
                    "critique": critique_finding,
                }
            },
        }

        # Quarantine the overreaching evidence finding
        quarantines = [
            {
                "task_id": "evidence",
                "reason": "Overreaching claim refuted by critic: _load_state strictly enforces results for all planned tasks before synthesis.",
            }
        ]

        # Build checked publication view
        view = build_publication_view(
            context=context,
            quarantines=quarantines,
        )

        # 1. Quarantined task is marked explicitly and excludes the raw result
        self.assertIn("evidence", view)
        self.assertEqual(view["evidence"]["status"], "quarantined")
        self.assertIn("Overreaching claim refuted", view["evidence"]["reason"])
        self.assertNotIn("result", view["evidence"])

        # 2. Accepted tasks retain their validated result payloads
        self.assertEqual(view["architecture"]["status"], "accepted")
        self.assertEqual(view["architecture"]["result"]["answer"], architecture_finding["answer"])
        self.assertEqual(view["critique"]["status"], "accepted")
        self.assertEqual(view["critique"]["result"]["answer"], critique_finding["answer"])

        # 3. Released findings view cleanly separates accepted and quarantined tasks
        accepted_task_ids = [tid for tid, entry in view.items() if entry["status"] == "accepted"]
        quarantined_task_ids = [tid for tid, entry in view.items() if entry["status"] == "quarantined"]
        self.assertEqual(sorted(accepted_task_ids), ["architecture", "critique"])
        self.assertEqual(quarantined_task_ids, ["evidence"])


class E1RegressionSuiteRegistrationTests(unittest.TestCase):
    """Verifies that E1 is captured and registered as a versioned RegressionCase."""

    def test_e1_failure_packet_conversion_and_split_isolation(self):
        packet = FailurePacket(
            original_intent="Determine atomic admission, single/review publication and incomplete-graph behaviour",
            task_id="evidence",
            task_objective="Inspect repository execution and checkpoint-loading completeness",
            failure_kind="result_check_failure",
            task_brief={
                "outcome": "Verification of checkpoint loading completeness",
                "missing_information": [],
            },
            source_snapshots=[
                {"id": "engine_src", "locator": "scripts/engine.py", "text": "def _load_state(state_file, phase)"}
            ],
            adjudicated_defects=[
                {
                    "defect_type": "unsupported_claim",
                    "description": "Evidence worker asserted incomplete legacy state could publish; omitted _load_state completeness enforcement",
                    "severity": "major",
                }
            ],
            metadata={
                "run_id": "7eacc84b92a44c51b92bffa8a4e71cdd",
            },
            resolution_status="confirmed",
        )

        # Convert to versioned regression case in 'dev' split
        case = convert_failure_to_regression(
            packet,
            split="dev",
            version=1,
            topic="incomplete_graph_behavior",
            source_family="engine_py",
            verification_spec={
                "required_locators": ["scripts/engine.py"],
                "expected_defect_types": ["unsupported_claim"],
                "required_answer_markers": ["Synthesis requires results for every planned task."],
                "forbidden_answer_markers": ["incomplete legacy state could publish"],
            },
        )

        self.assertEqual(case.split, "dev")
        self.assertEqual(case.topic, "incomplete_graph_behavior")
        self.assertEqual(case.source_family, "engine_py")
        self.assertEqual(case.failure_lineage["origin_run_id"], "7eacc84b92a44c51b92bffa8a4e71cdd")
        self.assertIn("Synthesis requires results for every planned task.", case.verification_spec["required_answer_markers"])

        # Create a disjoint held-out case from a different domain/source family
        held_out_case = RegressionCase(
            case_id="reg-heldout-recipe-1",
            version=1,
            packet_id="packet-heldout-pizza-1",
            original_intent="Compute hydration for Neapolitan pizza dough",
            goal="Calculate dough formula",
            topic="baking_and_formulation",
            source_family="vincenzo_recipe",
            failure_lineage={"origin_run_id": "run-pizza-001", "failure_kind": "formula_error"},
            split="held_out",
            split_family="baking_and_formulation::vincenzo_recipe",
            bound_sources=[{"id": "vincenzo", "locator": "fixtures/vincenzo.txt"}],
            verification_spec={"required_answer_markers": ["60% hydration"]},
        )

        # Validate that dev and held-out splits are completely family-disjoint
        validate_split_isolation([case, held_out_case])

        # Test export to eval dataset
        eval_case = case.to_eval_case()
        self.assertEqual(eval_case["id"], case.case_id)
        self.assertEqual(eval_case["lineage"]["origin_run_id"], "7eacc84b92a44c51b92bffa8a4e71cdd")


if __name__ == "__main__":
    unittest.main()
