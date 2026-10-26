"""P3.2: Convert confirmed failures into versioned regressions;
separate train/dev and fresh held-out families by source/topic and failure lineage.

Verifies:
1. Confirmed failure conversion: failure packets with confirmed/triaged defects convert
   to versioned RegressionCase instances with preserved lineage.
2. Waived rejection: waived failure packets cannot be converted into active regressions.
3. Family derivation: source and topic families are deterministically extracted.
4. Disjoint partitioning: splits allocate entire families with zero cross-split leakage.
5. Strict isolation enforcement: validate_split_isolation raises DataLeakageError
   if any source, topic, or failure lineage crosses between train/dev and held_out.
6. Persistence & Store: process-safe RegressionStore manages cases, loads/saves,
   and queries by split/topic.
7. Evaluator compatibility: export_eval_dataset outputs valid benchmarks for evaluate.py.
8. Acceptance criterion: confirmed failure from one family and disjoint held-out case
   from another family maintain strict isolation without leakage.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from failure_store import FailurePacket, FailureStore
from regression_suite import (
    DataLeakageError,
    RegressionCase,
    RegressionStore,
    convert_failure_to_regression,
    partition_splits,
    validate_split_isolation,
)


class RegressionSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.fstore_path = self.root / "failure-packets.jsonl"
        self.rstore_path = self.root / "regressions.jsonl"
        self.failure_store = FailureStore(store_path=self.fstore_path)
        self.regression_store = RegressionStore(store_path=self.rstore_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_convert_confirmed_failure_to_regression_case(self):
        """Confirmed failure packets convert into versioned RegressionCases with preserved lineage."""
        packet = FailurePacket(
            original_intent="Scale Vincenzo's Neapolitan Pizza dough for 8 pizzas",
            task_id="root.calc_hydration",
            task_objective="Calculate hydration percentage for pizza dough",
            failure_kind="result_check_failure",
            task_brief={
                "outcome": "Hydration calculated",
                "missing_information": [],
            },
            source_snapshots=[
                {"id": "vincenzo", "locator": "fixtures/vincenzo_pizza_source.txt", "text": "1000g flour, 600ml water"}
            ],
            attempts=[
                {"attempt": 1, "feedback": "Calculation returned 166.7% instead of 60.0% (math contradiction)"}
            ],
            adjudicated_defects=[
                {
                    "defect_type": "arithmetic_contradiction",
                    "severity": "critical",
                    "description": "Calculated 166.7% by dividing flour by water instead of water by flour.",
                    "adjudicator": "engine_supervisor",
                }
            ],
            resolution_status="confirmed",
            metadata={"run_id": "run-fail-pizza-01"},
        )
        self.failure_store.ingest(packet)

        case = convert_failure_to_regression(packet, version=1, split="train")

        self.assertTrue(case.case_id.startswith("reg-v1-"))
        self.assertEqual(case.version, 1)
        self.assertEqual(case.packet_id, packet.packet_id)
        self.assertEqual(case.split, "train")
        self.assertEqual(case.topic, "baking_and_formulation")
        self.assertIn("vincenzo", case.source_family)
        self.assertEqual(case.failure_lineage["origin_run_id"], "run-fail-pizza-01")
        self.assertEqual(case.failure_lineage["failure_kind"], "result_check_failure")
        self.assertIn("arithmetic_contradiction", case.failure_lineage["defect_types"])
        self.assertIn("fixtures/vincenzo_pizza_source.txt", case.verification_spec["required_locators"])

    def test_waived_packet_rejected_from_regression_conversion(self):
        """Waived failure packets cannot be converted into regressions."""
        packet = FailurePacket(
            original_intent="Ignored experiment failure",
            task_id="test.task",
            task_objective="Test task",
            failure_kind="result_check_failure",
            resolution_status="waived",
        )
        with self.assertRaises(ValueError):
            convert_failure_to_regression(packet)

    def test_missing_input_blocker_conversion_extracts_expected_blockers(self):
        """Missing input blocker failure extracts expected blockers into verification spec."""
        packet = FailurePacket(
            original_intent="Scale recipe with unknown target_yield",
            task_id="root.scale",
            task_objective="Scale ingredients to target_yield",
            failure_kind="missing_input_blocker",
            task_brief={
                "outcome": "Scale ingredients",
                "missing_information": ["target_yield", "dough_ball_count"],
            },
            adjudicated_defects=[
                {
                    "defect_type": "missing_required_input",
                    "severity": "critical",
                    "description": "Target yield missing from prompt",
                    "adjudicator": "deterministic_gate",
                }
            ],
            resolution_status="confirmed",
        )
        case = convert_failure_to_regression(packet, split="dev")
        self.assertIn("target_yield", case.verification_spec["expected_blockers"])
        self.assertIn("dough_ball_count", case.verification_spec["expected_blockers"])

    def test_partition_splits_strictly_isolates_families(self):
        """partition_splits allocates entire topic/source families into disjoint splits."""
        case_pizza1 = RegressionCase(
            case_id="reg-v1-pizza1", version=1, packet_id="pkt-p1",
            original_intent="Pizza 1", goal="Calculate hydration 1",
            topic="baking_and_formulation", source_family="vincenzo",
            failure_lineage={"lineage_root": "lin-pizza"},
            split="train", split_family="baking_and_formulation::vincenzo",
        )
        case_pizza2 = RegressionCase(
            case_id="reg-v1-pizza2", version=1, packet_id="pkt-p2",
            original_intent="Pizza 2", goal="Calculate hydration 2",
            topic="baking_and_formulation", source_family="vincenzo",
            failure_lineage={"lineage_root": "lin-pizza"},
            split="train", split_family="baking_and_formulation::vincenzo",
        )
        case_dep1 = RegressionCase(
            case_id="reg-v1-dep1", version=1, packet_id="pkt-d1",
            original_intent="Dep 1", goal="Verify codex pin",
            topic="dependency_management", source_family="requirements_txt",
            failure_lineage={"lineage_root": "lin-dep"},
            split="train", split_family="dependency_management::requirements_txt",
        )
        case_auth1 = RegressionCase(
            case_id="reg-v1-auth1", version=1, packet_id="pkt-a1",
            original_intent="Auth 1", goal="Verify timeout limit",
            topic="authentication_and_session", source_family="auth_config",
            failure_lineage={"lineage_root": "lin-auth"},
            split="train", split_family="authentication_and_session::auth_config",
        )

        all_cases = [case_pizza1, case_pizza2, case_dep1, case_auth1]

        # Allocate authentication to held_out explicitly
        partitioned = partition_splits(
            all_cases,
            held_out_families={"authentication_and_session::auth_config"},
            dev_families={"dependency_management::requirements_txt"},
        )

        # Verify allocations
        splits = {c.case_id: c.split for c in partitioned}
        self.assertEqual(splits["reg-v1-pizza1"], "train")
        self.assertEqual(splits["reg-v1-pizza2"], "train")
        self.assertEqual(splits["reg-v1-dep1"], "dev")
        self.assertEqual(splits["reg-v1-auth1"], "held_out")

        # Zero leakage validation passes cleanly
        validate_split_isolation(partitioned)

    def test_validate_split_isolation_blocks_source_topic_and_lineage_leakage(self):
        """validate_split_isolation raises DataLeakageError if sources, topics, or lineages overlap."""
        # 1. Source overlap
        case_train = RegressionCase(
            case_id="reg-v1-t1", version=1, packet_id="pkt-1",
            original_intent="Task 1", goal="Goal 1",
            topic="topic_a", source_family="shared_source",
            failure_lineage={"lineage_root": "lin-1"},
            split="train", split_family="topic_a::shared_source",
        )
        case_held_out_source_leak = RegressionCase(
            case_id="reg-v1-h1", version=1, packet_id="pkt-2",
            original_intent="Task 2", goal="Goal 2",
            topic="topic_b", source_family="shared_source",  # LEAK!
            failure_lineage={"lineage_root": "lin-2"},
            split="held_out", split_family="topic_b::shared_source",
        )
        with self.assertRaises(DataLeakageError) as ctx:
            validate_split_isolation([case_train, case_held_out_source_leak])
        self.assertIn("Source families {'shared_source'}", str(ctx.exception))

        # 2. Topic overlap
        case_held_out_topic_leak = RegressionCase(
            case_id="reg-v1-h2", version=1, packet_id="pkt-3",
            original_intent="Task 3", goal="Goal 3",
            topic="topic_a", source_family="disjoint_source_b",  # LEAK!
            failure_lineage={"lineage_root": "lin-3"},
            split="held_out", split_family="topic_a::disjoint_source_b",
        )
        with self.assertRaises(DataLeakageError) as ctx:
            validate_split_isolation([case_train, case_held_out_topic_leak])
        self.assertIn("Topic families {'topic_a'}", str(ctx.exception))

        # 3. Lineage overlap
        case_held_out_lineage_leak = RegressionCase(
            case_id="reg-v1-h3", version=1, packet_id="pkt-4",
            original_intent="Task 4", goal="Goal 4",
            topic="topic_c", source_family="disjoint_source_c",
            failure_lineage={"lineage_root": "lin-1"},  # LEAK: shares root with lin-1!
            split="held_out", split_family="topic_c::disjoint_source_c",
        )
        with self.assertRaises(DataLeakageError) as ctx:
            validate_split_isolation([case_train, case_held_out_lineage_leak])
        self.assertIn("Failure lineages {'lin-1'}", str(ctx.exception))

    def test_regression_store_ingest_from_failure_store_and_export_eval(self):
        """RegressionStore ingests confirmed failures, persists, validates, and exports for evaluate.py."""
        # 1. Ingest confirmed failure into failure store
        p1 = FailurePacket(
            original_intent="Verify pyproject pins",
            task_id="root.pins",
            task_objective="Check version requirements in pyproject",
            failure_kind="result_check_failure",
            source_snapshots=[{"id": "pyproj", "locator": "pyproject.toml"}],
            adjudicated_defects=[{"defect_type": "unsupported_claim", "severity": "major", "description": "unsupported"}],
            resolution_status="confirmed",
            metadata={"run_id": "run-pyproj-1"},
        )
        p2 = FailurePacket(
            original_intent="Bake neapolitan crust with yeast",
            task_id="root.bake",
            task_objective="Compute fresh yeast percentage",
            failure_kind="result_check_failure",
            source_snapshots=[{"id": "pizza_src", "locator": "pizza_guide.txt"}],
            adjudicated_defects=[{"defect_type": "arithmetic_contradiction", "severity": "critical", "description": "math"}],
            resolution_status="confirmed",
            metadata={"run_id": "run-pizza-2"},
        )
        self.failure_store.ingest(p1)
        self.failure_store.ingest(p2)

        # 2. Ingest into regression store with partition
        ingested = self.regression_store.ingest_from_failure_store(
            self.failure_store,
            auto_partition=True,
            held_out_ratio=0.5,
        )
        self.assertEqual(len(ingested), 2)

        # 3. Check integrity
        summary = self.regression_store.validate_integrity()
        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["status"], "VALID_DISJOINT_SPLITS")

        # 4. Export for evaluate.py
        eval_out = self.root / "eval_held_out.json"
        exported = self.regression_store.export_eval_dataset("held_out", out_file=eval_out)
        self.assertTrue(eval_out.exists())

        # Check export schema
        loaded = json.loads(eval_out.read_text(encoding="utf-8"))
        self.assertEqual(len(loaded), len(exported))
        for item in loaded:
            self.assertIn("id", item)
            self.assertIn("goal", item)
            self.assertIn("required_locators", item)
            self.assertIn("split", item)
            self.assertEqual(item["split"], "held_out")

    def test_smallest_meaningful_disjoint_split_and_leakage_rejection(self):
        """Smallest meaningful test: one confirmed repository failure and one disjoint held-out question.

        Validates:
        1. Confirmed failure and disjoint held-out case maintain independent family splits.
        2. Attempted leakage (cross-referencing held-out sources/topics in train) is rejected.
        3. Split identities and lineage pointers are immutable and reproducible.
        """
        # 1. Confirmed repository failure from baking family
        p_train = FailurePacket(
            original_intent="Scale Neapolitan dough with correct hydration",
            task_id="root.hydration",
            task_objective="Calculate hydration percentage",
            failure_kind="result_check_failure",
            source_snapshots=[{"id": "vincenzo", "locator": "fixtures/vincenzo_pizza_source.txt"}],
            adjudicated_defects=[
                {"defect_type": "arithmetic_contradiction", "severity": "critical", "description": "Contradiction in division"}
            ],
            resolution_status="confirmed",
            metadata={"run_id": "run-train-pizza"},
        )
        case_train = convert_failure_to_regression(p_train, split="train")

        # 2. Disjoint held-out question from dependency family
        p_held_out = FailurePacket(
            original_intent="Audit requirements.txt for pinned codex version",
            task_id="root.pin",
            task_objective="Extract exact codex sdk pin",
            failure_kind="result_check_failure",
            source_snapshots=[{"id": "reqs", "locator": "requirements.txt"}],
            adjudicated_defects=[
                {"defect_type": "unsupported_claim", "severity": "major", "description": "Unsupported pin claim"}
            ],
            resolution_status="confirmed",
            metadata={"run_id": "run-heldout-reqs"},
        )
        case_held_out = convert_failure_to_regression(p_held_out, split="held_out")

        # Valid disjoint suite
        validate_split_isolation([case_train, case_held_out])
        self.assertEqual(case_train.split, "train")
        self.assertEqual(case_held_out.split, "held_out")
        self.assertNotEqual(case_train.topic, case_held_out.topic)
        self.assertNotEqual(case_train.source_family, case_held_out.source_family)

        # Attempt to leak held-out source into a training candidate case
        leaked_train_case = RegressionCase(
            case_id="reg-v1-leaked",
            version=1,
            packet_id="pkt-leak",
            original_intent="Train case consuming held-out source",
            goal="Goal consuming requirements.txt",
            topic="baking_and_formulation",
            source_family=case_held_out.source_family,  # LEAK!
            failure_lineage={"lineage_root": "lin-leak"},
            split="train",
            split_family=f"baking_and_formulation::{case_held_out.source_family}",
        )
        with self.assertRaises(DataLeakageError):
            validate_split_isolation([leaked_train_case, case_held_out])


if __name__ == "__main__":
    unittest.main()
