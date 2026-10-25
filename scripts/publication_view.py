"""Publication status overlays preserve immutable worker records."""
from copy import deepcopy
from source_store import identity


def build_publication_view(context, quarantines=()):
    results = {**context.get("findings", {}), **context.get("checks", {}).get("critic_findings", {})}
    selected = {}
    for entry in quarantines:
        task_id, reason = entry["task_id"], entry["reason"]
        if task_id not in results or task_id in selected or not reason.strip():
            raise ValueError("Publication quarantine requires a unique existing task and reason")
        selected[task_id] = reason
    view = {}
    for task_id, result in results.items():
        entry = {"status": "quarantined" if task_id in selected else "accepted",
                 "original_hash": identity(result)}
        if task_id in selected:
            entry.update(reason=selected[task_id], gaps=deepcopy(result.get("gaps", [])) if isinstance(result, dict) else [],
                         sources=deepcopy(result.get("sources", [])) if isinstance(result, dict) else [])
        else:
            entry["result"] = deepcopy(result)
        view[task_id] = entry
    return view
