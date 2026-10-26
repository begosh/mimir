"""Failure packet schema, deduplication store, and defect adjudication.

Part of Priority 3: Offline failure-to-regression loop (P3.1).
Captures and deduplicates failure packets containing:
1. Original intent: high-level user goal, task brief, and task objective.
2. Source snapshots/spans: bound source locators, version hashes, retrieval metadata, and excerpts.
3. Attempts & feedback: candidate outputs, raw responses, Result Gate / checker verdicts, issues, and repairs.
4. Independently adjudicated defects: defect type, severity, description, and adjudicator source.
"""
from __future__ import annotations

from copy import deepcopy
import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from run_locks import ownership, RunBusyError
from source_store import identity


VALID_FAILURE_KINDS = {
    "result_check_failure",
    "missing_input_blocker",
    "budget_exhaustion",
    "execution_error",
    "assembly_failure",
    "structural_provenance_failure",
}

VALID_DEFECT_TYPES = {
    "hallucinated_entity",
    "wrong_association",
    "inverted_condition",
    "required_omission_violation",
    "arithmetic_contradiction",
    "missing_required_input",
    "unsupported_claim",
    "timeout",
    "execution_crash",
    "structural_defect",
    "unknown",
}

VALID_SEVERITIES = {"critical", "major", "minor"}

VALID_ADJUDICATORS = {
    "deterministic_gate",
    "blinded_checker",
    "engine_supervisor",
    "human_adjudication",
}

VALID_RESOLUTION_STATUSES = {"unresolved", "confirmed", "repaired", "waived"}


def compute_packet_id(original_intent: str, task_objective: str,
                      failure_kind: str, defect_fingerprint: str) -> str:
    """Deterministic content-addressable hash for failure packet deduplication."""
    clean_intent = " ".join((original_intent or "").split())
    clean_obj = " ".join((task_objective or "").split())
    key = [clean_intent, clean_obj, failure_kind, defect_fingerprint]
    return identity(key)


def classify_defect_from_feedback(issue: str, check_type: Optional[str] = None) -> Tuple[str, str]:
    """Classify an issue string into a standardized defect type and severity."""
    low = (issue or "").lower()
    ct = (check_type or "").lower()

    if "deterministic_calculation" in ct or "contradiction" in low or "math" in low:
        return "arithmetic_contradiction", "critical"
    if "structural" in ct or "citation" in low or "locator" in low or "offset" in low:
        return "structural_defect", "major"
    if "missing operand" in low or "missing required" in low or "unresolved required" in low:
        return "missing_required_input", "critical"
    if "hallucinat" in low or "invent" in low or "not in source" in low:
        return "hallucinated_entity", "critical"
    if "omit" in low or "omission" in low:
        return "required_omission_violation", "major"
    if "condition" in low or "precedence" in low:
        return "inverted_condition", "major"
    if "association" in low or "swapped" in low or "reversed" in low:
        return "wrong_association", "major"
    if "unsupported" in low:
        return "unsupported_claim", "major"
    if "timeout" in low:
        return "timeout", "critical"
    if "crash" in low or "exception" in low or "error" in low:
        return "execution_crash", "critical"

    return "unknown", "minor"


class FailurePacket:
    """Self-contained, content-deduplicated record of a task or run failure."""

    def __init__(
        self,
        *,
        packet_id: Optional[str] = None,
        created_at: Optional[str] = None,
        original_intent: str,
        task_id: str,
        task_objective: str,
        failure_kind: str,
        task_brief: Optional[Dict[str, Any]] = None,
        source_snapshots: Optional[List[Dict[str, Any]]] = None,
        attempts: Optional[List[Dict[str, Any]]] = None,
        adjudicated_defects: Optional[List[Dict[str, Any]]] = None,
        resolution_status: str = "unresolved",
        occurrences: int = 1,
        history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if failure_kind not in VALID_FAILURE_KINDS:
            raise ValueError(f"Invalid failure_kind: {failure_kind}. Must be one of {VALID_FAILURE_KINDS}")
        if resolution_status not in VALID_RESOLUTION_STATUSES:
            raise ValueError(f"Invalid resolution_status: {resolution_status}")

        self.original_intent = original_intent or ""
        self.task_id = task_id or ""
        self.task_objective = task_objective or ""
        self.failure_kind = failure_kind
        self.task_brief = deepcopy(task_brief) if task_brief else None
        self.source_snapshots = deepcopy(source_snapshots or [])
        self.attempts = deepcopy(attempts or [])
        self.adjudicated_defects = deepcopy(adjudicated_defects or [])
        self.resolution_status = resolution_status
        self.occurrences = max(1, occurrences)
        self.created_at = created_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.history = deepcopy(history or [{"timestamp": self.created_at, "run_id": (metadata or {}).get("run_id")}])
        self.metadata = deepcopy(metadata or {})

        # Compute deterministic defect fingerprint from attempts & issues
        all_issues = []
        for att in self.attempts:
            for issue in att.get("issues", []):
                all_issues.append(str(issue))
            if att.get("feedback"):
                all_issues.append(str(att["feedback"]))
        defect_fp = hashlib.sha256("\n".join(sorted(all_issues)).encode("utf-8")).hexdigest()[:16]

        self.packet_id = packet_id or compute_packet_id(
            self.original_intent, self.task_objective, self.failure_kind, defect_fp
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "created_at": self.created_at,
            "original_intent": self.original_intent,
            "task_id": self.task_id,
            "task_objective": self.task_objective,
            "failure_kind": self.failure_kind,
            "task_brief": self.task_brief,
            "source_snapshots": self.source_snapshots,
            "attempts": self.attempts,
            "adjudicated_defects": self.adjudicated_defects,
            "resolution_status": self.resolution_status,
            "occurrences": self.occurrences,
            "history": self.history,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FailurePacket:
        return cls(
            packet_id=data.get("packet_id"),
            created_at=data.get("created_at"),
            original_intent=data.get("original_intent", ""),
            task_id=data.get("task_id", ""),
            task_objective=data.get("task_objective", ""),
            failure_kind=data.get("failure_kind", "execution_error"),
            task_brief=data.get("task_brief"),
            source_snapshots=data.get("source_snapshots"),
            attempts=data.get("attempts"),
            adjudicated_defects=data.get("adjudicated_defects"),
            resolution_status=data.get("resolution_status", "unresolved"),
            occurrences=data.get("occurrences", 1),
            history=data.get("history"),
            metadata=data.get("metadata"),
        )

    def add_defect(self, defect_type: str, severity: str, description: str,
                   adjudicator: str = "engine_supervisor") -> None:
        """Add an independently adjudicated defect to this failure packet."""
        if defect_type not in VALID_DEFECT_TYPES:
            raise ValueError(f"Invalid defect_type: {defect_type}")
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity}")
        if adjudicator not in VALID_ADJUDICATORS:
            raise ValueError(f"Invalid adjudicator: {adjudicator}")

        defect = {
            "defect_type": defect_type,
            "severity": severity,
            "description": description.strip(),
            "adjudicator": adjudicator,
            "adjudicated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.adjudicated_defects.append(defect)


class FailureStore:
    """Thread-safe and process-safe deduplicated store for failure packets."""

    def __init__(self, store_path: Optional[Path | str] = None, *, workspace: Optional[Path | str] = None):
        ws = Path(workspace or Path.cwd()).resolve()
        if store_path:
            self.store_path = Path(store_path).resolve()
        else:
            self.store_path = ws / ".mimir" / "failure-packets.jsonl"
        self.lock_path = self.store_path.with_suffix(".lock")
        self.last_error: Optional[str] = None

    def ingest(self, packet: FailurePacket) -> Tuple[FailurePacket, bool]:
        """Ingest a failure packet, deduplicating by packet_id.

        Returns (packet, is_new). If existing, increments occurrences and appends history.
        """
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with ownership(self.lock_path):
                packets = self._load_packets_unlocked()
                if packet.packet_id in packets:
                    existing = packets[packet.packet_id]
                    existing.occurrences += 1
                    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    run_id = packet.metadata.get("run_id")
                    existing.history.append({"timestamp": ts, "run_id": run_id})

                    # Merge new attempts if any
                    seen_attempts = {att.get("attempt") for att in existing.attempts}
                    for att in packet.attempts:
                        if att.get("attempt") not in seen_attempts:
                            existing.attempts.append(att)

                    # Merge new defects
                    seen_defects = {(d.get("defect_type"), d.get("description")) for d in existing.adjudicated_defects}
                    for defect in packet.adjudicated_defects:
                        if (defect.get("defect_type"), defect.get("description")) not in seen_defects:
                            existing.adjudicated_defects.append(defect)

                    packets[packet.packet_id] = existing
                    self._save_packets_unlocked(packets)
                    return existing, False
                else:
                    packets[packet.packet_id] = packet
                    self._save_packets_unlocked(packets)
                    return packet, True
        except (OSError, UnicodeError, RunBusyError) as exc:
            self.last_error = str(exc)
            raise

    def get(self, packet_id: str) -> Optional[FailurePacket]:
        """Retrieve a failure packet by its content-addressable ID."""
        with ownership(self.lock_path):
            packets = self._load_packets_unlocked()
            return packets.get(packet_id)

    def list_packets(self, *, failure_kind: Optional[str] = None,
                     defect_type: Optional[str] = None,
                     resolution_status: Optional[str] = None) -> List[FailurePacket]:
        """List all failure packets matching optional filters."""
        with ownership(self.lock_path):
            packets = list(self._load_packets_unlocked().values())

        if failure_kind:
            packets = [p for p in packets if p.failure_kind == failure_kind]
        if defect_type:
            packets = [p for p in packets if any(d.get("defect_type") == defect_type for d in p.adjudicated_defects)]
        if resolution_status:
            packets = [p for p in packets if p.resolution_status == resolution_status]

        return sorted(packets, key=lambda p: p.created_at, reverse=True)

    def adjudicate(self, packet_id: str, *, defect_type: str, severity: str,
                   description: str, adjudicator: str = "human_adjudication",
                   resolution_status: Optional[str] = None) -> FailurePacket:
        """Independently adjudicate defects for an existing packet."""
        with ownership(self.lock_path):
            packets = self._load_packets_unlocked()
            if packet_id not in packets:
                raise KeyError(f"Failure packet {packet_id} not found in store")
            packet = packets[packet_id]
            packet.add_defect(defect_type=defect_type, severity=severity,
                              description=description, adjudicator=adjudicator)
            if resolution_status:
                if resolution_status not in VALID_RESOLUTION_STATUSES:
                    raise ValueError(f"Invalid resolution_status: {resolution_status}")
                packet.resolution_status = resolution_status
            packets[packet_id] = packet
            self._save_packets_unlocked(packets)
            return packet

    def _load_packets_unlocked(self) -> Dict[str, FailurePacket]:
        if not self.store_path.exists():
            return {}
        packets = {}
        with self.store_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if isinstance(data, dict) and "packet_id" in data:
                        packets[data["packet_id"]] = FailurePacket.from_dict(data)
                except json.JSONDecodeError:
                    continue
        return packets

    def _save_packets_unlocked(self, packets: Dict[str, FailurePacket]) -> None:
        temp_path = self.store_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as stream:
            for packet in packets.values():
                stream.write(json.dumps(packet.to_dict(), ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temp_path.replace(self.store_path)


# Helper functions for capturing failures from execution artifacts

def capture_from_node(node: Any, *, goal: str, task_brief: Optional[Dict[str, Any]] = None,
                      run_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Optional[FailurePacket]:
    """Capture a failure packet from a failed or blocked TaskNode."""
    from task_graph import TaskStatus

    if node.status == TaskStatus.COMPLETED:
        return None

    failure_kind = "missing_input_blocker" if node.status == TaskStatus.BLOCKED else "result_check_failure"
    sources = deepcopy(node.input_artifacts.get("supplied_sources", []))

    attempts = []
    adjudicated = []
    for att in getattr(node, "result_attempts", []):
        att_record = {
            "attempt": att.get("attempt", len(attempts) + 1),
            "output": att.get("output"),
            "raw_response": att.get("raw_response", ""),
            "issues": att.get("issues", []),
            "check_type": att.get("check_type", "semantic_support"),
            "repair": att.get("repair"),
            "repair_error": att.get("repair_error"),
        }
        attempts.append(att_record)
        for issue in att.get("issues", []):
            dtype, severity = classify_defect_from_feedback(issue, att.get("check_type"))
            adjudicated.append({
                "defect_type": dtype,
                "severity": severity,
                "description": issue,
                "adjudicator": "deterministic_gate" if att.get("check_type") == "deterministic_calculation" else "blinded_checker",
                "adjudicated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

    # If blocked by required inputs
    contract = node.input_artifacts.get("task_contract", {})
    blocked_by = contract.get("blocked_by", [])
    if blocked_by:
        for blocker in blocked_by:
            adjudicated.append({
                "defect_type": "missing_required_input",
                "severity": "critical",
                "description": f"Unresolved required input: {blocker}",
                "adjudicator": "engine_supervisor",
                "adjudicated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

    # If general error trace exists
    if getattr(node, "error_trace", None):
        dtype, severity = classify_defect_from_feedback(node.error_trace)
        adjudicated.append({
            "defect_type": dtype,
            "severity": severity,
            "description": str(node.error_trace),
            "adjudicator": "engine_supervisor",
            "adjudicated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

    meta = deepcopy(metadata or {})
    if run_id:
        meta["run_id"] = run_id
    meta["node_status"] = node.status.value
    meta["retry_count"] = getattr(node, "retry_count", 0)

    return FailurePacket(
        original_intent=goal,
        task_id=node.id,
        task_objective=node.title or contract.get("objective", ""),
        failure_kind=failure_kind,
        task_brief=task_brief,
        source_snapshots=sources,
        attempts=attempts,
        adjudicated_defects=adjudicated,
        metadata=meta,
    )


def capture_from_engine_state(state: Dict[str, Any], *, run_id: Optional[str] = None,
                              error: Optional[Exception | str] = None) -> List[FailurePacket]:
    """Capture failure packets from an engine checkpoint or execution state."""
    from task_graph import TaskGraph, TaskStatus

    goal = state.get("goal", "")
    task_brief = state.get("task_brief")
    meta = {
        "model": state.get("model"),
        "effort": state.get("effort"),
        "backend": state.get("backend"),
        "phase": state.get("phase"),
        "run_id": run_id or state.get("session_id"),
    }
    if error:
        meta["exception_type"] = type(error).__name__ if isinstance(error, Exception) else "Error"
        meta["exception_message"] = str(error)

    packets: List[FailurePacket] = []
    graph_dict = state.get("graph")
    if graph_dict:
        graph = TaskGraph.from_dict(graph_dict)
        for node in graph.nodes.values():
            if node.status != TaskStatus.COMPLETED:
                pkt = capture_from_node(node, goal=goal, task_brief=task_brief,
                                        run_id=run_id, metadata=meta)
                if pkt:
                    packets.append(pkt)

    return packets


def capture_from_report_file(path: Path | str, store: Optional[FailureStore] = None) -> List[FailurePacket]:
    """Ingest quarantined findings, rejected outputs, and check failures from a report JSON."""
    report_path = Path(path).resolve()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    goal = data.get("goal", "")
    task_brief = data.get("task_brief")
    run_id = data.get("metadata", {}).get("run_id") or report_path.stem
    target_store = store or FailureStore()

    packets: List[FailurePacket] = []

    # 1. Quarantined findings in publication_view
    pub_view = data.get("publication_view", {})
    for task_id, view_entry in pub_view.items():
        if view_entry.get("status") == "quarantined":
            reason = view_entry.get("reason", "Quarantined finding")
            dtype, sev = classify_defect_from_feedback(reason)
            pkt = FailurePacket(
                original_intent=goal,
                task_id=task_id,
                task_objective=f"Quarantined finding in task {task_id}",
                failure_kind="result_check_failure",
                task_brief=task_brief,
                source_snapshots=view_entry.get("sources", []),
                attempts=[{"attempt": 1, "feedback": reason, "issues": [reason]}],
                adjudicated_defects=[{
                    "defect_type": dtype,
                    "severity": sev,
                    "description": reason,
                    "adjudicator": "engine_supervisor",
                    "adjudicated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }],
                metadata={"source_file": str(report_path), "run_id": run_id, "quarantine_status": "quarantined"},
            )
            ingested, _ = target_store.ingest(pkt)
            packets.append(ingested)

    # 2. Final answer check failure
    final_check = data.get("final_answer_check", {})
    if isinstance(final_check, dict) and final_check.get("verdict") == "FAIL":
        issues = final_check.get("issues", ["Final answer consistency check failed"])
        defects = []
        for issue in issues:
            dtype, sev = classify_defect_from_feedback(issue)
            defects.append({
                "defect_type": dtype,
                "severity": sev,
                "description": issue,
                "adjudicator": "blinded_checker",
                "adjudicated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
        pkt = FailurePacket(
            original_intent=goal,
            task_id="synthesis.final_check",
            task_objective="Final answer consistency and entailment check",
            failure_kind="assembly_failure",
            task_brief=task_brief,
            attempts=[{"attempt": 1, "feedback": "\n".join(issues), "issues": issues}],
            adjudicated_defects=defects,
            metadata={"source_file": str(report_path), "run_id": run_id},
        )
        ingested, _ = target_store.ingest(pkt)
        packets.append(ingested)

    return packets


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Mímir failure packet capture and deduplication store")
    parser.add_argument("--store", type=Path, help="Path to failure-packets.jsonl")
    parser.add_argument("--list", action="store_true", help="List all stored failure packets")
    parser.add_argument("--stats", action="store_true", help="Print summary statistics")
    parser.add_argument("--inspect", type=str, help="Inspect packet JSON by ID")
    parser.add_argument("--ingest", type=Path, help="Ingest failures from checkpoint.json or report.json")
    parser.add_argument("--adjudicate", type=str, help="Packet ID to adjudicate")
    parser.add_argument("--defect-type", choices=sorted(VALID_DEFECT_TYPES), help="Defect type for adjudication")
    parser.add_argument("--severity", choices=sorted(VALID_SEVERITIES), default="major")
    parser.add_argument("--description", type=str, help="Defect description")
    parser.add_argument("--resolution", choices=sorted(VALID_RESOLUTION_STATUSES), help="Update resolution status")
    args = parser.parse_args()

    store = FailureStore(store_path=args.store)

    if args.ingest:
        p = Path(args.ingest).resolve()
        data = json.loads(p.read_text(encoding="utf-8"))
        if "graph" in data:
            pkts = capture_from_engine_state(data, run_id=p.stem)
            for pkt in pkts:
                store.ingest(pkt)
            print(f"Ingested {len(pkts)} failure packets from checkpoint {p.name}")
        else:
            pkts = capture_from_report_file(p, store=store)
            print(f"Ingested {len(pkts)} failure packets from report {p.name}")

    elif args.adjudicate:
        if not args.defect_type or not args.description:
            parser.error("--adjudicate requires --defect-type and --description")
        pkt = store.adjudicate(args.adjudicate, defect_type=args.defect_type,
                              severity=args.severity, description=args.description,
                              resolution_status=args.resolution)
        print(f"Adjudicated packet {pkt.packet_id}: {args.defect_type} ({args.severity})")

    elif args.inspect:
        pkt = store.get(args.inspect)
        if not pkt:
            print(f"Packet not found: {args.inspect}")
            return
        print(json.dumps(pkt.to_dict(), indent=2, ensure_ascii=False))

    elif args.stats:
        pkts = store.list_packets()
        kinds = {}
        defects = {}
        statuses = {}
        for p in pkts:
            kinds[p.failure_kind] = kinds.get(p.failure_kind, 0) + 1
            statuses[p.resolution_status] = statuses.get(p.resolution_status, 0) + 1
            for d in p.adjudicated_defects:
                dt = d.get("defect_type", "unknown")
                defects[dt] = defects.get(dt, 0) + 1
        stats = {
            "total_packets": len(pkts),
            "by_kind": kinds,
            "by_defect_type": defects,
            "by_resolution_status": statuses,
        }
        print(json.dumps(stats, indent=2))

    elif args.list:
        pkts = store.list_packets()
        print(f"Stored Failure Packets ({len(pkts)} total):")
        for p in pkts:
            d_types = [d.get("defect_type") for d in p.adjudicated_defects]
            print(f"  [{p.packet_id[:12]}] kind={p.failure_kind} task={p.task_id} "
                  f"defects={d_types} occurrences={p.occurrences} status={p.resolution_status}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
