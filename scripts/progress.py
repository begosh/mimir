"""Observed run activity presented as chat narration, separate from diagnostics.

No inference calls, worker reasoning or claims of independent verification.
The durable journal remains available when a caller explicitly requests events.
"""
from __future__ import annotations


def _activity(event: dict) -> str | None:
    kind = event.get("event")
    node = event.get("node_id")
    if kind == "task_submitted":
        return {
            "evidence": "Mímir draws from the well: the evidence specialist is checking primary sources.",
            "alternatives": "A second specialist weighs the alternatives and their practical tradeoffs.",
            "critique": "The findings enter Mímir's forge. The critic is challenging both specialist reports.",
            "research": "Mímir draws from the well: the specialist is investigating the question and its sources.",
        }.get(node, "Mímir has dispatched a specialist to investigate a part of the question.")
    if kind == "task_completed":
        return {
            "evidence": "The evidence specialist has returned findings and remaining gaps.",
            "alternatives": "The alternatives specialist has returned its assessment and tradeoffs.",
            "critique": "The critic has returned its challenges and corrections. The findings are ready for synthesis.",
            "research": "The specialist has returned findings and remaining gaps for the report.",
        }.get(node, "A specialist has returned findings for the review.")
    return {
        "scout_querying": "Mímir casts the net: gathering public sources for the investigation.",
        "research_completed": "The source search has returned. Mímir is preparing the investigation.",
        "graph_ready": "The runes are set: the investigation plan is ready.",
        "reflection_started": "Mímir brings the findings together, preserving the critic's corrections and unanswered questions.",
        "reflection_completed": "Mímir's synthesis has returned; the report is being prepared.",
        "artifacts_ready": "The report is written. Mímir is finishing cleanup before declaring the run complete.",
        "task_failed": "A specialist could not complete its work. Successful results are being preserved.",
        "configuration_required": "The investigation needs a configuration correction before it can continue.",
        "publication_recovered": "Mímir has recovered the saved report; cleanup is still being confirmed.",
    }.get(kind)


def present_progress(record: dict, events: list[dict], *, include_events: bool = False) -> dict:
    """Return compact narration and cursor controls from observed durable state."""
    status, phase = record["status"], record["phase"]
    # Sequence alone is not a meaningful change: heartbeat events are liveness.
    updates = [{"sequence": e["sequence"], "text": text}
               for e in events if (text := _activity(e)) is not None]
    latest = record.get("latest_event") or {}
    if status == "queued":
        narration = {
            "plan": "Mímir is preparing the investigation and its evidence needs.",
            "execute": "Mímir is preparing to dispatch the specialists.",
            "synthesize": "Mímir is preparing to bring the findings and critique together.",
        }.get(phase, "Mímir is preparing the investigation.")
    elif status == "completed":
        narration = {
            "plan": "The runes are set. The plan is complete and ready for investigation.",
            "execute": "The specialist work and critique are complete. Mímir is ready to assemble the report.",
            "synthesize": "Mímir's report is ready. The investigation and cleanup have completed; the findings and gaps can now be read.",
        }.get(phase, "Mímir has completed this phase.")
    elif status == "cancelling":
        narration = "Mímir is recalling the specialists and waiting for cleanup. Completed findings are being preserved."
    elif status in {"cancelled", "interrupted", "failed"}:
        narration = {
            "cancelled": "The investigation has stopped. Completed checkpoints are preserved.",
            "interrupted": "The previous investigation was interrupted. Its saved checkpoints remain available for recovery.",
            "failed": "The investigation could not finish. Saved findings are preserved; the reported failure needs attention.",
        }[status]
    elif phase == "plan":
        narration = ("Mímir is gathering public sources. No new findings have returned yet."
                     if latest.get("phase") == 1 else "Mímir is arranging the investigation and its evidence needs.")
    elif phase == "synthesize":
        narration = (_activity(latest) or
                     "Mímir is bringing the findings and critique together. The final report is still being prepared.")
    else:
        narration = _activity(latest)
        if narration is None:
            done, submitted = latest.get("completed_tasks", 0), latest.get("submitted_tasks", 0)
            if submitted and done < submitted:
                narration = (f"Mímir keeps watch: {done} of {submitted} dispatched specialists have returned. "
                             "The remaining work is still underway; no new findings have arrived.")
            else:
                narration = "Mímir keeps watch over the investigation. No new findings have returned yet."
    result = {key: record.get(key) for key in
              ("run_id", "phase", "status", "completed_phase", "recoverable_phases", "next_sequence", "has_more")}
    result.update(narration=narration, updates=updates,
                  elapsed_seconds=latest.get("elapsed_seconds", 0))
    if record.get("error"):
        result["error"] = record["error"]
    if include_events:
        result.update(events=events, latest_event=latest)
    return result
