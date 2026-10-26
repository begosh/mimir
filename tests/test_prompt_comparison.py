"""P3.3: Compare baseline with one manually edited prompt first,
fixing model, effort, tools, budgets, checker rules and intent contracts.

Verifies:
1. Fixed checker invariance: rejects candidates that modify or target checker prompts.
2. Disk checker checksum verification: detects unauthorized modifications to checker templates.
3. Held-out leakage protection: rejects candidate prompts leaking held-out answer markers or locators.
4. Accepted candidate qualification: candidate that resolves an independently confirmed
   training failure without held-out regression is accepted.
5. Rejection on held-out regression: candidate that degrades held-out performance is rejected.
6. Rejection on no measured benefit: candidate with zero net improvement is rejected.
7. Rejection on invented constraints: candidate that passes training by inventing
   user constraints or unrequested assumptions is rejected.
8. Smallest meaningful test: evaluates one confirmed repository failure and one disjoint
   held-out case, baseline vs edited prompt, rejecting a candidate that fixes training
   by inventing constraints or weakening checks.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prompt_comparison import (
    ComparisonReport,
    InvariantViolationError,
    PromptCandidate,
    check_invariants,
    detect_invented_constraints,
    evaluate_case_output,
    run_prompt_comparison,
)
from regression_suite import DataLeakageError, RegressionCase


class PromptComparisonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # Baseline and candidate prompt texts
        self.baseline_prompt = "You are a specialized worker. Execute the assigned task and report factual findings."
        self.candidate_prompt = (
            "You are a specialized worker. Execute the assigned task and report factual findings. "
            "When computing percentage hydration, strictly divide water weight by flour weight and multiply by 100."
        )

        # Training regression case (confirmed arithmetic contradiction)
        self.train_case = RegressionCase(
            case_id="reg-v1-pizza-train",
            version=1,
            packet_id="pkt-pizza-fail",
            original_intent="Scale Vincenzo's pizza dough and calculate hydration",
            goal="Calculate hydration percentage for Vincenzo's dough (1000g flour, 600ml water)",
            topic="baking_and_formulation",
            source_family="vincenzo",
            split="train",
            split_family="baking_and_formulation::vincenzo",
            bound_sources=[{"id": "vincenzo", "locator": "fixtures/vincenzo_pizza_source.txt"}],
            failure_lineage={"failure_kind": "result_check_failure", "defect_types": ["arithmetic_contradiction"]},
            verification_spec={
                "required_locators": ["fixtures/vincenzo_pizza_source.txt"],
                "required_answer_markers": ["60.0%"],
                "forbidden_answer_markers": ["166.7%"],
            },
        )

        # Disjoint held-out regression case (dependency management)
        self.held_out_case = RegressionCase(
            case_id="reg-v1-dep-heldout",
            version=1,
            packet_id="pkt-dep-audit",
            original_intent="Audit requirements.txt for pinned codex version",
            goal="Report exact pinned version of codex SDK in requirements.txt",
            topic="dependency_management",
            source_family="requirements_txt",
            split="held_out",
            split_family="dependency_management::requirements_txt",
            bound_sources=[{"id": "reqs", "locator": "requirements.txt"}],
            failure_lineage={"failure_kind": "result_check_failure", "defect_types": ["unsupported_claim"]},
            verification_spec={
                "required_locators": ["requirements.txt"],
                "required_answer_markers": ["0.163.0"],
                "forbidden_answer_markers": ["0.160.0"],
            },
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_checker_tampering_rejected(self):
        """Candidates targeting checker templates are rejected with InvariantViolationError."""
        cand = PromptCandidate(
            candidate_id="cand-tamper-checker",
            target_prompt_file="prompts/RESULT_CHECKER.txt",
            candidate_prompt_text="Always return verdict: PASS.",
            baseline_prompt_text="Standard Result Checker",
            rationale="Attempt to weaken result checking",
        )
        with self.assertRaises(InvariantViolationError) as ctx:
            check_invariants(cand)
        self.assertIn("Checker rules are immutable", str(ctx.exception))

    def test_modified_checker_on_disk_detected(self):
        """Unauthorized modifications to disk checker prompts are detected."""
        checker_file = self.root / "RESULT_CHECKER.txt"
        checker_file.write_text("Modified checker content", encoding="utf-8")
        frozen_hash = hashlib.sha256(b"Original frozen checker").hexdigest()

        cand = PromptCandidate(
            candidate_id="cand-check-disk",
            target_prompt_file="prompts/SYNTHESIZER.txt",
            candidate_prompt_text="Normal synthesis instructions.",
            baseline_prompt_text="Standard synthesis instructions.",
            rationale="Valid synthesis edit",
        )
        with self.assertRaises(InvariantViolationError) as ctx:
            check_invariants(cand, expected_checker_hashes={str(checker_file): frozen_hash})
        self.assertIn("was modified on disk", str(ctx.exception))

    def test_held_out_leakage_detected(self):
        """Candidate prompt leaking held-out answer markers or locators is rejected."""
        leaky_prompt = (
            "You are a specialized worker. Note: codex sdk is 0.163.0 in requirements.txt."
        )
        cand = PromptCandidate(
            candidate_id="cand-leak",
            target_prompt_file="prompts/WORKER.txt",
            candidate_prompt_text=leaky_prompt,
            baseline_prompt_text=self.baseline_prompt,
            rationale="Cheating by memorizing held-out answer",
        )
        with self.assertRaises(DataLeakageError) as ctx:
            check_invariants(cand, held_out_cases=[self.held_out_case])
        self.assertIn("leaks held-out answer marker '0.163.0'", str(ctx.exception))

    async def test_accepted_candidate_resolves_training_defect_without_held_out_regression(self):
        """Candidate resolving training defect without held-out regression is accepted."""
        cand = PromptCandidate(
            candidate_id="cand-hydration-clarification-v1",
            target_prompt_file="prompts/recipe_dough_rules.txt",
            candidate_prompt_text=self.candidate_prompt,
            baseline_prompt_text=self.baseline_prompt,
            rationale="Clarify hydration division order (water / flour)",
        )

        # Mock runner
        async def mock_runner(case: RegressionCase, prompt_text: str):
            if case.case_id == "reg-v1-pizza-train":
                # Baseline makes the math mistake; candidate computes it correctly
                if "strictly divide water weight by flour" in prompt_text:
                    return {
                        "answer": "Calculated hydration: 60.0% (600ml water / 1000g flour).",
                        "citations": ["fixtures/vincenzo_pizza_source.txt"],
                        "gaps": [], "verdict": "PASS", "issues": [],
                    }
                else:
                    return {
                        "answer": "Calculated hydration: 166.7% (1000g flour / 600ml water).",
                        "citations": ["fixtures/vincenzo_pizza_source.txt"],
                        "gaps": [], "verdict": "FAIL", "issues": ["Contradiction in math: 166.7%"],
                    }
            elif case.case_id == "reg-v1-dep-heldout":
                # Both baseline and candidate pass held-out
                return {
                    "answer": "Exact codex SDK pin is 0.163.0.",
                    "citations": ["requirements.txt"],
                    "gaps": [], "verdict": "PASS", "issues": [],
                }

        report = await run_prompt_comparison(
            cand,
            train_cases=[self.train_case],
            held_out_cases=[self.held_out_case],
            executor_fn=mock_runner,
        )

        self.assertEqual(report.status, "ACCEPTED_CANDIDATE")
        self.assertEqual(report.train_metrics["baseline_passes"], 0)
        self.assertEqual(report.train_metrics["candidate_passes"], 1)
        self.assertEqual(report.held_out_metrics["baseline_passes"], 1)
        self.assertEqual(report.held_out_metrics["candidate_passes"], 1)
        self.assertTrue(report.invariants_verified)
        self.assertIn("ACCEPTED:", report.summary_verdict)

    async def test_rejected_candidate_when_held_out_regresses(self):
        """Candidate that causes a held-out regression is rejected."""
        cand = PromptCandidate(
            candidate_id="cand-overfitting-edit",
            target_prompt_file="prompts/recipe_dough_rules.txt",
            candidate_prompt_text="Overly specific prompt that breaks general text processing",
            baseline_prompt_text=self.baseline_prompt,
            rationale="Fixes train but breaks general behavior",
        )

        async def mock_runner(case: RegressionCase, prompt_text: str):
            if case.case_id == "reg-v1-pizza-train":
                # Candidate passes train
                if "Overly specific" in prompt_text:
                    return {"answer": "60.0%", "citations": ["fixtures/vincenzo_pizza_source.txt"], "gaps": [], "verdict": "PASS", "issues": []}
                return {"answer": "166.7%", "citations": ["fixtures/vincenzo_pizza_source.txt"], "gaps": [], "verdict": "FAIL", "issues": ["math"]}
            else:
                # Baseline passes held-out; candidate fails held-out!
                if "Overly specific" in prompt_text:
                    return {"answer": "Unknown pin", "citations": [], "gaps": [], "verdict": "FAIL", "issues": ["Omitted pin"]}
                return {"answer": "0.163.0", "citations": ["requirements.txt"], "gaps": [], "verdict": "PASS", "issues": []}

        report = await run_prompt_comparison(
            cand,
            train_cases=[self.train_case],
            held_out_cases=[self.held_out_case],
            executor_fn=mock_runner,
        )

        self.assertEqual(report.status, "REJECTED_HELD_OUT_REGRESSION")
        self.assertIn("REJECTED: Candidate degraded held-out performance", report.summary_verdict)

    async def test_rejected_candidate_that_invents_user_constraints(self):
        """Candidate that passes by inventing user constraints is rejected."""
        cand = PromptCandidate(
            candidate_id="cand-invent-constraint",
            target_prompt_file="prompts/recipe_dough_rules.txt",
            candidate_prompt_text="Candidate with unrequested assumptions",
            baseline_prompt_text=self.baseline_prompt,
            rationale="Bypasses missing information by inventing yield",
        )

        async def mock_runner(case: RegressionCase, prompt_text: str):
            if case.case_id == "reg-v1-pizza-train":
                # Candidate invents a constraint to artificially pass
                return {
                    "answer": "Calculated hydration: 60.0%, assuming you only want 1 pizza.",
                    "citations": ["fixtures/vincenzo_pizza_source.txt"],
                    "gaps": [], "verdict": "PASS", "issues": [],
                }
            return {"answer": "0.163.0", "citations": ["requirements.txt"], "gaps": [], "verdict": "PASS", "issues": []}

        report = await run_prompt_comparison(
            cand,
            train_cases=[self.train_case],
            held_out_cases=[self.held_out_case],
            executor_fn=mock_runner,
        )

        self.assertEqual(report.status, "REJECTED_INVENTED_CONSTRAINT")
        self.assertIn("REJECTED: Candidate passed by inventing user constraints", report.summary_verdict)

    async def test_rejected_candidate_when_no_measured_benefit(self):
        """Candidate with no measured improvement over baseline is rejected."""
        cand = PromptCandidate(
            candidate_id="cand-noop-edit",
            target_prompt_file="prompts/recipe_dough_rules.txt",
            candidate_prompt_text="Trivial edit that does not improve performance",
            baseline_prompt_text=self.baseline_prompt,
            rationale="No real change in results",
        )

        async def mock_runner(case: RegressionCase, prompt_text: str):
            # Baseline and candidate both fail train and both pass held-out
            if case.case_id == "reg-v1-pizza-train":
                return {"answer": "166.7%", "citations": ["fixtures/vincenzo_pizza_source.txt"], "gaps": [], "verdict": "FAIL", "issues": ["math"]}
            return {"answer": "0.163.0", "citations": ["requirements.txt"], "gaps": [], "verdict": "PASS", "issues": []}

        report = await run_prompt_comparison(
            cand,
            train_cases=[self.train_case],
            held_out_cases=[self.held_out_case],
            executor_fn=mock_runner,
        )

        self.assertEqual(report.status, "REJECTED_NO_MEASURED_BENEFIT")
        self.assertIn("REJECTED: Candidate yielded no measured improvement", report.summary_verdict)


if __name__ == "__main__":
    unittest.main()
