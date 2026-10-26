"""Tests for GEPA vs. manual edit evaluation and workload optionality (P3.6)."""
from pathlib import Path
import json
import sys
import tempfile
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from candidate_scoring import (
    AdoptionThresholds,
    CandidateScoreVector,
    IndependentReviewResult,
    IndependentSourceReviewer,
    SelectionRecord,
)
from gepa_evaluation import (
    CandidateProfile,
    GepaComparisonReport,
    audit_workload_optionality,
    evaluate_gepa_vs_manual,
)
from manifest_activation import ManifestActivationManager
from regression_suite import DataLeakageError, RegressionCase


def make_clean_review(supported: bool = True) -> IndependentReviewResult:
    return IndependentReviewResult(
        supported=supported,
        unsupported_claims=[] if supported else ["Temperature 250 C not in evidence"],
        omissions=[] if supported else ["Missing dough rest time"],
        conflicts_retained=True,
        audit_trace=["Audit PASS"] if supported else ["Audit FAIL"],
    )


def test_reject_gepa_when_no_benefit_over_manual_edit():
    base = CandidateProfile(
        candidate_id="base",
        candidate_type="baseline",
        content="Base prompt",
        description="Base prompt",
        train_score=CandidateScoreVector(defect_resolutions=0, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    # Manual edit resolves 1 training defect cleanly
    manual = CandidateProfile(
        candidate_id="manual-edit-v1",
        candidate_type="manual_edit",
        content="Manual prompt with explicit ratio extraction",
        description="Manual prompt edit",
        train_score=CandidateScoreVector(defect_resolutions=1, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    # GEPA candidate also resolves 1 training defect, but uses 12 calls (more expensive, zero additional gain)
    gepa = CandidateProfile(
        candidate_id="gepa-mutant-1",
        candidate_type="gepa_mutation",
        content="GEPA mutated prompt with reflective additions",
        description="GEPA reflective prompt mutation",
        train_score=CandidateScoreVector(defect_resolutions=1, usage_calls=12),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=12),
        independent_review=make_clean_review(True),
    )

    report = evaluate_gepa_vs_manual(
        manifest_target="prompts/TASK_REPAIR.txt",
        baseline=base,
        manual_cand=manual,
        gepa_cand=gepa,
    )

    assert report.decision == "REJECT_GEPA_IN_FAVOR_OF_MANUAL"
    assert report.preferred_candidate_id == "manual-edit-v1"
    assert "GEPA did not demonstrate benefit over manual edit" in " ".join(report.decision_rationale)


def test_reject_gepa_on_held_out_regression_overfitting():
    base = CandidateProfile(
        candidate_id="base",
        candidate_type="baseline",
        content="Base prompt",
        description="Base prompt",
        train_score=CandidateScoreVector(defect_resolutions=0, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    manual = CandidateProfile(
        candidate_id="manual-v1",
        candidate_type="manual_edit",
        content="Manual prompt",
        description="Manual edit",
        train_score=CandidateScoreVector(defect_resolutions=1, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    # GEPA overfits: resolves 2 training defects, but introduces 1 unsupported claim on held-out data
    gepa = CandidateProfile(
        candidate_id="gepa-overfit",
        candidate_type="gepa_mutation",
        content="Overfitted GEPA prompt",
        description="GEPA mutation",
        train_score=CandidateScoreVector(defect_resolutions=2, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=1, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    report = evaluate_gepa_vs_manual(
        manifest_target="prompts/TASK_REPAIR.txt",
        baseline=base,
        manual_cand=manual,
        gepa_cand=gepa,
    )

    assert report.decision == "REJECT_GEPA_IN_FAVOR_OF_MANUAL"
    assert report.preferred_candidate_id == "manual-v1"
    assert any("held-out unsupported claims" in r for r in report.decision_rationale)


def test_gepa_disqualified_on_held_out_leakage():
    held_out = [
        RegressionCase(
            case_id="case-held-out-pizza",
            version=1,
            packet_id="pkt-1",
            original_intent="Bake pizza",
            goal="Bake pizza",
            topic="pizza",
            source_family="king_arthur",
            failure_lineage={},
            split="held_out",
            split_family="held_out_pizza",
            bound_sources=[{"id": "s1", "locator": "tests/fixtures/king_arthur_pizza_source.txt"}],
            verification_spec={"expected_output": "Preheated stone at 500 F for 8 to 10 minutes"},
        )
    ]

    base = CandidateProfile(
        candidate_id="base",
        candidate_type="baseline",
        content="Base prompt",
        description="Base prompt",
        train_score=CandidateScoreVector(defect_resolutions=0, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    manual = CandidateProfile(
        candidate_id="manual-clean",
        candidate_type="manual_edit",
        content="Manual clean prompt",
        description="Manual edit",
        train_score=CandidateScoreVector(defect_resolutions=1, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    # GEPA candidate leaked the held-out expected output
    gepa_leaked = CandidateProfile(
        candidate_id="gepa-leaked",
        candidate_type="gepa_mutation",
        content="Always verify preheated stone at 500 F for 8 to 10 minutes from source",
        description="Leaked prompt",
        train_score=CandidateScoreVector(defect_resolutions=2, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    report = evaluate_gepa_vs_manual(
        manifest_target="prompts/TASK_REPAIR.txt",
        baseline=base,
        manual_cand=manual,
        gepa_cand=gepa_leaked,
        held_out_cases=held_out,
    )

    assert report.held_out_leakage["gepa_leaked"] is True
    assert report.decision == "REJECT_GEPA_IN_FAVOR_OF_MANUAL"
    assert report.preferred_candidate_id == "manual-clean"
    assert any("held-out test data" in r for r in report.decision_rationale)


def test_adopt_gepa_when_it_demonstrates_genuine_benefit():
    base = CandidateProfile(
        candidate_id="base",
        candidate_type="baseline",
        content="Base prompt",
        description="Base prompt",
        train_score=CandidateScoreVector(defect_resolutions=0, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    manual = CandidateProfile(
        candidate_id="manual-v1",
        candidate_type="manual_edit",
        content="Manual prompt",
        description="Manual edit",
        train_score=CandidateScoreVector(defect_resolutions=1, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    # GEPA resolves 2 training defects (strictly superior to manual's 1), with 0 held-out regressions and equal usage
    gepa_superior = CandidateProfile(
        candidate_id="gepa-superior",
        candidate_type="gepa_mutation",
        content="GEPA optimized instructions with superior generalization",
        description="GEPA reflective prompt mutation",
        train_score=CandidateScoreVector(defect_resolutions=2, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    report = evaluate_gepa_vs_manual(
        manifest_target="prompts/TASK_REPAIR.txt",
        baseline=base,
        manual_cand=manual,
        gepa_cand=gepa_superior,
    )

    assert report.decision == "ADOPT_GEPA_OVER_MANUAL"
    assert report.preferred_candidate_id == "gepa-superior"
    assert any("measured benefit over manual edit" in r for r in report.decision_rationale)


def test_reject_both_when_both_fail():
    base = CandidateProfile(
        candidate_id="base",
        candidate_type="baseline",
        content="Base prompt",
        description="Base prompt",
        train_score=CandidateScoreVector(defect_resolutions=0, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    manual_bad = CandidateProfile(
        candidate_id="manual-bad",
        candidate_type="manual_edit",
        content="Manual prompt",
        description="Manual edit",
        train_score=CandidateScoreVector(defect_resolutions=0, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=1, usage_calls=10),
        independent_review=make_clean_review(False),
    )

    gepa_bad = CandidateProfile(
        candidate_id="gepa-bad",
        candidate_type="gepa_mutation",
        content="GEPA prompt",
        description="GEPA mutation",
        train_score=CandidateScoreVector(defect_resolutions=0, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=2, usage_calls=10),
        independent_review=make_clean_review(False),
    )

    report = evaluate_gepa_vs_manual(
        manifest_target="prompts/TASK_REPAIR.txt",
        baseline=base,
        manual_cand=manual_bad,
        gepa_cand=gepa_bad,
    )

    assert report.decision == "REJECT_BOTH_RETAIN_BASELINE"
    assert report.preferred_candidate_id == "base"


def test_workload_optionality_audit():
    audit = audit_workload_optionality()
    assert audit["optionality_verified"] is True
    assert audit["rlm_is_optional"] is True
    assert audit["jev_is_optional"] is True
    assert audit["rlm_default"] == "native"


def test_integration_gepa_rejection_activates_manual_edit(tmp_path):
    target_prompt = tmp_path / "TASK_REPAIR.txt"
    base_text = "ORIGINAL BASE PROMPT"
    target_prompt.write_text(base_text, encoding="utf-8")

    manager = ManifestActivationManager(workspace=tmp_path)

    base = CandidateProfile(
        candidate_id="base",
        candidate_type="baseline",
        content=base_text,
        description="Base",
        train_score=CandidateScoreVector(defect_resolutions=0, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    manual_text = "MANUAL HARDENED PROMPT"
    manual = CandidateProfile(
        candidate_id="manual-v1",
        candidate_type="manual_edit",
        content=manual_text,
        description="Manual edit",
        train_score=CandidateScoreVector(defect_resolutions=1, usage_calls=10),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=10),
        independent_review=make_clean_review(True),
    )

    gepa_text = "GEPA PROMPT WITH NO BENEFIT"
    gepa = CandidateProfile(
        candidate_id="gepa-v1",
        candidate_type="gepa_mutation",
        content=gepa_text,
        description="GEPA mutation",
        train_score=CandidateScoreVector(defect_resolutions=1, usage_calls=14),
        held_out_score=CandidateScoreVector(unsupported_claims=0, usage_calls=14),
        independent_review=make_clean_review(True),
    )

    # Run competitive evaluation
    report = evaluate_gepa_vs_manual(
        manifest_target=str(target_prompt),
        baseline=base,
        manual_cand=manual,
        gepa_cand=gepa,
    )
    assert report.decision == "REJECT_GEPA_IN_FAVOR_OF_MANUAL"

    # Create P3.4 selection record for preferred candidate (manual)
    sel = SelectionRecord(
        selection_id="sel-manual-v1",
        candidate_id=report.preferred_candidate_id,
        manifest_target=str(target_prompt),
        decision="ADOPT",
        passed_all_thresholds=True,
        threshold_checks={"defect_reduction": {"passed": True}},
        reasons=report.decision_rationale,
        baseline_scores={"train": base.train_score.to_dict(), "held_out": base.held_out_score.to_dict()},
        candidate_scores={"train": manual.train_score.to_dict(), "held_out": manual.held_out_score.to_dict()},
        independent_review_summary=manual.independent_review.to_dict(),
        reviewer="supervisor",
        review_note="GEPA evaluation selected manual edit over GEPA",
    )

    # Process activation via P3.5 manager
    changed, act_record = manager.process_candidate(target_prompt, manual_text, sel)
    assert changed is True
    assert act_record.action == "ACTIVATE"
    assert target_prompt.read_text(encoding="utf-8") == manual_text

    # GEPA content was NEVER written to disk
    assert gepa_text not in target_prompt.read_text(encoding="utf-8")
