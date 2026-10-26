"""Versioned regression suite and failure-to-regression loop.

Part of Priority 3: Offline failure-to-regression loop (P3.2).
Converts confirmed failures into versioned regressions and enforces
strict disjoint family separation between train/dev and fresh held-out cases
by source, topic, and failure lineage.

Prevents held-out data leakage, weak check promotion, and unvalidated guidance.
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
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from failure_store import FailurePacket, FailureStore
from run_locks import ownership, RunBusyError
from source_store import identity


VALID_SPLITS = {"train", "dev", "held_out"}
DEFAULT_REGRESSION_STORE_PATH = ".mimir/regressions.jsonl"


class DataLeakageError(ValueError):
    """Raised when train/dev and held-out splits share sources, topics, or lineages."""
    pass


def normalize_token(s: str) -> str:
    """Normalize identifiers, locators, and topic names."""
    return "".join(c.lower() if c.isalnum() or c in "._-" else "_" for c in (s or "").strip()).strip("_")


def derive_source_family(sources: List[Dict[str, Any]], default: str = "unbound") -> str:
    """Extract a canonical source family name from bound sources or locators."""
    if not sources:
        return default
    locators = [s.get("locator") or s.get("id") or "" for s in sources]
    for loc in locators:
        if loc:
            # Handle fixture:name, file paths, or URIs
            p = Path(loc)
            base = p.stem or p.name or loc
            clean = normalize_token(base)
            if clean:
                return clean
    return default


def derive_topic_family(intent: str, objective: str, defects: List[Dict[str, Any]],
                        default: str = "general") -> str:
    """Heuristically derive a semantic topic family from intent and defects."""
    combined = f"{intent} {objective} " + " ".join(d.get("description", "") for d in defects)
    low = combined.lower()

    if any(k in low for k in ("pizza", "dough", "hydration", "baker", "flour", "yeast")):
        return "baking_and_formulation"
    if any(k in low for k in ("requirement", "dependency", "version", "pin", "package", "setup")):
        return "dependency_management"
    if any(k in low for k in ("auth", "timeout", "token", "credential", "login", "jwt")):
        return "authentication_and_session"
    if any(k in low for k in ("calc", "formula", "percentage", "ratio", "scale", "arithmetic")):
        return "quantitative_reasoning"
    if any(k in low for k in ("ast", "syntax", "parse", "grammar", "code")):
        return "syntax_and_structure"

    # Default to first two significant words from objective
    words = [normalize_token(w) for w in (objective or intent).split() if len(w) > 3]
    if words:
        return "_".join(words[:2])
    return default


def compute_case_id(packet_id: str, version: int, topic: str, source_family: str) -> str:
    """Compute deterministic regression case identifier."""
    raw = f"{packet_id}:v{version}:{topic}:{source_family}"
    return f"reg-v{version}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


@dataclass
class RegressionCase:
    """Versioned regression test case derived from a confirmed failure."""

    case_id: str
    version: int
    packet_id: str
    original_intent: str
    goal: str
    topic: str
    source_family: str
    failure_lineage: Dict[str, Any]
    split: str
    split_family: str
    bound_sources: List[Dict[str, Any]] = field(default_factory=list)
    verification_spec: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def __post_init__(self):
        if self.split not in VALID_SPLITS:
            raise ValueError(f"Invalid split '{self.split}'. Must be one of {VALID_SPLITS}")
        if not self.topic or not self.topic.strip():
            raise ValueError("RegressionCase requires a non-empty topic family.")
        if not self.source_family or not self.source_family.strip():
            raise ValueError("RegressionCase requires a non-empty source family.")
        if not self.goal or not self.goal.strip():
            raise ValueError("RegressionCase requires a non-empty goal.")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RegressionCase:
        d = deepcopy(data)
        return cls(**d)

    def to_eval_case(self) -> Dict[str, Any]:
        """Export case representation directly compatible with scripts/evaluate.py."""
        spec = self.verification_spec or {}
        return {
            "id": self.case_id,
            "goal": self.goal,
            "topic": self.topic,
            "source_family": self.source_family,
            "split": self.split,
            "required_locators": spec.get("required_locators", []),
            "required_answer_markers": spec.get("required_answer_markers", []),
            "forbidden_answer_markers": spec.get("forbidden_answer_markers", []),
            "expected_blockers": spec.get("expected_blockers", []),
            "expected_defect_types": spec.get("expected_defect_types", []),
            "lineage": {
                "packet_id": self.packet_id,
                "origin_run_id": self.failure_lineage.get("origin_run_id"),
                "failure_kind": self.failure_lineage.get("failure_kind"),
            },
        }


def convert_failure_to_regression(
    packet: FailurePacket,
    *,
    split: str = "train",
    version: int = 1,
    topic: Optional[str] = None,
    source_family: Optional[str] = None,
    override_goal: Optional[str] = None,
    verification_spec: Optional[Dict[str, Any]] = None,
) -> RegressionCase:
    """Convert an independently confirmed failure packet into a versioned RegressionCase.

    Accepts packets that represent confirmed or triaged defects.
    Derives deterministic family keys for partition isolation.
    """
    if packet.resolution_status == "waived":
        raise ValueError(f"Cannot convert waived failure packet {packet.packet_id} to a regression case.")

    sources = packet.source_snapshots or []
    src_fam = source_family or derive_source_family(sources, default="unbound")
    top_fam = topic or derive_topic_family(packet.original_intent, packet.task_objective,
                                          packet.adjudicated_defects)
    split_fam = f"{top_fam}::{src_fam}"

    # Compile verification spec from defects, attempts, and feedback
    spec = deepcopy(verification_spec or {})
    if "required_locators" not in spec:
        spec["required_locators"] = [s.get("locator") for s in sources if s.get("locator")]
    if "expected_defect_types" not in spec:
        spec["expected_defect_types"] = [d.get("defect_type") for d in packet.adjudicated_defects if d.get("defect_type")]
    if packet.failure_kind == "missing_input_blocker" and "expected_blockers" not in spec:
        # Extract unresolved input names from task brief or attempts
        blockers = []
        if packet.task_brief and packet.task_brief.get("missing_information"):
            blockers.extend(packet.task_brief["missing_information"])
        for d in packet.adjudicated_defects:
            desc = d.get("description", "")
            for word in desc.split():
                if "_" in word or word.isalnum():
                    clean_w = normalize_token(word)
                    if clean_w and clean_w not in blockers and clean_w in desc:
                        blockers.append(clean_w)
        spec["expected_blockers"] = blockers

    lineage = {
        "packet_id": packet.packet_id,
        "task_id": packet.task_id,
        "failure_kind": packet.failure_kind,
        "origin_run_id": packet.metadata.get("run_id"),
        "defect_types": [d.get("defect_type") for d in packet.adjudicated_defects],
        "occurrences": packet.occurrences,
        "resolution_status": packet.resolution_status,
        "lineage_root": packet.metadata.get("run_id") or packet.packet_id,
    }

    cid = compute_case_id(packet.packet_id, version, top_fam, src_fam)
    eval_goal = override_goal or packet.original_intent or packet.task_objective

    return RegressionCase(
        case_id=cid,
        version=version,
        packet_id=packet.packet_id,
        original_intent=packet.original_intent,
        goal=eval_goal,
        topic=top_fam,
        source_family=src_fam,
        failure_lineage=lineage,
        split=split,
        split_family=split_fam,
        bound_sources=sources,
        verification_spec=spec,
        metadata={
            "created_from_packet": packet.packet_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "packet_created_at": packet.created_at,
        },
    )


def partition_splits(
    cases: List[RegressionCase],
    *,
    held_out_families: Optional[Set[str]] = None,
    dev_families: Optional[Set[str]] = None,
    held_out_ratio: float = 0.25,
    dev_ratio: float = 0.25,
    seed: int = 42,
) -> List[RegressionCase]:
    """Partition regression cases into train, dev, and held_out splits with strict family isolation.

    Guarantees:
    - Entire (topic, source_family) pairs are placed into exactly one split.
    - No source or topic assigned to held_out ever appears in train or dev.
    - Deterministic and reproducible across environments.
    """
    if not cases:
        return []

    # Map families
    distinct_families = sorted(list({c.split_family for c in cases}))
    distinct_topics = sorted(list({c.topic for c in cases}))
    distinct_sources = sorted(list({c.source_family for c in cases}))

    assigned_held_out: Set[str] = set(held_out_families or [])
    assigned_dev: Set[str] = set(dev_families or [])

    # If not explicitly specified, partition based on deterministic hashing
    if not assigned_held_out and not assigned_dev:
        # We partition by distinct topics / source families to enforce disjointness
        for fam in distinct_families:
            h = int(hashlib.sha256(f"{fam}:{seed}".encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
            if h < held_out_ratio:
                assigned_held_out.add(fam)
            elif h < (held_out_ratio + dev_ratio):
                assigned_dev.add(fam)

    # If any family in held-out shares a topic or source with dev or train, isolate the entire topic/source
    held_out_topics = {c.topic for c in cases if c.split_family in assigned_held_out}
    held_out_sources = {c.source_family for c in cases if c.split_family in assigned_held_out}

    updated: List[RegressionCase] = []
    for c in cases:
        # Determine split
        if c.split_family in assigned_held_out or c.topic in held_out_topics or c.source_family in held_out_sources:
            target_split = "held_out"
        elif c.split_family in assigned_dev:
            target_split = "dev"
        else:
            target_split = "train"

        d = c.to_dict()
        d["split"] = target_split
        updated.append(RegressionCase.from_dict(d))

    # Validate before returning
    validate_split_isolation(updated)
    return updated


def validate_split_isolation(cases: Iterable[RegressionCase]) -> None:
    """Enforce zero data leakage between train/dev and held-out splits.

    Checks:
    1. Every case has a valid split in {"train", "dev", "held_out"}.
    2. Intersection of source families between train/dev and held_out is strictly empty.
    3. Intersection of topic families between train/dev and held_out is strictly empty.
    4. Intersection of failure lineages between train/dev and held_out is strictly empty.
    """
    train_dev_sources: Set[str] = set()
    train_dev_topics: Set[str] = set()
    train_dev_lineages: Set[str] = set()
    train_dev_packet_ids: Set[str] = set()

    held_out_sources: Set[str] = set()
    held_out_topics: Set[str] = set()
    held_out_lineages: Set[str] = set()
    held_out_packet_ids: Set[str] = set()

    for c in cases:
        if c.split not in VALID_SPLITS:
            raise DataLeakageError(f"Case {c.case_id} has invalid split '{c.split}'.")

        lineage_id = c.failure_lineage.get("lineage_root") or c.packet_id

        if c.split in {"train", "dev"}:
            train_dev_sources.add(c.source_family)
            train_dev_topics.add(c.topic)
            train_dev_lineages.add(lineage_id)
            train_dev_packet_ids.add(c.packet_id)
        else:
            held_out_sources.add(c.source_family)
            held_out_topics.add(c.topic)
            held_out_lineages.add(lineage_id)
            held_out_packet_ids.add(c.packet_id)

    # 1. Source overlap check
    source_overlap = train_dev_sources & held_out_sources
    if source_overlap:
        raise DataLeakageError(
            f"Cross-split contamination detected: Source families {source_overlap} "
            f"appear in both train/dev and held-out splits."
        )

    # 2. Topic overlap check
    topic_overlap = train_dev_topics & held_out_topics
    if topic_overlap:
        raise DataLeakageError(
            f"Cross-split contamination detected: Topic families {topic_overlap} "
            f"appear in both train/dev and held-out splits."
        )

    # 3. Lineage overlap check
    lineage_overlap = train_dev_lineages & held_out_lineages
    if lineage_overlap:
        raise DataLeakageError(
            f"Lineage leakage detected: Failure lineages {lineage_overlap} "
            f"appear in both train/dev and held-out splits."
        )

    # 4. Packet ID check
    packet_overlap = train_dev_packet_ids & held_out_packet_ids
    if packet_overlap:
        raise DataLeakageError(
            f"Direct packet leakage detected: Packet IDs {packet_overlap} "
            f"appear in both train/dev and held-out splits."
        )


class RegressionStore:
    """Process-safe, file-backed repository of versioned regression cases."""

    def __init__(self, store_path: Optional[str | Path] = None, workspace: Optional[str | Path] = None):
        base = Path(workspace) if workspace else Path.cwd()
        if store_path:
            p = Path(store_path)
            self.store_path = p if p.is_absolute() else base / p
        else:
            self.store_path = base / DEFAULT_REGRESSION_STORE_PATH

        self.lock_path = self.store_path.with_suffix(".lock")
        self._ensure_store_dir()

    def _ensure_store_dir(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_all_unlocked(self) -> Dict[str, RegressionCase]:
        if not self.store_path.exists():
            return {}
        cases = {}
        for line in self.store_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    data = json.loads(line)
                    case = RegressionCase.from_dict(data)
                    cases[case.case_id] = case
                except Exception:
                    continue
        return cases

    def _save_all_unlocked(self, cases: Dict[str, RegressionCase]):
        tmp = self.store_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for case in cases.values():
                f.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")
        tmp.replace(self.store_path)

    def get(self, case_id: str) -> Optional[RegressionCase]:
        """Retrieve a regression case by ID."""
        with ownership(self.lock_path):
            cases = self._load_all_unlocked()
            return cases.get(case_id)

    def add(self, case: RegressionCase) -> RegressionCase:
        """Add or update a regression case in the store."""
        with ownership(self.lock_path):
            cases = self._load_all_unlocked()
            cases[case.case_id] = deepcopy(case)
            self._save_all_unlocked(cases)
            return deepcopy(case)

    def add_many(self, cases: Iterable[RegressionCase], *, validate: bool = True) -> int:
        """Add multiple regression cases and optionally validate split isolation."""
        case_list = list(cases)
        if validate:
            validate_split_isolation(case_list)

        with ownership(self.lock_path):
            existing = self._load_all_unlocked()
            for c in case_list:
                existing[c.case_id] = deepcopy(c)
            if validate:
                validate_split_isolation(existing.values())
            self._save_all_unlocked(existing)
            return len(case_list)

    def list_cases(
        self,
        *,
        split: Optional[str] = None,
        topic: Optional[str] = None,
        source_family: Optional[str] = None,
        version: Optional[int] = None,
    ) -> List[RegressionCase]:
        """Query regression cases filtered by split, topic, source family, or version."""
        with ownership(self.lock_path):
            cases = list(self._load_all_unlocked().values())

        if split:
            cases = [c for c in cases if c.split == split]
        if topic:
            cases = [c for c in cases if c.topic == topic]
        if source_family:
            cases = [c for c in cases if c.source_family == source_family]
        if version:
            cases = [c for c in cases if c.version == version]

        return sorted(cases, key=lambda c: (c.topic, c.source_family, c.case_id))

    def ingest_from_failure_store(
        self,
        failure_store: FailureStore,
        *,
        version: int = 1,
        auto_partition: bool = True,
        held_out_ratio: float = 0.25,
        dev_ratio: float = 0.25,
    ) -> List[RegressionCase]:
        """Ingest confirmed/triaged failure packets from FailureStore into RegressionCases."""
        # Query confirmed or unresolved packets with non-empty adjudicated defects
        packets = failure_store.list_packets()
        confirmed = [p for p in packets if p.resolution_status != "waived" and p.adjudicated_defects]

        cases = []
        for p in confirmed:
            try:
                case = convert_failure_to_regression(p, version=version)
                cases.append(case)
            except Exception:
                continue

        if auto_partition and cases:
            cases = partition_splits(cases, held_out_ratio=held_out_ratio, dev_ratio=dev_ratio)

        self.add_many(cases, validate=True)
        return cases

    def export_eval_dataset(self, split: str, out_file: Optional[Path | str] = None) -> List[Dict[str, Any]]:
        """Export cases for a specific split in scripts/evaluate.py JSON format."""
        if split not in VALID_SPLITS:
            raise ValueError(f"Invalid split '{split}'. Must be one of {VALID_SPLITS}")

        cases = self.list_cases(split=split)
        eval_cases = [c.to_eval_case() for c in cases]

        if out_file:
            p = Path(out_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(eval_cases, indent=2, ensure_ascii=False), encoding="utf-8")

        return eval_cases

    def validate_integrity(self) -> Dict[str, Any]:
        """Validate isolation and summarize case counts across splits."""
        with ownership(self.lock_path):
            cases = list(self._load_all_unlocked().values())

        validate_split_isolation(cases)

        summary = {
            "total_cases": len(cases),
            "splits": {
                "train": sum(c.split == "train" for c in cases),
                "dev": sum(c.split == "dev" for c in cases),
                "held_out": sum(c.split == "held_out" for c in cases),
            },
            "topics": sorted(list({c.topic for c in cases})),
            "source_families": sorted(list({c.source_family for c in cases})),
            "status": "VALID_DISJOINT_SPLITS",
        }
        return summary


def main():
    p = argparse.ArgumentParser(description="Mímir Regression Suite: Versioned Failure-to-Regression Management")
    p.add_argument("--store", type=Path, default=None, help="Path to regression JSONL store")
    p.add_argument("--list", action="store_true", help="List regression cases")
    p.add_argument("--split", choices=list(VALID_SPLITS), help="Filter by split")
    p.add_argument("--topic", help="Filter by topic family")
    p.add_argument("--from-failures", type=Path, help="Ingest confirmed failures from FailureStore JSONL")
    p.add_argument("--export-eval", type=Path, help="Export eval cases to JSON file")
    p.add_argument("--validate", action="store_true", help="Validate split isolation and integrity")
    args = p.parse_args()

    store = RegressionStore(store_path=args.store)

    if args.from_failures:
        fstore = FailureStore(store_path=args.from_failures)
        ingested = store.ingest_from_failure_store(fstore)
        print(f"Ingested and partitioned {len(ingested)} regression cases from {args.from_failures}.")

    if args.validate:
        summary = store.validate_integrity()
        print(json.dumps(summary, indent=2))

    if args.export_eval:
        split_name = args.split or "held_out"
        exported = store.export_eval_dataset(split_name, out_file=args.export_eval)
        print(f"Exported {len(exported)} cases for split '{split_name}' to {args.export_eval}.")

    if args.list:
        cases = store.list_cases(split=args.split, topic=args.topic)
        print(f"Found {len(cases)} regression cases:")
        for c in cases:
            print(f"  [{c.case_id}] (v{c.version}) {c.split.upper()} | Topic: {c.topic} | Source: {c.source_family} | Goal: {c.goal[:60]}")


if __name__ == "__main__":
    main()
