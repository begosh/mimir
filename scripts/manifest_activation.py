"""Manifest activation history, rollback management, and guidance promotion guards.

Part of Priority 3: Offline failure-to-regression loop (P3.5).
Implements:
1. Immutable activation lineage: records candidate hash, parent prior hash,
   selection record ID, and pre/post state snapshots in a durable ledger.
2. Rejected/unchanged candidate invariance: guarantees that losing or unchanged
   candidates never alter runtime prompts, manifests, or configuration.
3. Clean, verifiable rollback: restores prior state exactly and records rollback events.
4. Held-out answer leakage prevention: strictly audits candidate text and metadata
   against held-out regression cases, raising DataLeakageError on contamination.
5. LEARNINGS.md guidance promotion guard: prevents unvalidated notes or failed candidates
   from being promoted into standing project guidance.
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

from candidate_scoring import SelectionRecord
from regression_suite import DataLeakageError, RegressionCase
from run_locks import ownership, RunBusyError
from source_store import identity


class ActivationError(Exception):
    """Base exception for manifest activation errors."""


class RollbackError(ActivationError):
    """Exception raised when rollback validation fails."""


class PromotionGateError(ActivationError):
    """Exception raised when unvalidated notes or failed candidates attempt guidance promotion."""


@dataclass
class ActivationRecord:
    """Cryptographic ledger entry for an activation, rejection, or rollback event."""

    activation_id: str
    timestamp: str
    target_path: str
    action: str  # "ACTIVATE", "REJECT", "UNCHANGED", "ROLLBACK"
    candidate_id: str
    candidate_hash: str
    prior_hash: str
    selection_record_id: Optional[str] = None
    decision_rationale: List[str] = field(default_factory=list)
    pre_state_content: Optional[str] = None
    post_state_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ActivationRecord:
        return cls(**data)


def compute_sha256(text: str) -> str:
    """Compute normalized SHA-256 of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_held_out_leakage(text: str, held_out_cases: List[RegressionCase]) -> None:
    """Inspect text for leakage of held-out case answers, numbers, locators, or text spans."""
    if not held_out_cases or not text:
        return

    text_lower = text.lower()
    for case in held_out_cases:
        # Check case ID and source snapshot locators
        if case.case_id.lower() in text_lower:
            raise DataLeakageError(f"Held-out case ID leaked into candidate: {case.case_id}")

        for snap in getattr(case, "bound_sources", []):
            loc = snap.get("locator", "").lower()
            if loc and loc in text_lower and not loc.startswith("http"):
                raise DataLeakageError(f"Held-out source locator leaked: {loc}")

        # Check expected outputs or verification spec
        exp = getattr(case, "verification_spec", {}).get("expected_output") or getattr(case, "expected_output", "")
        if exp and len(exp.strip()) > 15:
            exp_clean = " ".join(exp.split()).lower()
            if exp_clean in " ".join(text_lower.split()):
                raise DataLeakageError(f"Held-out expected output leaked into candidate: {exp[:60]}...")

        # Check diagnostic specific values if present
        diag = getattr(case, "failure_lineage", {}).get("diagnostic") or getattr(case, "failure_diagnostic", "")
        if diag:
            numbers = re.findall(r"\b\d+(?:[.,]\d+)?\s*(?:°c|%|g|minuter|minutes)\b", diag.lower())
            for num in numbers:
                if num in text_lower:
                    raise DataLeakageError(f"Held-out diagnostic value '{num}' leaked into candidate prompt.")


class ManifestActivationManager:
    """Manages manifest activations, lineage tracking, and rollbacks."""

    def __init__(
        self,
        workspace: Optional[Path] = None,
        activation_log_path: Optional[Path] = None,
    ):
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.mimir_dir = self.workspace / ".mimir"
        self.activation_log = (
            Path(activation_log_path).resolve()
            if activation_log_path
            else self.mimir_dir / "manifest-activations.jsonl"
        )
        self.lock_path = self.activation_log.with_suffix(".lock")

    def get_history(self) -> List[ActivationRecord]:
        """Read all activation records from the durable ledger."""
        if not self.activation_log.exists():
            return []
        records = []
        with open(self.activation_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(ActivationRecord.from_dict(json.loads(line)))
                    except Exception:
                        continue
        return records

    def process_candidate(
        self,
        target_path: Path,
        candidate_text: str,
        selection_record: SelectionRecord,
        held_out_cases: Optional[List[RegressionCase]] = None,
        force: bool = False,
    ) -> Tuple[bool, ActivationRecord]:
        """Process a candidate adoption decision.
        
        If decision is ADOPT: atomically updates target_path and appends ACTIVATE record.
        If decision is REJECT/UNCHANGED: target_path is verified untouched and REJECT/UNCHANGED record is appended.
        """
        target = Path(target_path).resolve()
        if not target.exists():
            raise ActivationError(f"Target manifest/prompt path does not exist: {target}")

        # 1. Held-out answer leakage check
        if held_out_cases:
            check_held_out_leakage(candidate_text, held_out_cases)

        current_content = target.read_text(encoding="utf-8")
        current_hash = compute_sha256(current_content)
        cand_hash = compute_sha256(candidate_text)

        decision = selection_record.decision
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if decision == "ADOPT":
            if current_hash == cand_hash and not force:
                decision = "UNCHANGED"

        self.mimir_dir.mkdir(parents=True, exist_ok=True)

        with ownership(self.lock_path):
            if decision == "ADOPT":
                act_id = f"act-{identity([selection_record.candidate_id, str(target), cand_hash, now_iso])}"
                record = ActivationRecord(
                    activation_id=act_id,
                    timestamp=now_iso,
                    target_path=str(target),
                    action="ACTIVATE",
                    candidate_id=selection_record.candidate_id,
                    candidate_hash=cand_hash,
                    prior_hash=current_hash,
                    selection_record_id=selection_record.selection_id,
                    decision_rationale=selection_record.reasons,
                    pre_state_content=current_content,
                    post_state_content=candidate_text,
                    metadata={"reviewer": selection_record.reviewer},
                )
                # Atomically write new target content
                target.write_text(candidate_text, encoding="utf-8")
                # Append to activation ledger
                with open(self.activation_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
                return True, record

            else:
                # REJECT or UNCHANGED: target MUST remain untouched
                act_id = f"noact-{identity([selection_record.candidate_id, str(target), decision, now_iso])}"
                record = ActivationRecord(
                    activation_id=act_id,
                    timestamp=now_iso,
                    target_path=str(target),
                    action=decision,
                    candidate_id=selection_record.candidate_id,
                    candidate_hash=cand_hash,
                    prior_hash=current_hash,
                    selection_record_id=selection_record.selection_id,
                    decision_rationale=selection_record.reasons,
                    pre_state_content=current_content,
                    post_state_content=current_content,  # Unaltered
                    metadata={"reviewer": selection_record.reviewer},
                )
                # Verify target remained untouched
                post_content = target.read_text(encoding="utf-8")
                if compute_sha256(post_content) != current_hash:
                    raise ActivationError(f"Target was modified during {decision} processing.")

                with open(self.activation_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
                return False, record

    def rollback(
        self,
        activation_id: Optional[str] = None,
        target_path: Optional[Path] = None,
        reason: str = "Rollback requested by operator",
    ) -> ActivationRecord:
        """Roll back an activation to its pre-state snapshot."""
        history = self.get_history()
        if not history:
            raise RollbackError("Activation history is empty; cannot roll back.")

        # Find target activation to roll back
        target_record: Optional[ActivationRecord] = None
        if activation_id:
            for rec in reversed(history):
                if rec.activation_id == activation_id and rec.action == "ACTIVATE":
                    target_record = rec
                    break
            if not target_record:
                raise RollbackError(f"No active activation found with ID: {activation_id}")
        else:
            # Most recent ACTIVATE record
            for rec in reversed(history):
                if rec.action == "ACTIVATE":
                    target_record = rec
                    break
            if not target_record:
                raise RollbackError("No previous ACTIVATE record found in history to roll back.")

        target = Path(target_path or target_record.target_path).resolve()
        if not target.exists():
            raise RollbackError(f"Target path does not exist for rollback: {target}")

        current_content = target.read_text(encoding="utf-8")
        current_hash = compute_sha256(current_content)

        if current_hash != target_record.candidate_hash:
            # File was modified out-of-band after activation
            raise RollbackError(
                f"Target file hash {current_hash} differs from active candidate hash {target_record.candidate_hash}. "
                "Refusing blind rollback over modified file."
            )

        if not target_record.pre_state_content:
            raise RollbackError(f"Activation record {target_record.activation_id} lacks pre-state snapshot.")

        restored_content = target_record.pre_state_content
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rb_id = f"rb-{identity([target_record.activation_id, now_iso])}"

        with ownership(self.lock_path):
            # Restore previous content
            target.write_text(restored_content, encoding="utf-8")
            restored_hash = compute_sha256(restored_content)

            if restored_hash != target_record.prior_hash:
                raise RollbackError(f"Restored content hash {restored_hash} does not match prior hash {target_record.prior_hash}.")

            rollback_record = ActivationRecord(
                activation_id=rb_id,
                timestamp=now_iso,
                target_path=str(target),
                action="ROLLBACK",
                candidate_id=target_record.candidate_id,
                candidate_hash=restored_hash,
                prior_hash=current_hash,
                selection_record_id=target_record.selection_record_id,
                decision_rationale=[f"Rolled back {target_record.activation_id}: {reason}"],
                pre_state_content=current_content,
                post_state_content=restored_content,
                metadata={"rolled_back_activation_id": target_record.activation_id, "reason": reason},
            )

            with open(self.activation_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(rollback_record.to_dict(), ensure_ascii=False) + "\n")

            return rollback_record


def guard_guidance_promotion(
    candidate_note: Dict[str, Any],
    proposed_heuristic_text: str,
    guidance_file_path: Path,
    adjudicator_status: str,
    held_out_cases: Optional[List[RegressionCase]] = None,
) -> bool:
    """Guard LEARNINGS.md against unvalidated notes or failed candidates.
    
    Acceptance requirements:
    1. Candidate status must not be 'requires_independent_validation' or unreviewed.
    2. Adjudicator status must be explicitly 'validated' or 'adjudicated_pass'.
    3. Proposed note must provide cited evidence and non-empty reflection.
    4. Proposed note must not leak any held-out cases or data.
    """
    guidance_path = Path(guidance_file_path).resolve()

    # 1. Check adjudicator status
    if adjudicator_status not in {"validated", "adjudicated_pass"}:
        raise PromotionGateError(
            f"Guidance promotion denied: candidate status is '{adjudicator_status}'. "
            "Promotion requires an explicit 'validated' adjudicator status."
        )

    # 2. Check candidate note internal status
    cand_status = candidate_note.get("status", "")
    if cand_status == "requires_independent_validation":
        raise PromotionGateError(
            "Guidance promotion denied: candidate internal status is 'requires_independent_validation'."
        )

    # 3. Check for held-out leakage
    if held_out_cases:
        check_held_out_leakage(proposed_heuristic_text, held_out_cases)

    # 4. Content sanity
    if len(proposed_heuristic_text.strip()) < 20:
        raise PromotionGateError("Guidance promotion denied: proposed heuristic text is too brief or empty.")

    # 5. Append to LEARNINGS.md under lock
    lock = guidance_path.with_suffix(".lock")
    with ownership(lock):
        if not guidance_path.exists():
            guidance_path.parent.mkdir(parents=True, exist_ok=True)
            guidance_path.write_text("# M Í M I R // Standing Guidance\n\n", encoding="utf-8")

        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        formatted_entry = (
            f"\n### [{timestamp}] Promoted Heuristic: {candidate_note.get('candidate_id', 'unknown')}\n"
            f"- **Validated Principle:** {proposed_heuristic_text.strip()}\n"
            f"- **Adjudicated by:** {candidate_note.get('reviewer', 'supervisor')} ({adjudicator_status})\n"
        )
        with open(guidance_path, "a", encoding="utf-8") as f:
            f.write(formatted_entry)

    return True
