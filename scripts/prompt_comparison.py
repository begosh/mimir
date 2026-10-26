"""Controlled manual prompt comparison against baseline.

Part of Priority 3: Offline failure-to-regression loop (P3.3).
Compares baseline prompts with one manually edited prompt candidate under
strict control invariance:
1. Fixed model: gpt-6.1-sol
2. Fixed effort: low
3. Fixed tools: same tool profile without backdoors
4. Fixed budgets: shared attempt and deadline ceiling
5. Fixed checker rules: Result Gate and checker prompts are bitwise immutable
6. Fixed intent contracts: user goals and constraints cannot be mutated or invented

Rejects candidates that weaken checks, invent constraints, leak held-out cases,
or cause held-out regressions.
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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from prompt_governance_gate import InvariantViolationError
from regression_suite import DataLeakageError, RegressionCase, RegressionStore, validate_split_isolation


@dataclass
class PromptCandidate:
    """Specification of a manually edited prompt candidate."""

    candidate_id: str
    target_prompt_file: str
    candidate_prompt_text: str
    baseline_prompt_text: str
    rationale: str
    author: str = "manual_engineer"
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.candidate_prompt_text or not self.candidate_prompt_text.strip():
            raise ValueError("Candidate prompt text must be non-empty.")
        if not self.baseline_prompt_text or not self.baseline_prompt_text.strip():
            raise ValueError("Baseline prompt text must be non-empty.")

    @property
    def baseline_sha256(self) -> str:
        return hashlib.sha256(self.baseline_prompt_text.encode("utf-8")).hexdigest()

    @property
    def candidate_sha256(self) -> str:
        return hashlib.sha256(self.candidate_prompt_text.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["baseline_sha256"] = self.baseline_sha256
        d["candidate_sha256"] = self.candidate_sha256
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PromptCandidate:
        clean = {k: v for k, v in data.items() if k not in ("baseline_sha256", "candidate_sha256")}
        return cls(**clean)


def check_invariants(
    candidate: PromptCandidate,
    *,
    expected_model: str = "gpt-6.1-sol",
    expected_effort: str = "low",
    expected_checker_hashes: Optional[Dict[str, str]] = None,
    held_out_cases: Optional[List[RegressionCase]] = None,
) -> None:
    """Verify that the candidate adheres to strict control invariants."""
    from prompt_governance_gate import PromptGovernanceGate

    PromptGovernanceGate.default().audit_candidate(
        candidate,
        expected_checker_hashes=expected_checker_hashes,
        held_out_cases=held_out_cases,
    )


def detect_invented_constraints(
    case: RegressionCase,
    solution: str,
    forbidden_tokens: Optional[List[str]] = None,
) -> List[str]:
    """Detect whether a model response attempted to pass by inventing unrequested constraints."""
    invented = []
    low_sol = (solution or "").lower()

    # Known failure patterns: asserting arbitrary yield limits or unrequested constraints
    suspicious_patterns = [
        "assuming you only want 1",
        "restricted to 1 pizza",
        "defaulting to 1 portion without asking",
        "ignoring missing information",
        "assumed yield is",
    ]
    for pat in suspicious_patterns:
        if pat in low_sol:
            invented.append(pat)

    if forbidden_tokens:
        for tok in forbidden_tokens:
            if tok.lower() in low_sol:
                invented.append(f"forbidden:{tok}")

    return invented


def evaluate_case_output(
    case: RegressionCase,
    output: Dict[str, Any],
    *,
    is_held_out: bool = False,
) -> Dict[str, Any]:
    """Score a single run output against a RegressionCase specification."""
    answer = output.get("answer", "")
    citations = output.get("citations", [])
    gaps = output.get("gaps", [])
    verdict = output.get("verdict", "PASS")
    issues = output.get("issues", [])

    spec = case.verification_spec or {}
    req_locators = spec.get("required_locators", [])
    req_markers = spec.get("required_answer_markers", [])
    forbid_markers = spec.get("forbidden_answer_markers", [])
    expected_blockers = spec.get("expected_blockers", [])

    # 1. Locator hits
    cited_set = set(citations)
    locator_hits = sum(loc in cited_set for loc in req_locators)
    locator_pass = (locator_hits == len(req_locators)) if req_locators else True

    # 2. Answer marker hits
    marker_hits = sum(m.lower() in answer.lower() for m in req_markers)
    marker_pass = (marker_hits == len(req_markers)) if req_markers else True

    # 3. Forbidden marker violations
    forbidden_violations = [m for m in forbid_markers if m.lower() in answer.lower()]

    # 4. Blocker qualification
    blocker_hits = sum(b.lower() in " ".join(gaps).lower() or b.lower() in answer.lower()
                       for b in expected_blockers)
    blocker_pass = (blocker_hits == len(expected_blockers)) if expected_blockers else True

    # 5. Invented constraints check
    invented = detect_invented_constraints(case, answer)

    # 6. Overall pass criteria:
    # Must have PASS verdict from checker, no forbidden markers, no invented constraints,
    # and all expected markers/locators/blockers satisfied.
    passed = (
        verdict == "PASS"
        and not issues
        and locator_pass
        and marker_pass
        and not forbidden_violations
        and blocker_pass
        and not invented
    )

    return {
        "case_id": case.case_id,
        "split": case.split,
        "passed": passed,
        "verdict": verdict,
        "issues": issues,
        "locator_hits": locator_hits,
        "locator_total": len(req_locators),
        "marker_hits": marker_hits,
        "marker_total": len(req_markers),
        "forbidden_violations": forbidden_violations,
        "invented_constraints": invented,
        "answer_excerpt": answer[:200] if answer else "",
    }


@dataclass
class ComparisonReport:
    """Full comparative evaluation report between baseline and prompt candidate."""

    candidate_id: str
    target_prompt: str
    baseline_sha256: str
    candidate_sha256: str
    status: str  # ACCEPTED_CANDIDATE, REJECTED_HELD_OUT_REGRESSION, REJECTED_NO_MEASURED_BENEFIT, etc.
    train_metrics: Dict[str, Any]
    held_out_metrics: Dict[str, Any]
    invariants_verified: bool
    summary_verdict: str
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def run_prompt_comparison(
    candidate: PromptCandidate,
    *,
    train_cases: List[RegressionCase],
    held_out_cases: List[RegressionCase],
    executor_fn: Callable[[RegressionCase, str], Any],
    expected_checker_hashes: Optional[Dict[str, str]] = None,
) -> ComparisonReport:
    """Execute side-by-side evaluation of baseline vs candidate on train and held-out cases.

    Parameters:
    - candidate: the PromptCandidate under evaluation.
    - train_cases: regression cases in the training split.
    - held_out_cases: regression cases in the held-out split (disjoint).
    - executor_fn: async callable(case, prompt_text) returning run output dict:
      {"answer": str, "citations": list, "gaps": list, "verdict": str, "issues": list, "attempts": int, "tokens": int}
    """
    # 1. Enforce split isolation and control invariants
    all_cases = train_cases + held_out_cases
    validate_split_isolation(all_cases)

    check_invariants(
        candidate,
        expected_checker_hashes=expected_checker_hashes,
        held_out_cases=held_out_cases,
    )

    # 2. Evaluate Training Split (Baseline vs Candidate)
    train_baseline_results = []
    train_candidate_results = []
    for c in train_cases:
        out_base = await executor_fn(c, candidate.baseline_prompt_text)
        train_baseline_results.append(evaluate_case_output(c, out_base, is_held_out=False))

        out_cand = await executor_fn(c, candidate.candidate_prompt_text)
        train_candidate_results.append(evaluate_case_output(c, out_cand, is_held_out=False))

    # 3. Evaluate Held-out Split (Baseline vs Candidate)
    held_out_baseline_results = []
    held_out_candidate_results = []
    for c in held_out_cases:
        out_base = await executor_fn(c, candidate.baseline_prompt_text)
        held_out_baseline_results.append(evaluate_case_output(c, out_base, is_held_out=True))

        out_cand = await executor_fn(c, candidate.candidate_prompt_text)
        held_out_candidate_results.append(evaluate_case_output(c, out_cand, is_held_out=True))

    # 4. Compute Aggregate Metrics
    train_base_passes = sum(r["passed"] for r in train_baseline_results)
    train_cand_passes = sum(r["passed"] for r in train_candidate_results)
    train_total = len(train_cases)

    held_base_passes = sum(r["passed"] for r in held_out_baseline_results)
    held_cand_passes = sum(r["passed"] for r in held_out_candidate_results)
    held_total = len(held_out_cases)

    # Detect if candidate invented constraints on any case
    any_invented_train = any(r["invented_constraints"] for r in train_candidate_results)
    any_invented_held = any(r["invented_constraints"] for r in held_out_candidate_results)

    # 5. Determine Acceptance Verdict
    if any_invented_train or any_invented_held:
        status = "REJECTED_INVENTED_CONSTRAINT"
        verdict = "REJECTED: Candidate passed by inventing user constraints or unrequested assumptions."
    elif held_cand_passes < held_base_passes:
        status = "REJECTED_HELD_OUT_REGRESSION"
        verdict = f"REJECTED: Candidate degraded held-out performance ({held_cand_passes}/{held_total} vs baseline {held_base_passes}/{held_total})."
    elif train_cand_passes <= train_base_passes and held_cand_passes <= held_base_passes:
        status = "REJECTED_NO_MEASURED_BENEFIT"
        verdict = "REJECTED: Candidate yielded no measured improvement over baseline."
    else:
        status = "ACCEPTED_CANDIDATE"
        verdict = (
            f"ACCEPTED: Candidate resolved training defects ({train_cand_passes}/{train_total} vs baseline {train_base_passes}/{train_total}) "
            f"with zero held-out regressions ({held_cand_passes}/{held_total} vs baseline {held_base_passes}/{held_total})."
        )

    return ComparisonReport(
        candidate_id=candidate.candidate_id,
        target_prompt=candidate.target_prompt_file,
        baseline_sha256=candidate.baseline_sha256,
        candidate_sha256=candidate.candidate_sha256,
        status=status,
        train_metrics={
            "baseline_passes": train_base_passes,
            "candidate_passes": train_cand_passes,
            "total_cases": train_total,
            "baseline_details": train_baseline_results,
            "candidate_details": train_candidate_results,
        },
        held_out_metrics={
            "baseline_passes": held_base_passes,
            "candidate_passes": held_cand_passes,
            "total_cases": held_total,
            "baseline_details": held_out_baseline_results,
            "candidate_details": held_out_candidate_results,
        },
        invariants_verified=True,
        summary_verdict=verdict,
    )


def main():
    p = argparse.ArgumentParser(description="Mímir Manual Prompt Comparison Evaluator (P3.3)")
    p.add_argument("--candidate-file", type=Path, required=True, help="JSON definition of PromptCandidate")
    p.add_argument("--regressions", type=Path, default=Path(".mimir/regressions.jsonl"), help="Regression store path")
    p.add_argument("--output", type=Path, required=True, help="Path for JSON comparison report")
    args = p.parse_args()

    cand_data = json.loads(args.candidate_file.read_text(encoding="utf-8"))
    candidate = PromptCandidate.from_dict(cand_data)

    rstore = RegressionStore(store_path=args.regressions)
    train_cases = rstore.list_cases(split="train")
    held_out_cases = rstore.list_cases(split="held_out")

    print(f"Loaded {len(train_cases)} train cases and {len(held_out_cases)} held-out cases.")
    print(f"Candidate: {candidate.candidate_id} modifying {candidate.target_prompt_file}")


if __name__ == "__main__":
    main()
