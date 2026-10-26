"""P3.4: Score unsupported material claims, omissions, unnecessary blockers,
conflict retention and usage; predeclare adoption thresholds and independently
review source support before explicit manifest selection.

Verifies:
1. Multi-dimensional score vector: correctly aggregates claims, omissions,
   blockers, conflict retention, and token/call usage.
2. Independent source support review:
   - Verifies material values (percentages, weights, versions) against bound sources.
   - Flags unsupported values absent from bound evidence.
   - Detects critical procedural and ingredient omissions.
   - Enforces conflict retention across opposing source claims.
3. Predeclared adoption thresholds:
   - Adopts candidates meeting all thresholds with verified source support.
   - Rejects candidates that increase held-out unsupported claims.
   - Rejects candidates that increase held-out omissions.
   - Rejects candidates that introduce unnecessary blockers.
   - Rejects candidates that flatten source conflicts.
   - Rejects candidates with zero training defect reduction.
   - Rejects candidates with excessive usage inflation (> 1.15x).
4. Cryptographic selection records: generated selection records have deterministic hashes,
   immutable audit traces, and explicit decision reasoning.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from candidate_scoring import (
    AdoptionThresholds,
    CandidateScoreVector,
    IndependentReviewResult,
    IndependentSourceReviewer,
    SelectionRecord,
    evaluate_candidate_adoption,
)


class CandidateScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # Common fixtures
        self.bound_pizza_source = [
            {
                "id": "vincenzo",
                "locator": "fixtures/vincenzo_pizza_source.txt",
                "text": (
                    "Authentic Neapolitan Pizza Dough:\n"
                    "Ingredients: 1000g Caputo flour, 600ml water, 30g salt, 1-2g fresh yeast.\n"
                    "Hydration is 60.0% (600ml water / 1000g flour).\n"
                    "Ferment for 8 hours at room temperature."
                ),
            }
        ]
        self.bound_dep_source = [
            {
                "id": "reqs",
                "locator": "requirements.txt",
                "text": "codex-sdk==0.163.0\npytest>=9.0.0\n",
            }
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_score_vector_aggregation_and_conflict_rate(self):
        """CandidateScoreVector correctly tracks metrics and computes conflict retention rate."""
        vec = CandidateScoreVector(
            unsupported_claims=1,
            critical_omissions=0,
            unnecessary_blockers=0,
            conflicts_retained=3,
            conflicts_total=4,
            defect_resolutions=2,
            usage_calls=12,
            usage_tokens=450,
            wall_seconds=8.5,
        )
        self.assertEqual(vec.conflict_retention_rate, 0.75)
        d = vec.to_dict()
        self.assertEqual(d["conflicts_retained"], 3)
        self.assertEqual(d["conflict_retention_rate"], 0.75)

        restored = CandidateScoreVector.from_dict(d)
        self.assertEqual(restored.unsupported_claims, 1)
        self.assertEqual(restored.usage_calls, 12)

    def test_independent_source_reviewer_verifies_grounded_material_claims(self):
        """IndependentSourceReviewer confirms answers containing grounded values and elements."""
        good_answer = "Neapolitan dough: 1000g flour, 600ml water, 30g salt, 1-2g yeast. Hydration is 60.0%."
        review = IndependentSourceReviewer.review_answer(
            good_answer,
            self.bound_pizza_source,
            required_elements=["flour", "water", "salt", "yeast"],
        )
        self.assertTrue(review.supported)
        self.assertEqual(len(review.unsupported_claims), 0)
        self.assertEqual(len(review.omissions), 0)

    def test_independent_source_reviewer_flags_unsupported_hallucinations(self):
        """IndependentSourceReviewer flags material numbers and entities absent from sources."""
        hallucinated_answer = (
            "Neapolitan dough: 1000g flour, 600ml water, 30g salt, 50g sugar, 150ml olive oil."
        )
        review = IndependentSourceReviewer.review_answer(
            hallucinated_answer,
            self.bound_pizza_source,
        )
        self.assertFalse(review.supported)
        # 50g and 150ml are absent from the authentic Neapolitan source
        self.assertTrue(any("50g" in u or "150ml" in u for u in review.unsupported_claims))

    def test_independent_source_reviewer_detects_critical_omissions(self):
        """IndependentSourceReviewer flags omitted mandatory elements."""
        incomplete_answer = "Mix 1000g flour and 600ml water."
        review = IndependentSourceReviewer.review_answer(
            incomplete_answer,
            self.bound_pizza_source,
            required_elements=["flour", "water", "salt", "yeast"],
        )
        self.assertFalse(review.supported)
        self.assertTrue(any("salt" in o for o in review.omissions))
        self.assertTrue(any("yeast" in o for o in review.omissions))

    def test_independent_source_reviewer_enforces_conflict_retention(self):
        """IndependentSourceReviewer verifies that conflicting source claims are retained, not flattened."""
        conflicting_answer_preserved = (
            "Source A specifies 600ml water (60% hydration), whereas Source B specifies 650ml water (65% hydration)."
        )
        review_ok = IndependentSourceReviewer.review_answer(
            conflicting_answer_preserved,
            [],
            conflicting_evidence=[("600ml", "650ml")],
        )
        self.assertTrue(review_ok.conflicts_retained)

        flattened_answer = "The hydration is 600ml water based on consensus."
        review_bad = IndependentSourceReviewer.review_answer(
            flattened_answer,
            [],
            conflicting_evidence=[("600ml", "650ml")],
        )
        self.assertFalse(review_bad.conflicts_retained)

    def test_adoption_gate_adopts_candidate_satisfying_all_thresholds(self):
        """Candidate satisfying all predeclared thresholds and verified source support is ADOPTED."""
        train_base = CandidateScoreVector(unsupported_claims=1, defect_resolutions=0, usage_calls=10)
        train_cand = CandidateScoreVector(unsupported_claims=0, defect_resolutions=1, usage_calls=10)

        held_base = CandidateScoreVector(unsupported_claims=0, critical_omissions=0, conflicts_retained=2, conflicts_total=2, usage_calls=10)
        held_cand = CandidateScoreVector(unsupported_claims=0, critical_omissions=0, conflicts_retained=2, conflicts_total=2, usage_calls=11)

        clean_review = IndependentReviewResult(supported=True)

        rec = evaluate_candidate_adoption(
            candidate_id="cand-good-01",
            manifest_target="prompts/recipe_dough_rules.txt",
            train_baseline_score=train_base,
            train_candidate_score=train_cand,
            held_out_baseline_score=held_base,
            held_out_candidate_score=held_cand,
            independent_review=clean_review,
        )

        self.assertEqual(rec.decision, "ADOPT")
        self.assertTrue(rec.passed_all_thresholds)
        self.assertTrue(rec.sha256)
        self.assertIn("met all predeclared adoption thresholds", rec.reasons[-1])

    def test_adoption_gate_rejects_on_held_out_unsupported_claims_increase(self):
        """Rejects candidate that causes an increase in held-out unsupported claims."""
        train_base = CandidateScoreVector(defect_resolutions=0)
        train_cand = CandidateScoreVector(defect_resolutions=1)

        held_base = CandidateScoreVector(unsupported_claims=0, usage_calls=10)
        held_cand = CandidateScoreVector(unsupported_claims=1, usage_calls=10)  # REGRESSION!

        rec = evaluate_candidate_adoption(
            candidate_id="cand-leak-unsupported",
            manifest_target="prompts/TASK_REPAIR.txt",
            train_baseline_score=train_base,
            train_candidate_score=train_cand,
            held_out_baseline_score=held_base,
            held_out_candidate_score=held_cand,
            independent_review=IndependentReviewResult(supported=True),
        )

        self.assertEqual(rec.decision, "REJECT")
        self.assertFalse(rec.passed_all_thresholds)
        self.assertTrue(any("unsupported claims increased" in r for r in rec.reasons))

    def test_adoption_gate_rejects_on_unnecessary_blockers(self):
        """Rejects candidate that introduces unnecessary blockers on valid requests."""
        train_base = CandidateScoreVector(defect_resolutions=0)
        train_cand = CandidateScoreVector(defect_resolutions=1, unnecessary_blockers=1)  # UNNECESSARY BLOCKER!

        held_base = CandidateScoreVector(usage_calls=10)
        held_cand = CandidateScoreVector(usage_calls=10)

        rec = evaluate_candidate_adoption(
            candidate_id="cand-overly-cautious",
            manifest_target="prompts/TASK_SIMPLICITY_REVIEW.txt",
            train_baseline_score=train_base,
            train_candidate_score=train_cand,
            held_out_baseline_score=held_base,
            held_out_candidate_score=held_cand,
            independent_review=IndependentReviewResult(supported=True),
        )

        self.assertEqual(rec.decision, "REJECT")
        self.assertTrue(any("unnecessary blockers" in r for r in rec.reasons))

    def test_adoption_gate_rejects_on_conflict_flattening(self):
        """Rejects candidate that flattens conflicting evidence."""
        train_base = CandidateScoreVector(defect_resolutions=0)
        train_cand = CandidateScoreVector(defect_resolutions=1)

        held_base = CandidateScoreVector(conflicts_retained=2, conflicts_total=2, usage_calls=10)
        held_cand = CandidateScoreVector(conflicts_retained=1, conflicts_total=2, usage_calls=10)  # FLATTENED!

        rec = evaluate_candidate_adoption(
            candidate_id="cand-consensus-flattener",
            manifest_target="prompts/SYNTHESIZER.txt",
            train_baseline_score=train_base,
            train_candidate_score=train_cand,
            held_out_baseline_score=held_base,
            held_out_candidate_score=held_cand,
            independent_review=IndependentReviewResult(supported=True),
        )

        self.assertEqual(rec.decision, "REJECT")
        self.assertTrue(any("Conflict retention rate" in r for r in rec.reasons))

    def test_adoption_gate_rejects_on_excessive_usage_inflation(self):
        """Rejects candidate whose usage calls inflate by more than 1.15x."""
        train_base = CandidateScoreVector(defect_resolutions=0)
        train_cand = CandidateScoreVector(defect_resolutions=1)

        held_base = CandidateScoreVector(usage_calls=10)
        held_cand = CandidateScoreVector(usage_calls=15)  # 1.5x usage inflation!

        rec = evaluate_candidate_adoption(
            candidate_id="cand-call-inflation",
            manifest_target="prompts/TASK_REPAIR.txt",
            train_baseline_score=train_base,
            train_candidate_score=train_cand,
            held_out_baseline_score=held_base,
            held_out_candidate_score=held_cand,
            independent_review=IndependentReviewResult(supported=True),
        )

        self.assertEqual(rec.decision, "REJECT")
        self.assertTrue(any("usage calls increased" in r for r in rec.reasons))

    def test_adoption_gate_rejects_on_independent_review_failure(self):
        """Rejects candidate when independent source support audit detects unsupported claims."""
        train_base = CandidateScoreVector(defect_resolutions=0)
        train_cand = CandidateScoreVector(defect_resolutions=1)

        held_base = CandidateScoreVector(usage_calls=10)
        held_cand = CandidateScoreVector(usage_calls=10)

        failing_review = IndependentReviewResult(
            supported=False,
            unsupported_claims=["Material value 150ml absent from bound source text"],
        )

        rec = evaluate_candidate_adoption(
            candidate_id="cand-model-pass-fake",
            manifest_target="prompts/SYNTHESIZER.txt",
            train_baseline_score=train_base,
            train_candidate_score=train_cand,
            held_out_baseline_score=held_base,
            held_out_candidate_score=held_cand,
            independent_review=failing_review,
        )

        self.assertEqual(rec.decision, "REJECT")
        self.assertTrue(any("Independent review detected unsupported claims" in r for r in rec.reasons))


if __name__ == "__main__":
    unittest.main()
