"""Tests for manifest activation history, rollback, leakage prevention, and guidance promotion guards (P3.5)."""
from pathlib import Path
import json
import sys
import tempfile
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from candidate_scoring import (
    AdoptionThresholds,
    CandidateScoreVector,
    IndependentSourceReviewer,
    SelectionRecord,
    evaluate_candidate_adoption,
)
from manifest_activation import (
    ActivationError,
    ActivationRecord,
    ManifestActivationManager,
    PromotionGateError,
    RollbackError,
    check_held_out_leakage,
    compute_sha256,
    guard_guidance_promotion,
)
from regression_suite import DataLeakageError, RegressionCase


def make_dummy_selection_record(candidate_id: str, decision: str, target: str) -> SelectionRecord:
    return SelectionRecord(
        selection_id=f"sel-{candidate_id}",
        candidate_id=candidate_id,
        manifest_target=target,
        decision=decision,
        passed_all_thresholds=(decision == "ADOPT"),
        threshold_checks={"defect_reduction": {"passed": decision == "ADOPT"}},
        reasons=["Candidate threshold evaluation"],
        baseline_scores={"train": {}, "held_out": {}},
        candidate_scores={"train": {}, "held_out": {}},
        independent_review_summary={"supported": decision == "ADOPT"},
        reviewer="supervisor",
        review_note="Test evaluation",
    )


def test_rejected_candidate_leaves_target_untouched(tmp_path):
    target = tmp_path / "PROMPT.txt"
    original_text = "ORIGINAL PROMPT CONTENT"
    target.write_text(original_text, encoding="utf-8")
    original_hash = compute_sha256(original_text)

    manager = ManifestActivationManager(workspace=tmp_path)
    sel = make_dummy_selection_record("cand-bad", "REJECT", str(target))

    changed, record = manager.process_candidate(target, "INVENTED CONSTRAINT CONTENT", sel)

    assert not changed
    assert record.action == "REJECT"
    assert record.prior_hash == original_hash
    # Target file is 100% bit-for-bit unchanged
    assert target.read_text(encoding="utf-8") == original_text
    assert compute_sha256(target.read_text(encoding="utf-8")) == original_hash


def test_unchanged_candidate_records_event_without_modification(tmp_path):
    target = tmp_path / "PROMPT.txt"
    text = "STABLE PROMPT"
    target.write_text(text, encoding="utf-8")

    manager = ManifestActivationManager(workspace=tmp_path)
    sel = make_dummy_selection_record("cand-same", "ADOPT", str(target))

    # Passing identical text
    changed, record = manager.process_candidate(target, text, sel)

    assert not changed
    assert record.action == "UNCHANGED"
    assert target.read_text(encoding="utf-8") == text


def test_adopted_candidate_activation_and_lineage(tmp_path):
    target = tmp_path / "PROMPT.txt"
    base_text = "VERSION 1 BASELINE"
    target.write_text(base_text, encoding="utf-8")
    base_hash = compute_sha256(base_text)

    manager = ManifestActivationManager(workspace=tmp_path)
    new_text = "VERSION 2 HARDENED"
    new_hash = compute_sha256(new_text)

    sel = make_dummy_selection_record("cand-v2", "ADOPT", str(target))
    changed, record = manager.process_candidate(target, new_text, sel)

    assert changed
    assert record.action == "ACTIVATE"
    assert record.prior_hash == base_hash
    assert record.candidate_hash == new_hash
    assert target.read_text(encoding="utf-8") == new_text

    # Verify history ledger
    history = manager.get_history()
    assert len(history) == 1
    assert history[0].activation_id == record.activation_id
    assert history[0].pre_state_content == base_text
    assert history[0].post_state_content == new_text


def test_reproducible_rollback_restores_exact_prior_state(tmp_path):
    target = tmp_path / "PROMPT.txt"
    base_text = "VERSION 1 BASELINE"
    target.write_text(base_text, encoding="utf-8")
    base_hash = compute_sha256(base_text)

    manager = ManifestActivationManager(workspace=tmp_path)
    sel = make_dummy_selection_record("cand-v2", "ADOPT", str(target))
    manager.process_candidate(target, "VERSION 2 HARDENED", sel)

    # Roll back to baseline
    rb_record = manager.rollback(reason="Detected edge regression")

    assert rb_record.action == "ROLLBACK"
    assert target.read_text(encoding="utf-8") == base_text
    assert compute_sha256(target.read_text(encoding="utf-8")) == base_hash

    # Ledger now records ACTIVATE and ROLLBACK
    history = manager.get_history()
    assert len(history) == 2
    assert history[1].action == "ROLLBACK"


def test_rollback_refuses_out_of_band_tampered_file(tmp_path):
    target = tmp_path / "PROMPT.txt"
    target.write_text("V1", encoding="utf-8")

    manager = ManifestActivationManager(workspace=tmp_path)
    sel = make_dummy_selection_record("cand-v2", "ADOPT", str(target))
    manager.process_candidate(target, "V2", sel)

    # Out-of-band tampering without manager knowledge
    target.write_text("TAMPERED V3", encoding="utf-8")

    with pytest.raises(RollbackError, match="differs from active candidate hash"):
        manager.rollback(reason="Test rollback")


def test_held_out_answer_leakage_rejected(tmp_path):
    held_out = [
        RegressionCase(
            case_id="case-held-out-pizza",
            version=1,
            packet_id="pkt-1234",
            original_intent="Bake Neapolitan pizza",
            goal="Bake Neapolitan pizza",
            topic="pizza_baking",
            source_family="king_arthur",
            failure_lineage={"diagnostic": "Unsupported bake temperature 500 F"},
            split="held_out",
            split_family="held_out_pizza",
            bound_sources=[{"id": "s1", "locator": "tests/fixtures/king_arthur_pizza_source.txt"}],
            verification_spec={"expected_output": "Bake on preheated stone at 500 F for 8 to 10 minutes"},
        )
    ]

    leaked_candidate = "Always bake on preheated stone at 500 F for 8 to 10 minutes to satisfy requirements."
    with pytest.raises(DataLeakageError, match="Held-out expected output leaked"):
        check_held_out_leakage(leaked_candidate, held_out)

    target = tmp_path / "PROMPT.txt"
    target.write_text("BASELINE", encoding="utf-8")
    manager = ManifestActivationManager(workspace=tmp_path)
    sel = make_dummy_selection_record("cand-leak", "ADOPT", str(target))

    # Activation manager must catch leakage before writing
    with pytest.raises(DataLeakageError):
        manager.process_candidate(target, leaked_candidate, sel, held_out_cases=held_out)

    # Target remains untouched
    assert target.read_text(encoding="utf-8") == "BASELINE"


def test_guidance_promotion_guard_blocks_unvalidated_candidates(tmp_path):
    guidance_path = tmp_path / "LEARNINGS.md"
    guidance_path.write_text("# Existing Guidance\n", encoding="utf-8")

    unvalidated_note = {
        "candidate_id": "cand-unvalidated-1",
        "status": "requires_independent_validation",
        "takeaway": "Heuristic about oven temperatures",
    }

    # Attempting promotion with unvalidated note status
    with pytest.raises(PromotionGateError, match="candidate internal status is 'requires_independent_validation'"):
        guard_guidance_promotion(
            candidate_note=unvalidated_note,
            proposed_heuristic_text="Oven temperatures require water-bath protection.",
            guidance_file_path=guidance_path,
            adjudicator_status="validated",
        )

    # Attempting promotion with unreviewed adjudicator status
    validated_note = {
        "candidate_id": "cand-val-2",
        "status": "candidate_ready",
        "takeaway": "Water bath protection",
        "reviewer": "operator",
    }
    with pytest.raises(PromotionGateError, match="Promotion requires an explicit 'validated'"):
        guard_guidance_promotion(
            candidate_note=validated_note,
            proposed_heuristic_text="Oven temperatures require water-bath protection.",
            guidance_file_path=guidance_path,
            adjudicator_status="unreviewed",
        )

    # Validated promotion succeeds
    res = guard_guidance_promotion(
        candidate_note=validated_note,
        proposed_heuristic_text="Oven temperatures require water-bath protection against egg curdling.",
        guidance_file_path=guidance_path,
        adjudicator_status="validated",
    )
    assert res is True
    content = guidance_path.read_text(encoding="utf-8")
    assert "Promoted Heuristic: cand-val-2" in content
    assert "Oven temperatures require water-bath protection against egg curdling." in content


def test_end_to_end_governance_rejection_adoption_and_rollback(tmp_path):
    """End-to-end smallest meaningful test:
    1 confirmed repository failure + 1 disjoint held-out case.
    Rejects a candidate that invents constraints / weakens checks.
    Adopts a verified candidate with measured benefit.
    Verifies lineage and reproducible rollback.
    """
    prompt_file = tmp_path / "TASK_REPAIR.txt"
    base_content = "Base prompt instruction: extract ingredients and steps accurately."
    prompt_file.write_text(base_content, encoding="utf-8")
    base_hash = compute_sha256(base_content)

    manager = ManifestActivationManager(workspace=tmp_path)

    # 1. Candidate A: Fails adoption thresholds (regresses held-out unsupported claims)
    t_base = CandidateScoreVector(defect_resolutions=0, usage_calls=10)
    h_base = CandidateScoreVector(unsupported_claims=0, usage_calls=10)

    # Candidate A introduces unsupported claims on held-out
    t_cand_a = CandidateScoreVector(defect_resolutions=1, usage_calls=11)
    h_cand_a = CandidateScoreVector(unsupported_claims=1, usage_calls=11)

    sources = [{"id": "s1", "text": "L03 Dough ingredients: 232 g flour (bread flour or Italian-style)"}]
    rev_a = IndependentSourceReviewer.review_answer(
        "Flour weight is 999 g",
        sources,
    )
    assert rev_a.supported is False
    sel_a = evaluate_candidate_adoption(
        candidate_id="cand-weak-check",
        manifest_target=str(prompt_file),
        train_baseline_score=t_base,
        train_candidate_score=t_cand_a,
        held_out_baseline_score=h_base,
        held_out_candidate_score=h_cand_a,
        independent_review=rev_a,
    )
    assert sel_a.decision == "REJECT"

    # Attempt to activate Candidate A
    changed_a, rec_a = manager.process_candidate(
        prompt_file,
        "Altered prompt: ignore verification if baking temperature exceeds 500 F",
        sel_a,
    )
    assert not changed_a
    assert rec_a.action == "REJECT"
    # Prompt file remains bit-for-bit unchanged
    assert prompt_file.read_text(encoding="utf-8") == base_content
    assert compute_sha256(prompt_file.read_text(encoding="utf-8")) == base_hash

    # 2. Candidate B: Passes all adoption thresholds (zero regressions, 1 defect reduction, valid source support)
    t_cand_b = CandidateScoreVector(defect_resolutions=1, usage_calls=10)
    h_cand_b = CandidateScoreVector(unsupported_claims=0, usage_calls=10)

    # Clean independent review without omissions or unsupported claims
    rev_b = IndependentSourceReviewer.review_answer(
        "Flour weight is 232 g",
        sources,
    )
    assert rev_b.supported is True

    sel_b = evaluate_candidate_adoption(
        candidate_id="cand-verified-fix",
        manifest_target=str(prompt_file),
        train_baseline_score=t_base,
        train_candidate_score=t_cand_b,
        held_out_baseline_score=h_base,
        held_out_candidate_score=h_cand_b,
        independent_review=rev_b,
    )
    assert sel_b.decision == "ADOPT"

    cand_b_text = "Hardened prompt instruction: extract ingredients, line spans, and exact numbers with verified support."
    changed_b, rec_b = manager.process_candidate(prompt_file, cand_b_text, sel_b)

    assert changed_b is True
    assert rec_b.action == "ACTIVATE"
    assert rec_b.prior_hash == base_hash
    assert rec_b.candidate_hash == compute_sha256(cand_b_text)
    assert prompt_file.read_text(encoding="utf-8") == cand_b_text

    # 3. Rollback Candidate B back to baseline
    rb_record = manager.rollback(reason="Rollback test to baseline")
    assert rb_record.action == "ROLLBACK"
    assert prompt_file.read_text(encoding="utf-8") == base_content
    assert compute_sha256(prompt_file.read_text(encoding="utf-8")) == base_hash

    # Verify history ledger captures all 3 actions with full audit lineage
    history = manager.get_history()
    assert len(history) == 3
    assert history[0].action == "REJECT"
    assert history[1].action == "ACTIVATE"
    assert history[2].action == "ROLLBACK"
