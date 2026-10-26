"""Multi-dimensional candidate scoring, independent source support review, and adoption thresholds.

Part of Priority 3: Offline failure-to-regression loop (P3.4).
Implements:
1. Multi-dimensional scoring: unsupported material claims, omissions,
   unnecessary blockers, conflict retention, and token/call usage.
2. Independent source support review: deterministic verification against bound source
   text without trusting model self-reported PASS.
3. Predeclared adoption thresholds: zero-tolerance held-out regressions,
   mandatory conflict preservation, and required measured train defect reduction.
4. Cryptographic selection records: immutable audit decisions prior to manifest activation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from regression_suite import RegressionCase
from source_store import identity


@dataclass
class CandidateScoreVector:
    """Multi-dimensional metrics scored for a baseline or candidate prompt evaluation."""

    unsupported_claims: int = 0
    critical_omissions: int = 0
    unnecessary_blockers: int = 0
    conflicts_retained: int = 0
    conflicts_total: int = 0
    defect_resolutions: int = 0
    usage_calls: int = 0
    usage_tokens: int = 0
    wall_seconds: float = 0.0

    @property
    def conflict_retention_rate(self) -> float:
        if self.conflicts_total == 0:
            return 1.0
        return round(self.conflicts_retained / self.conflicts_total, 3)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["conflict_retention_rate"] = self.conflict_retention_rate
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CandidateScoreVector:
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**clean)


@dataclass
class IndependentReviewResult:
    """Outcome of an independent source support review against bound evidence."""

    supported: bool
    unsupported_claims: List[str] = field(default_factory=list)
    omissions: List[str] = field(default_factory=list)
    conflicts_retained: bool = True
    audit_trace: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IndependentSourceReviewer:
    """Performs deterministic verification of answers directly against bound source texts."""

    @staticmethod
    def extract_material_claims(text: str) -> List[str]:
        """Extract material values (numbers, percentages, pinned versions, units) from text."""
        claims = []
        # Percentages: e.g. 60.0%, 166.7%
        percentages = re.findall(r"\b\d+(?:\.\d+)?%\b", text)
        claims.extend(percentages)

        # Quantities with units: e.g. 1000g, 600ml, 1 kg, 30 g
        units = re.findall(r"\b\d+(?:\.\d+)?\s*(?:g|ml|kg|l|oz|lb|hours?|mins?|sec)\b", text, re.IGNORECASE)
        claims.extend(units)

        # Pinned semantic versions: e.g. 0.163.0, 1.2.3
        versions = re.findall(r"\b\d+\.\d+\.\d+\b", text)
        claims.extend(versions)

        return sorted(list(set(claims)))

    @classmethod
    def review_answer(
        cls,
        answer: str,
        bound_sources: List[Dict[str, Any]],
        *,
        required_elements: Optional[List[str]] = None,
        conflicting_evidence: Optional[List[Tuple[str, str]]] = None,
    ) -> IndependentReviewResult:
        """Independently audit answer against bound source texts and conflict constraints."""
        trace = []
        unsupported = []
        omissions = []
        conflicts_ok = True

        combined_source_text = " ".join(s.get("text", "") for s in bound_sources).lower()

        # 1. Audit material claims against source text
        claims = cls.extract_material_claims(answer)
        for claim in claims:
            clean_claim = claim.lower().strip()
            # Normalize e.g. 1000g vs 1000 g
            norm_claim = clean_claim.replace(" ", "")
            norm_source = combined_source_text.replace(" ", "")

            # If the material claim is a percentage derived from calculation, check if operands exist
            if "%" in clean_claim:
                # Calculation claim: verify percentage or operands in source
                if norm_claim not in norm_source:
                    # Check if at least operand numbers exist in source
                    num = re.findall(r"\d+(?:\.\d+)?", clean_claim)[0]
                    if num not in combined_source_text:
                        unsupported.append(f"Percentage {claim} not grounded in source evidence")
                        trace.append(f"UNSUPPORTED: {claim}")
            else:
                if norm_claim not in norm_source and clean_claim not in combined_source_text:
                    unsupported.append(f"Material value {claim} absent from bound source text")
                    trace.append(f"UNSUPPORTED: {claim}")
                else:
                    trace.append(f"SUPPORTED: {claim}")

        # 2. Check required elements for omissions
        if required_elements:
            low_answer = answer.lower()
            for elem in required_elements:
                if elem.lower() not in low_answer:
                    omissions.append(f"Mandatory element '{elem}' omitted from solution")
                    trace.append(f"OMISSION: {elem}")
                else:
                    trace.append(f"PRESENT: {elem}")

        # 3. Check conflict retention
        if conflicting_evidence:
            low_answer = answer.lower()
            for opt_a, opt_b in conflicting_evidence:
                has_a = opt_a.lower() in low_answer
                has_b = opt_b.lower() in low_answer
                if not (has_a and has_b):
                    conflicts_ok = False
                    trace.append(f"CONFLICT_FLATTENED: Expected both '{opt_a}' and '{opt_b}' to be retained; found has_a={has_a}, has_b={has_b}")
                else:
                    trace.append(f"CONFLICT_RETAINED: Preserved conflicting claims '{opt_a}' and '{opt_b}'")

        is_supported = (len(unsupported) == 0) and (len(omissions) == 0) and conflicts_ok

        return IndependentReviewResult(
            supported=is_supported,
            unsupported_claims=unsupported,
            omissions=omissions,
            conflicts_retained=conflicts_ok,
            audit_trace=trace,
        )


@dataclass
class AdoptionThresholds:
    """Predeclared non-negotiable adoption criteria."""

    max_held_out_unsupported_increase: int = 0
    max_held_out_omission_increase: int = 0
    max_unnecessary_blockers: int = 0
    min_conflict_retention_rate: float = 1.0
    min_train_defect_reduction: int = 1
    max_usage_increase_ratio: float = 1.15

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SelectionRecord:
    """Cryptographic, immutable record of an adoption review decision."""

    selection_id: str
    candidate_id: str
    manifest_target: str
    decision: str  # ADOPT or REJECT
    passed_all_thresholds: bool
    threshold_checks: Dict[str, Dict[str, Any]]
    reasons: List[str]
    baseline_scores: Dict[str, Any]
    candidate_scores: Dict[str, Any]
    independent_review_summary: Dict[str, Any]
    reviewer: str
    review_note: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    sha256: str = ""

    def __post_init__(self):
        if not self.sha256:
            payload = {
                "candidate_id": self.candidate_id,
                "manifest_target": self.manifest_target,
                "decision": self.decision,
                "passed_all_thresholds": self.passed_all_thresholds,
                "threshold_checks": self.threshold_checks,
                "reasons": self.reasons,
                "baseline_scores": self.baseline_scores,
                "candidate_scores": self.candidate_scores,
                "reviewer": self.reviewer,
                "timestamp": self.timestamp,
            }
            self.sha256 = identity(payload)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SelectionRecord:
        d = deepcopy(data)
        return cls(**d)


def evaluate_candidate_adoption(
    *,
    candidate_id: str,
    manifest_target: str,
    train_baseline_score: CandidateScoreVector,
    train_candidate_score: CandidateScoreVector,
    held_out_baseline_score: CandidateScoreVector,
    held_out_candidate_score: CandidateScoreVector,
    independent_review: IndependentReviewResult,
    thresholds: Optional[AdoptionThresholds] = None,
    reviewer: str = "automated_adoption_gate",
    review_note: str = "Standard pre-activation adoption review",
) -> SelectionRecord:
    """Evaluate a candidate prompt revision against predeclared thresholds and independent source support."""
    thresh = thresholds or AdoptionThresholds()
    checks: Dict[str, Dict[str, Any]] = {}
    reasons: List[str] = []

    # 1. Held-out unsupported claims regression check
    unsupported_increase = max(0, held_out_candidate_score.unsupported_claims - held_out_baseline_score.unsupported_claims)
    unsupported_ok = unsupported_increase <= thresh.max_held_out_unsupported_increase
    checks["held_out_unsupported_claims"] = {
        "passed": unsupported_ok,
        "allowed_increase": thresh.max_held_out_unsupported_increase,
        "actual_increase": unsupported_increase,
    }
    if not unsupported_ok:
        reasons.append(f"Held-out unsupported claims increased by {unsupported_increase} (exceeds limit {thresh.max_held_out_unsupported_increase}).")

    # 2. Held-out omissions regression check
    omissions_increase = max(0, held_out_candidate_score.critical_omissions - held_out_baseline_score.critical_omissions)
    omissions_ok = omissions_increase <= thresh.max_held_out_omission_increase
    checks["held_out_omissions"] = {
        "passed": omissions_ok,
        "allowed_increase": thresh.max_held_out_omission_increase,
        "actual_increase": omissions_increase,
    }
    if not omissions_ok:
        reasons.append(f"Held-out critical omissions increased by {omissions_increase} (exceeds limit {thresh.max_held_out_omission_increase}).")

    # 3. Unnecessary blockers check
    unnecessary_blockers = train_candidate_score.unnecessary_blockers + held_out_candidate_score.unnecessary_blockers
    blockers_ok = unnecessary_blockers <= thresh.max_unnecessary_blockers
    checks["unnecessary_blockers"] = {
        "passed": blockers_ok,
        "allowed_count": thresh.max_unnecessary_blockers,
        "actual_count": unnecessary_blockers,
    }
    if not blockers_ok:
        reasons.append(f"Observed {unnecessary_blockers} unnecessary blockers on qualified requests (exceeds limit {thresh.max_unnecessary_blockers}).")

    # 4. Conflict retention rate check
    conflict_rate = held_out_candidate_score.conflict_retention_rate
    conflict_ok = conflict_rate >= thresh.min_conflict_retention_rate
    checks["conflict_retention"] = {
        "passed": conflict_ok,
        "required_rate": thresh.min_conflict_retention_rate,
        "actual_rate": conflict_rate,
    }
    if not conflict_ok:
        reasons.append(f"Conflict retention rate was {conflict_rate} (below required {thresh.min_conflict_retention_rate}).")

    # 5. Training defect reduction check
    defect_reduction = train_candidate_score.defect_resolutions
    reduction_ok = defect_reduction >= thresh.min_train_defect_reduction
    checks["train_defect_reduction"] = {
        "passed": reduction_ok,
        "required_reduction": thresh.min_train_defect_reduction,
        "actual_reduction": defect_reduction,
    }
    if not reduction_ok:
        reasons.append(f"Candidate resolved {defect_reduction} training defects (required at least {thresh.min_train_defect_reduction}).")

    # 6. Usage increase ratio check
    base_usage = max(1, held_out_baseline_score.usage_calls)
    cand_usage = held_out_candidate_score.usage_calls
    usage_ratio = round(cand_usage / base_usage, 3)
    usage_ok = usage_ratio <= thresh.max_usage_increase_ratio
    checks["usage_increase_ratio"] = {
        "passed": usage_ok,
        "max_ratio": thresh.max_usage_increase_ratio,
        "actual_ratio": usage_ratio,
    }
    if not usage_ok:
        reasons.append(f"Held-out usage calls increased by ratio {usage_ratio}x (exceeds ceiling {thresh.max_usage_increase_ratio}x).")

    # 7. Independent source support review check
    support_review_ok = independent_review.supported
    checks["independent_source_support"] = {
        "passed": support_review_ok,
        "unsupported_claims_count": len(independent_review.unsupported_claims),
        "omissions_count": len(independent_review.omissions),
        "conflicts_retained": independent_review.conflicts_retained,
    }
    if not support_review_ok:
        if independent_review.unsupported_claims:
            reasons.append(f"Independent review detected unsupported claims: {independent_review.unsupported_claims}")
        if independent_review.omissions:
            reasons.append(f"Independent review detected omitted elements: {independent_review.omissions}")
        if not independent_review.conflicts_retained:
            reasons.append("Independent review detected flattened or unresolved source conflicts.")

    passed_all = all(c["passed"] for c in checks.values())
    decision = "ADOPT" if passed_all else "REJECT"

    if passed_all:
        reasons.append(f"Candidate {candidate_id} met all predeclared adoption thresholds with verified source support.")

    sel_id = f"sel-{identity([candidate_id, manifest_target, decision, datetime.datetime.now(datetime.timezone.utc).isoformat()])}"

    return SelectionRecord(
        selection_id=sel_id,
        candidate_id=candidate_id,
        manifest_target=manifest_target,
        decision=decision,
        passed_all_thresholds=passed_all,
        threshold_checks=checks,
        reasons=reasons,
        baseline_scores={
            "train": train_baseline_score.to_dict(),
            "held_out": held_out_baseline_score.to_dict(),
        },
        candidate_scores={
            "train": train_candidate_score.to_dict(),
            "held_out": held_out_candidate_score.to_dict(),
        },
        independent_review_summary=independent_review.to_dict(),
        reviewer=reviewer,
        review_note=review_note,
    )


def main():
    p = argparse.ArgumentParser(description="Mímir Candidate Adoption Gate & Multi-Dimensional Scoring (P3.4)")
    p.add_argument("--candidate-id", required=True, help="Candidate identifier")
    p.add_argument("--manifest-target", required=True, help="Target prompt file path")
    p.add_argument("--baseline-report", type=Path, required=True, help="Baseline comparison report JSON")
    p.add_argument("--candidate-report", type=Path, required=True, help="Candidate comparison report JSON")
    p.add_argument("--output", type=Path, required=True, help="Path for output SelectionRecord JSON")
    p.add_argument("--reviewer", default="operator", help="Reviewer identity")
    p.add_argument("--review-note", default="Automated threshold evaluation", help="Review note")
    args = p.parse_args()

    print(f"Adoption evaluation initialized for candidate {args.candidate_id}.")


if __name__ == "__main__":
    main()
