"""Failure and provenance regressions for graph scheduling and JEV decisions."""

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from jev_gate import JevDecisionGate
from task_graph import Blackboard, EvidenceContract, EvidenceDelta, RecursiveDecomposer, TaskGraph, TaskNode, TaskStatus


def node(task_id, dependencies=(), **kwargs):
    return TaskNode(task_id, "Domain-Analyst", f"Analyze {task_id}", "Inspect evidence", dependencies=set(dependencies), **kwargs)


class FakeWorker:
    def __init__(self, data, status="SUCCESS"):
        self.result = SimpleNamespace(data=data, status=status, raw_response="worker response", duration_seconds=0.1)
        self.calls = []

    async def spawn(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class GraphIntegrityTests(unittest.TestCase):
    def test_duplicate_id_cannot_replace_original_task(self):
        graph = TaskGraph("review")
        first = node("t1")
        graph.add_node(first)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            graph.add_node(node("t1"))
        self.assertIs(graph.nodes["t1"], first)

    def test_cycles_and_missing_dependencies_cannot_be_scheduled(self):
        for dependencies in ({"t1"}, {"missing"}):
            with self.subTest(dependencies=dependencies):
                graph = TaskGraph("review")
                graph.add_node(node("t1", dependencies))
                with self.assertRaises(ValueError):
                    graph.get_execution_tiers()
                with self.assertRaises(ValueError):
                    graph.get_runnable_nodes()

    def test_failure_cascades_fully_with_reverse_insertion_order(self):
        graph = TaskGraph("review")
        graph.add_node(node("t3", {"t2"}))
        graph.add_node(node("t2", {"t1"}))
        graph.add_node(node("t1", status=TaskStatus.FAILED))
        graph.cascade_failure("t1")
        self.assertEqual(graph.nodes["t3"].status, TaskStatus.CANCELLED)
        self.assertEqual(graph.nodes["t2"].status, TaskStatus.CANCELLED)

    def test_ready_nodes_are_available_until_dispatched(self):
        graph = TaskGraph("review")
        graph.add_node(node("t1"))
        self.assertEqual(graph.get_runnable_nodes(), graph.get_runnable_nodes())

    def test_round_trip_preserves_completed_output_failure_and_provenance(self):
        graph = TaskGraph("review")
        n = node("t1", status=TaskStatus.COMPLETED, output_data={"finding": "source gap"}, duration_seconds=2.5,
                 retry_count=1, max_retries=3, error_trace="previous retry", input_artifacts={"source": "doc"})
        n.output_deltas = [EvidenceDelta("finding", "source gap", EvidenceContract("node://t1", "a" * 64))]
        graph.add_node(n)
        saved = json.loads(json.dumps(graph.to_dict()))
        self.assertEqual(TaskGraph.from_dict(saved).to_dict(), saved)

    def test_saved_graph_rejects_status_key_and_dependency_corruption(self):
        for changes in ({"status": "unknown"}, {"id": "other"}, {"dependencies": "t2"}, {"jev_score": float("nan")},
                        {"duration_seconds": float("inf")}, {"retry_count": -1}, {"depth": 5}):
            with self.subTest(changes=changes):
                graph = TaskGraph("review")
                graph.add_node(node("t1"))
                saved = graph.to_dict()
                saved["nodes"]["t1"].update(changes)
                with self.assertRaises(ValueError):
                    TaskGraph.from_dict(saved)


class BlackboardIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.board = Blackboard("review", task_dag={"t1": node("t1"), "t2": node("t2", {"t1"})})

    def test_commit_requires_registered_bytes_and_matching_node_provenance(self):
        contract = EvidenceContract("node://t1", "a" * 64, True)
        self.assertFalse(self.board.commit_evidence("t1", "t1_result", {}, contract))
        digest = self.board.register_evidence("raw output")
        contract.raw_evidence_hash = digest
        self.assertFalse(self.board.commit_evidence("t2", "t1_result", {}, contract))
        self.assertTrue(self.board.commit_evidence("t1", "t1_result", {}, contract))
        self.board.verified_evidence_store[digest] = "tampered bytes"
        self.assertFalse(self.board.commit_evidence("t1", "other", {}, contract))

    def test_unreviewed_output_retains_status_and_delta_cannot_self_approve(self):
        contract = EvidenceContract("node://t1", self.board.register_evidence("raw output"))
        self.assertFalse(contract.verification_passed)
        value = {"finding": ["candidate"]}
        self.assertTrue(self.board.commit_evidence("t1", "t1_result", value, contract))
        value["finding"].append("mutated")
        self.assertEqual(self.board.artifacts["t1_result"], {"finding": ["candidate"]})
        self.assertIn("unreviewed worker output", self.board.get_dependency_context("t2"))
        self.assertFalse(self.board.commit_evidence_delta(EvidenceDelta("t1_other", value, contract)))

    def test_dependency_context_includes_all_required_outputs_and_full_values(self):
        for index in range(8):
            task_id = f"d{index}"
            self.board.task_dag[task_id] = node(task_id)
            text = f"dependency-{index}:" + "x" * 450 + f" tail-{index}"
            contract = EvidenceContract(f"node://{task_id}", self.board.register_evidence(text))
            self.assertTrue(self.board.commit_evidence(task_id, f"{task_id}_result", text, contract))
        self.board.task_dag["t2"].dependencies = {f"d{i}" for i in range(6)}
        context = self.board.get_dependency_context("t2")
        for index in range(6):
            self.assertIn(f"tail-{index}", context)
        self.assertNotIn("dependency-6", context)
        self.assertNotIn("dependency-7", context)

    def test_missing_required_context_is_explicit_error(self):
        with self.assertRaisesRegex(ValueError, "Missing blackboard"):
            self.board.get_dependency_context("t2")
        self.board.task_dag["t2"].dependencies = {"missing"}
        with self.assertRaisesRegex(ValueError, "Unknown blackboard"):
            self.board.get_dependency_context("t2")

    def test_tampered_provenance_cannot_be_used_as_dependency_context(self):
        digest = self.board.register_evidence("raw output")
        self.board.commit_evidence("t1", "t1_result", "finding", EvidenceContract("node://t1", digest))
        self.board.verified_evidence_store[digest] = "tampered"
        with self.assertRaisesRegex(ValueError, "Invalid provenance"):
            self.board.get_dependency_context("t2")

    def test_artifact_key_cannot_be_overwritten_by_other_task(self):
        for task_id in ("t1", "t2"):
            contract = EvidenceContract(f"node://{task_id}", self.board.register_evidence(task_id))
            self.assertEqual(self.board.commit_evidence(task_id, "result", task_id, contract), task_id == "t1")


class DecisionAndDecompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_decomposition_never_fabricates_or_repairs_graph(self):
        valid = {"id": "t1", "role": "Domain-Analyst", "title": "Analyze", "objective": "Review code", "dependencies": []}
        invalid_data = [{}, {"tasks": []}, {"tasks": "invalid"}, {"tasks": [None]},
                        {"tasks": [valid, valid]}, {"tasks": [{**valid, "dependencies": "t2"}]},
                        {"tasks": [{**valid, "dependencies": ["missing"]}]},
                        {"tasks": [{**valid, "dependencies": ["t1"]}]},
                        {"tasks": [{**valid, "objective": ""}]}]
        for data in invalid_data:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    await RecursiveDecomposer(FakeWorker(data), mode="swarm").decompose_goal("review")

    async def test_valid_decomposition_retains_dependency_order(self):
        tasks = [{"id": "t2", "role": "Red-Team-Critic", "title": "Critique", "objective": "Challenge findings", "dependencies": ["t1"]},
                 {"id": "t1", "role": "Domain-Analyst", "title": "Analyze", "objective": "Review code", "dependencies": []}]
        brief = {"outcome": "Review", "constraints": [], "components": ["Analyze", "Critique"],
                 "evidence_needs": ["Current behavior"], "missing_information": []}
        graph = await RecursiveDecomposer(FakeWorker({"tasks": tasks, "task_brief": brief}), mode="swarm").decompose_goal("review")
        self.assertEqual([[n.id for n in tier] for tier in graph.get_execution_tiers()], [["t1"], ["t2"]])

    async def test_evidence_screen_fails_closed_on_bad_or_failed_worker_result(self):
        for status, data in [("FAILED", {"decision": "APPROVE", "confidence": 1}), ("SUCCESS", {}),
                             ("SUCCESS", None), ("SUCCESS", {"decision": "unknown", "confidence": 1})]:
            with self.subTest(status=status, data=data):
                result = await JevDecisionGate(FakeWorker(data, status)).screen_evidence_contract("review", "finding", "a" * 64)
                self.assertEqual(result, (False, 0.0, "AUDIT_REQUIRED"))

    async def test_evidence_confidence_rejects_nonfinite_coercions_and_out_of_range(self):
        for confidence in (float("nan"), float("inf"), -1, 2, "0.9", True, None):
            with self.subTest(confidence=confidence):
                gate = JevDecisionGate(FakeWorker({"decision": "APPROVE", "confidence": confidence}))
                self.assertEqual(await gate.screen_evidence_contract("review", "finding", "a" * 64), (False, 0.0, "AUDIT_REQUIRED"))

    async def test_choice_never_defaults_failed_output_to_confident_first_choice(self):
        for data, status in (({}, "SUCCESS"), ({"choice": "yes", "confidence": 1}, "FAILED"),
                             ({"choice": "other", "confidence": 1}, "SUCCESS")):
            with self.subTest(data=data, status=status):
                with self.assertRaises(ValueError):
                    await JevDecisionGate(FakeWorker(data, status)).evaluate_choice("context", "question", ["yes", "no"])

    async def test_pruning_does_not_assign_scores_from_failed_or_invalid_results(self):
        for data, status in (({}, "SUCCESS"), ({"criticality": 1, "redundancy_penalty": 0}, "FAILED"),
                             ({"criticality": float("nan"), "redundancy_penalty": 0}, "SUCCESS")):
            with self.subTest(data=data, status=status):
                with self.assertRaises(ValueError):
                    await JevDecisionGate(FakeWorker(data, status)).evaluate_task_jev("task", "prompt", "goal", [])

    async def test_valid_scores_and_screen_remain_supported(self):
        gate = JevDecisionGate(FakeWorker({"criticality": 0.8, "redundancy_penalty": 0.2}))
        self.assertAlmostEqual(await gate.evaluate_task_jev("task", "prompt", "goal", []), 0.72)
        gate = JevDecisionGate(FakeWorker({"decision": "APPROVE", "confidence": 0.9}))
        self.assertEqual(await gate.screen_evidence_contract("review", "finding", "a" * 64), (True, 0.9, "APPROVE"))

    async def test_pruning_rewires_removed_dependencies_and_protects_critic_and_synthesis(self):
        graph = TaskGraph("review")
        graph.add_node(node("t1"))
        graph.add_node(node("t2", {"t1"}))
        graph.add_node(TaskNode("t3", "Red-Team-Critic", "Critique", "Find risks", {"t2"}))
        graph.add_node(TaskNode("t4", "Executive-Synthesizer", "Synthesize", "Combine findings", {"t2", "t3"}))
        gate = JevDecisionGate(FakeWorker({"criticality": 0.1, "redundancy_penalty": 1}))
        self.assertEqual(await graph.prune_with_jev(gate), ["t2"])
        self.assertEqual(graph.nodes["t3"].dependencies, {"t1"})
        self.assertEqual(graph.nodes["t4"].dependencies, {"t1", "t3"})
        self.assertTrue(graph.validate_acyclic_and_integrity()[0])

    async def test_evidence_screen_receives_suffix_beyond_old_prefix_limit(self):
        worker = FakeWorker({"decision": "AUDIT_REQUIRED", "confidence": 0.9})
        payload = "plausible introduction " + "x" * 900 + " fabricated unsupported claim in suffix"
        await JevDecisionGate(worker).screen_evidence_contract("review", payload, "a" * 64)
        self.assertIn(payload, worker.calls[0]["prompt"])

    async def test_full_precision_score_preserves_pruning_threshold(self):
        gate = JevDecisionGate(FakeWorker({"criticality": 0.32, "redundancy_penalty": 0.15}))
        self.assertAlmostEqual(await gate.evaluate_task_jev("task", "prompt", "goal", []), 0.296)
        graph = TaskGraph("review")
        graph.add_node(node("root"))
        graph.add_node(node("optional", {"root"}))
        self.assertEqual(await graph.prune_with_jev(gate, min_jev=0.30), ["optional"])

    async def test_required_evidence_scout_and_their_prerequisites_survive_pruning(self):
        graph = TaskGraph("review")
        graph.add_node(node("root"))
        graph.add_node(node("prerequisite", {"root"}))
        graph.add_node(node("retrieval", {"prerequisite"}, required_evidence=True))
        graph.add_node(TaskNode("scout", "Intel-Scout", "Retrieve", "Read sources", {"root"}))
        graph.add_node(node("optional", {"root"}))
        gate = JevDecisionGate(FakeWorker({"criticality": 0.1, "redundancy_penalty": 1}))
        self.assertEqual(await graph.prune_with_jev(gate), ["optional"])
        self.assertEqual(graph.nodes["retrieval"].dependencies, {"prerequisite"})
        saved = json.loads(json.dumps(graph.to_dict()))
        self.assertTrue(TaskGraph.from_dict(saved).nodes["retrieval"].required_evidence)

    async def test_pruning_is_transactional_when_later_scoring_fails(self):
        graph = TaskGraph("review")
        graph.add_node(node("root", jev_score=0.7))
        graph.add_node(node("first", {"root"}, jev_score=0.8))
        graph.add_node(node("second", {"first"}, jev_score=0.9))
        before = graph.to_dict()
        class Gate:
            async def evaluate_task_jev(self, **kwargs):
                if kwargs["task_title"] == "Analyze second":
                    raise ValueError("malformed worker response")
                return 0.1
        with self.assertRaisesRegex(ValueError, "malformed worker"):
            await graph.prune_with_jev(Gate())
        self.assertEqual(graph.to_dict(), before)

    async def test_decomposer_preserves_required_evidence_metadata(self):
        task = {"id": "source", "role": "Domain-Analyst", "title": "Read evidence", "objective": "Retrieve sources", "required_evidence": True}
        brief = {"outcome": "Review", "constraints": [], "components": ["Retrieve sources"],
                 "evidence_needs": ["Primary sources"], "missing_information": []}
        graph = await RecursiveDecomposer(FakeWorker({"tasks": [task], "task_brief": brief}), mode="swarm").decompose_goal("review")
        self.assertTrue(graph.nodes["source"].required_evidence)
        with self.assertRaisesRegex(ValueError, "required_evidence"):
            await RecursiveDecomposer(FakeWorker({"tasks": [{**task, "required_evidence": "true"}]}), mode="swarm").decompose_goal("review")


if __name__ == "__main__":
    unittest.main()
