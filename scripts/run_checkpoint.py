"""Deep module for RunCheckpoint persistence, phase-transition verification, and artifact publication."""
from __future__ import annotations

from contextlib import contextmanager
import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional

from backend import has_worker_result
from mimir_config import ConfigurationRequired
from task_graph import TaskGraph, TaskStatus


class RunCheckpoint:
    """Authoritative seam for run checkpoint state, resume verification, and atomic artifact publication."""

    @staticmethod
    @contextmanager
    def lock(state_file: str):
        """One phase owns a checkpoint at a time, including its model calls."""
        from run_locks import ownership

        target = Path(state_file).resolve()
        with ownership(target.with_name(target.name + ".lock")):
            yield

    @staticmethod
    def write_artifact(target: Path, content: str) -> None:
        """Atomically write UTF-8 text to target via a sibling temp file with Windows lock retry."""
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            # Windows scanners can temporarily open a just-written destination
            # without delete sharing. Retry only that transient replace failure.
            for attempt in range(5):
                try:
                    os.replace(temporary, target)
                    break
                except PermissionError:
                    if os.name != "nt" or attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    @staticmethod
    def save(state: Dict[str, Any], state_file: str) -> None:
        """Replace a complete checkpoint atomically, keeping the previous one on error."""
        target = Path(state_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: value
            for key, value in state.items()
            if key not in {"task_graph_obj", "blackboard"}
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(
                    payload,
                    stream,
                    indent=2,
                    ensure_ascii=False,
                    allow_nan=False,
                )
            for attempt in range(5):
                try:
                    os.replace(temporary, target)
                    break
                except PermissionError:
                    if os.name != "nt" or attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    @staticmethod
    def validate_output_paths(state_file: str, output_path: str) -> None:
        """Verify that report, JSON sidecar, checkpoint, and lock paths are distinct."""
        state_path = Path(state_file).resolve()
        paths = [
            Path(output_path).resolve(),
            Path(output_path).with_suffix(".json").resolve(),
            state_path,
            state_path.with_name(state_path.name + ".lock"),
        ]
        if len(set(paths)) != len(paths):
            raise ValueError(
                "Report, JSON sidecar and state paths must be distinct; use a .md report path."
            )

    @staticmethod
    def load(state_file: str, phase: str) -> Dict[str, Any]:
        """Load and validate checkpoint state for resuming into `execute` or `synthesize`."""
        target = Path(state_file)
        if not target.is_file():
            raise FileNotFoundError(
                f"State file not found at {target}. Run --phase plan first."
            )
        state = json.loads(target.read_text(encoding="utf-8-sig"))
        if (
            not isinstance(state, dict)
            or type(state.get("version")) is not int
            or state["version"] != 1
        ):
            raise ValueError("Unsupported Mimir state version.")
        if not isinstance(state.get("goal"), str) or not state["goal"].strip():
            raise ValueError("State requires a nonempty objective.")
        expected = (
            {"planned", "executing"}
            if phase == "execute"
            else {"executed", "synthesized"}
        )
        if state.get("phase") not in expected:
            raise ValueError(
                f"Cannot {phase} state in phase {state.get('phase')!r}."
            )
        graph = TaskGraph.from_dict(state.get("graph", {}))
        valid, message = graph.validate_acyclic_and_integrity()
        if not graph.nodes or not valid:
            raise ValueError(f"Invalid persisted task graph: {message}")
        if phase == "execute":
            retained = state.get("completed_data", {})
            if not isinstance(retained, dict) or not set(retained).issubset(
                graph.nodes
            ):
                raise ValueError("Invalid retained task results.")
            for node in graph.nodes.values():
                if (
                    node.status == TaskStatus.COMPLETED
                    and node.id not in retained
                ):
                    raise ValueError(
                        "Completed task is missing its retained result."
                    )
                if node.status != TaskStatus.COMPLETED:
                    node.status = TaskStatus.PENDING
                    node.error_trace = None
            state["graph"] = graph.to_dict()
        if phase == "synthesize":
            results = state.get("completed_data")
            if not isinstance(results, dict) or set(results) != set(graph.nodes):
                raise ValueError(
                    "Synthesis requires results for every planned task."
                )
            if any(
                not isinstance(result, dict) or "result" not in result
                for result in results.values()
            ):
                raise ValueError("Invalid persisted task results.")
            if any(
                not has_worker_result(result["result"])
                for result in results.values()
            ):
                raise ValueError(
                    "Synthesis requires usable output for every planned task."
                )
            if any(
                node.status != TaskStatus.COMPLETED
                for node in graph.nodes.values()
            ):
                if state.get("mode"):
                    raise ConfigurationRequired(
                        "Synthesis requires every planned task to be completed."
                    )
            for node_id, result in results.items():
                if state.get("mode") and not all(
                    result.get(key)
                    for key in (
                        "result_hash",
                        "evidence_hash",
                        "input_fingerprint",
                    )
                ):
                    raise ConfigurationRequired(
                        "Retained task is missing its identity records; synthesis cannot consume it."
                    )
                if result.get("result_hash"):
                    content = json.dumps(
                        result["result"],
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                    if (
                        hashlib.sha256(content.encode()).hexdigest()
                        != result["result_hash"]
                    ):
                        raise ConfigurationRequired(
                            "Retained result identity changed; synthesis cannot consume it."
                        )
                    raw = result.get("raw_response")
                    if (
                        not isinstance(raw, str)
                        or hashlib.sha256(raw.encode()).hexdigest()
                        != result.get("evidence_hash")
                    ):
                        raise ConfigurationRequired(
                            "Retained raw evidence identity changed; synthesis cannot consume it."
                        )
        return state

    @staticmethod
    def recover_published_artifacts(
        state: Dict[str, Any],
        final_out_path: str,
        total_elapsed: float,
        ui: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Recover previously synthesized artifacts if their paths and SHA-256 digests match."""
        publication = state.get("publication")
        if state.get("phase") != "synthesized" or not isinstance(
            publication, dict
        ):
            return None
        report = Path(final_out_path).resolve()
        if str(report) != publication.get("report_path"):
            raise ConfigurationRequired(
                "Recovery must use the published report path; start a new run to change it."
            )
        for path, key in (
            (report, "report_hash"),
            (report.with_suffix(".json"), "sidecar_hash"),
        ):
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest()
                != publication.get(key)
            ):
                raise ConfigurationRequired(
                    "Published artifact identity changed; recovery cannot silently replace it."
                )
        completed_data = state.get("completed_data", {})
        data = dict(
            report_path=str(report),
            json_path=str(report.with_suffix(".json")),
            task_count=len(completed_data),
            duration_seconds=state.get("total_elapsed_seconds", total_elapsed),
            recovered=True,
        )
        if ui is not None:
            ui.emit("publication_recovered", **data)
            ui.completion = ("run_completed", data)
        return state

    @staticmethod
    def verify_synthesis_readiness(
        state: Dict[str, Any], swarm: Optional[Any] = None
    ) -> None:
        """Verify completed task presence, current result_gate_policy, and retained task validity before synthesis."""
        completed_data = state.get("completed_data", {})
        if not completed_data:
            raise ValueError(
                "No completed worker tasks found in state file. Run --phase execute first."
            )
        if state.get("mode"):
            from admission_and_assembly_gate import result_gate_policy

            policy = result_gate_policy()
            nodes = TaskGraph.from_dict(state["graph"]).nodes
            if any(
                nodes[nid].input_artifacts.get("result_gate") != policy
                or data.get("result_check", {}).get("policy") != policy
                for nid, data in completed_data.items()
            ):
                raise ConfigurationRequired(
                    "Publication requires current material-finding checks for every task; replan explicitly."
                )
        if state.get("mode") and swarm is not None:
            from scheduler import validate_retained

            validate_retained(
                TaskGraph.from_dict(state["graph"]), swarm, completed_data
            )

    @staticmethod
    def compute_usage_summary(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate model call and token breakdown telemetry for the JSON sidecar."""
        usage: Dict[str, Any] = {
            "model_calls": len(calls),
            "known_tokens": sum(c.get("tokens_used", 0) or 0 for c in calls),
            "usage_complete": bool(calls)
            and all((c.get("tokens_used") or 0) > 0 for c in calls),
            "calls": calls,
            "billed_cost": None,
        }
        usage["worker_calls"] = len(calls)
        usage["token_scope"] = (
            "Cumulative reported API/runtime usage, including cached input; not unique context or verified billed tokens. Reported-token thresholds may overshoot in-flight work."
        )
        detailed_calls = [c for c in calls if c.get("usage_details")]
        usage["calls_with_token_breakdown"] = len(detailed_calls)
        usage["known_token_breakdown"] = {
            name: sum(c["usage_details"].get(name, 0) for c in detailed_calls)
            for name in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
            )
            if any(name in c["usage_details"] for c in detailed_calls)
        }
        usage["model_calls_scope"] = (
            "Adapter invocations, not provider inference requests; native tool continuations may make multiple model requests."
        )
        return usage

    @staticmethod
    def publish_artifacts(
        state: Dict[str, Any],
        *,
        final_out_path: str,
        hardened_solution: Any,
        reflection: Any,
        published_data: Dict[str, Any],
        combined_critique: str,
        red_team_critiques: List[str],
        memory: Any,
        swarm: Any,
        backend_display: str,
        active_backend: str,
        active_model: str,
        active_effort: str,
        total_elapsed: float,
        synthesis_started_at: float,
        is_en: bool,
        state_file: Optional[str] = None,
        ui: Optional[Any] = None,
    ) -> tuple[Path, Path, str, bool]:
        """Render and atomically publish Markdown report and JSON sidecar, record quarantined failures, and stamp checkpoint."""
        from evidence_provenance import EvidenceProvenance

        goal = state.get("goal", "")
        completed_data = state.get("completed_data", {})
        intel_context = state.get("intel_context", "")
        publication_view = state.get("publication_view", {})

        hardened_str = (
            json.dumps(hardened_solution, indent=2, ensure_ascii=False)
            if isinstance(hardened_solution, (dict, list))
            else str(hardened_solution)
        )
        reflection_str = (
            json.dumps(reflection, indent=2, ensure_ascii=False)
            if isinstance(reflection, (dict, list))
            else str(reflection)
        )

        mimir_persona_intro = (
            "> *Mímir records the worker findings and supplied checks. "
            "Source retrieval, model critique, and output hashes do not independently verify factual claims.*\n\n"
        )
        report_lines = [
            f"# M Í M I R // Review: {' '.join(goal.split())[:180]}",
            f"\n**Produced by:** Mímir Autonomous Swarm ({backend_display} / {active_model}) | **Time:** {total_elapsed:.1f}s | **Tasks Completed:** {len(completed_data)}",
            "\n---\n",
            mimir_persona_intro,
            "## 1. Executive Summary & Reviewed Findings",
            hardened_str,
            "\n---\n",
            "## 2. Assembly notes and limitations",
            f"**Assembly Notes:**\n{reflection_str}\n" if reflection_str else "",
            f"**Identified Pitfalls:**\n{combined_critique}\n"
            if combined_critique
            else "",
            "\n---\n",
            "## 3. Empirical Intelligence (Omni-Channel Evidence)",
            intel_context
            if intel_context
            else "No external intelligence gathered.",
            "\n---\n",
            "## 4. Atomic Task Results per Agent (with Evidence Contracts)",
        ]

        for node_id, data in completed_data.items():
            h = data.get("evidence_hash", "")
            h_str = f" [sha256:{h}]" if h else ""
            report_lines.append(
                f"### Node [{node_id}] - {data.get('role', 'Agent')}: {data.get('title', 'Task' if is_en else 'Uppgift')}{h_str}"
            )
            entry = publication_view.get(node_id, {})
            if entry.get("status") == "quarantined":
                report_lines.append(
                    "Publication: **quarantined**. "
                    + entry["reason"]
                    + " Original assertions retained as diagnostic records in the sidecar/checkpoint.\n"
                )
                report_lines.append(
                    "Sources and remaining gaps:\n```json\n"
                    + json.dumps(
                        {"sources": entry["sources"], "gaps": entry["gaps"]},
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n```\n"
                )
                continue
            if data.get("result_check"):
                rejected_count = sum(
                    a.get("status") != "PASS"
                    for a in data.get("result_attempts", [])
                )
                report_lines.append(
                    "Admission: model PASS; independent factual verification not performed. "
                    "This is the accepted task version; final publication checks also cover the appendix. "
                    f"Rejected attempts quarantined in the checkpoint: {rejected_count}.\n"
                )
            node_res = data.get("result", "")
            node_res_str = (
                json.dumps(node_res, indent=2, ensure_ascii=False)
                if isinstance(node_res, (dict, list))
                else str(node_res)
            )
            report_lines.append(f"```text\n{node_res_str}\n```\n")

        full_report = "\n".join([str(x) for x in report_lines])
        out_path = Path(final_out_path)
        json_path = out_path.with_suffix(".json")
        blackboard = state.get("blackboard")
        bb_artifacts = (
            blackboard.artifacts
            if blackboard
            else state.get("blackboard_artifacts", {})
        )
        bb_hashes = (
            list(blackboard.verified_evidence_store.keys())
            if blackboard
            else state.get("verified_evidence_hashes", [])
        )

        research = EvidenceProvenance.audit_publication(
            hardened_str,
            published_data,
            scout_gaps=state.get("intel_brief", {}).get("retrieval_gaps", []),
        )
        calls = list(getattr(swarm, "usage_calls", []))
        usage = RunCheckpoint.compute_usage_summary(calls)

        research_lines = [
            "\n## Evidence coverage and limitations\n",
            f"Record coverage: **{research['coverage']}**. Independent factual validation: **not performed**.\n",
        ]
        for source in research["sources"]:
            research_lines.append(
                f"- [{source['id']}] {source['locator']} ({source['retrieval_type']}; retrieved {source['retrieved_at'] or 'time unavailable'})\n  Supporting excerpt: {source['support_excerpt']}"
            )
        for gap in research["gaps"] + research["issues"]:
            research_lines.append(
                f"- Gap [{gap['task_id']}]: {gap['description']}"
            )
        for locator in research["final_reference_audit"][
            "missing_supporting_locators"
        ]:
            research_lines.append(
                f"- Supporting source omitted from the synthesis text: {locator}"
            )
        for unbound in research["final_reference_audit"].get(
            "unbound_references", []
        ):
            research_lines.append(
                f"- Unbound reference in synthesis text: {unbound}"
            )
        ref_audit_status = (
            "**passed**"
            if research["final_reference_audit"]["reference_presence_passed"]
            else "**partial**"
        )
        research_lines.append(
            f"- Final reference audit: {ref_audit_status} (String presence and ID resolution; not independent verification or citation entailment)."
        )

        full_report += "\n" + "\n".join(research_lines)

        json_payload = {
            "goal": goal,
            "persona": "Mímir",
            "backend": backend_display,
            "model": active_model,
            "worker_effort": active_effort,
            "elapsed_seconds": total_elapsed,
            "intel_brief": state.get("intel_brief", {}),
            "task_brief": state.get("task_brief"),
            "task_brief_origin": state.get("task_brief_origin", "legacy"),
            "retrieval_policy": state.get("retrieval_policy", "legacy"),
            "task_results": completed_data,
            "publication_view": publication_view,
            "task_results_scope": "Original immutable diagnostic records; publication_view governs released task assertions.",
            "reflection": reflection,
            "hardened_solution": hardened_solution,
            "synthesis_result": state.get("synthesis_result"),
            "synthesis_context": state.get("synthesis_context"),
            "assembly_history": state.get("assembly_history"),
            "final_answer_check": state.get("final_answer_check"),
            "blackboard_artifacts": bb_artifacts,
            "verified_evidence_hashes": bb_hashes,
            "output_identity_hashes": bb_hashes,
            "evidence_verification": "Output identity only; factual correctness has not been independently verified.",
            "memory_file": str(memory.memory_path),
            "memory_mode": state.get("memory_mode", "read"),
            "learning_candidate_file": str(
                getattr(memory, "candidate_path", memory.memory_path)
            ),
            "execution_policy": {
                "mode": state.get("mode", "legacy"),
                "max_tasks": state.get("max_tasks"),
                "max_context_chars": state.get("max_context_chars"),
                "research_program": state.get("research_program", "native"),
                "research_budget": (state.get("research_config") or {}).get(
                    "budget"
                ),
            },
            "research": research,
            "usage": usage,
            "budget_status": getattr(swarm, "budget_status", None),
            "research_identity": state.get("research_identity"),
            "captured_sources": [
                {k: v for k, v in r.items() if k != "text"}
                for r in (state.get("research_config") or {}).get("sources", [])
            ],
        }
        json_content = json.dumps(
            json_payload, indent=2, ensure_ascii=False, allow_nan=False
        )
        RunCheckpoint.write_artifact(json_path, json_content)
        RunCheckpoint.write_artifact(out_path, full_report)

        quarantined_tasks = [
            t
            for t, v in publication_view.items()
            if v.get("status") == "quarantined"
        ]
        if quarantined_tasks:
            try:
                from failure_store import FailurePacket, FailureStore

                failure_store = FailureStore(
                    store_path=state.get("failure_store_path"),
                    workspace=state.get("workspace"),
                )
                for q_id in quarantined_tasks:
                    q_entry = publication_view[q_id]
                    pkt = FailurePacket(
                        original_intent=goal,
                        task_id=q_id,
                        task_objective=f"Quarantined assertion in task {q_id}",
                        failure_kind="result_check_failure",
                        attempts=[
                            {
                                "attempt": 1,
                                "feedback": q_entry.get("reason", ""),
                                "issues": [q_entry.get("reason", "")],
                            }
                        ],
                        adjudicated_defects=[
                            {
                                "defect_type": "unsupported_claim",
                                "severity": "major",
                                "description": q_entry.get(
                                    "reason", "Quarantined assertion"
                                ),
                                "adjudicator": "engine_supervisor",
                                "adjudicated_at": datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat(),
                            }
                        ],
                        metadata={
                            "run_id": state.get("session_id"),
                            "quarantine_status": "quarantined",
                        },
                    )
                    failure_store.ingest(pkt)
            except Exception as exc:
                if ui is not None:
                    ui.emit("failure_store_error", error=str(exc))

        state.update(
            phase="synthesized",
            report_path=str(out_path.resolve()),
            backend=active_backend,
            model=active_model,
            effort=active_effort,
            synthesis_duration_seconds=round(
                time.monotonic() - synthesis_started_at, 2
            ),
        )
        state["usage_calls"] = calls
        state["total_elapsed_seconds"] = total_elapsed
        state["publication"] = {
            "report_path": str(out_path.resolve()),
            "report_hash": hashlib.sha256(out_path.read_bytes()).hexdigest(),
            "sidecar_hash": hashlib.sha256(json_path.read_bytes()).hexdigest(),
        }
        # Commit publication identity before any optional learning write. A crash
        # after this point recovers artifacts without another reflective call.
        if state_file:
            RunCheckpoint.save(state, state_file)

        memory_saved = memory.record_learning(
            goal=goal,
            hardened_solution_snippet=hardened_str,
            reflection_notes=reflection_str,
            red_team_traps=red_team_critiques,
            report_path=str(out_path.resolve()),
        )
        mode = state.get("memory_mode", "read")
        if ui is not None:
            ui.emit(
                (
                    "memory_recorded"
                    if memory_saved
                    else "memory_write_failed"
                )
                if mode == "write"
                else "memory_write_skipped",
                memory_file=str(memory.memory_path),
                candidate_file=str(
                    getattr(memory, "candidate_path", memory.memory_path)
                ),
                mode=mode,
            )
        state["learning_candidate_saved"] = (
            memory_saved if mode == "write" else False
        )
        if state_file:
            RunCheckpoint.save(state, state_file)
        return out_path, json_path, hardened_str, memory_saved
