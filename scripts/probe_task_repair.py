"""Run one bounded task repair followed by an independent simplicity review.

This is a planning experiment, not scheduler retry or automatic DAG mutation.
Inputs and raw completions remain in the explicitly supplied artifact directory.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time

from backend import create_swarm_backend
from engine import _write_artifact
from invocation_broker import InvocationBroker
from recursive_planner import RecursivePlanner, OPERATIONS


def validate_repair(result, context):
    if not isinstance(result, dict) or set(result) != {"action", "reason", "tasks", "missing_inputs"}:
        raise ValueError("Repair response must contain action, reason, tasks and missing_inputs")
    action, tasks = result["action"], result["tasks"]
    if action not in {"REPHRASE", "SPLIT", "BLOCKED", "STOP"}:
        raise ValueError("Unknown repair action")
    if not isinstance(result["reason"], str) or not result["reason"].strip():
        raise ValueError("Repair needs a reason")
    if not isinstance(tasks, list) or not isinstance(result["missing_inputs"], list):
        raise ValueError("Tasks and missing_inputs must be arrays")
    if action in {"BLOCKED", "STOP"}:
        if tasks or (action == "BLOCKED" and not result["missing_inputs"]):
            raise ValueError("Blocked/stopped repairs cannot return executable tasks")
        return
    if (action == "REPHRASE" and len(tasks) != 1) or (action == "SPLIT" and not 2 <= len(tasks) <= 4):
        raise ValueError("Invalid repair child count")
    if len(tasks) > context["remaining_budget"]["replacement_leaf_slots"]:
        raise ValueError("Repair exceeds remaining leaf slots")
    from jsonschema import validate
    properties = {
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,19}$"},
        "objective": {"type": "string", "minLength": 1, "maxLength": 500},
        "atomic": {"type": "boolean"}, "operation": {"enum": [*OPERATIONS, "split"]},
        **{key: {"type": "array", "maxItems": 4, "items": {"type": "string", "minLength": 1, "maxLength": 300}}
           for key in ("inputs", "blocked_by", "dependencies")},
        **{key: {"type": "string", "maxLength": 400} for key in ("expected_output", "acceptance_check")},
        "max_input_items": {"type": "integer", "minimum": 0, "maximum": 2},
        "max_output_words": {"type": "integer", "minimum": 0, "maximum": 150}}
    ids = set()
    for task in tasks:
        validate(task, {"type": "object", "additionalProperties": False,
                        "required": list(properties), "properties": properties})
        if task["id"] in ids:
            raise ValueError("Duplicate repair id")
        ids.add(task["id"])
        if task["atomic"]:
            if task["operation"] == "split" or not 1 <= len(task["inputs"]) <= task["max_input_items"] or not task["max_output_words"]:
                raise ValueError("Invalid repair leaf operation or input/output bound")
            if not task["expected_output"].strip() or not task["acceptance_check"].strip():
                raise ValueError("Repair leaf needs output and check")
        elif task["operation"] != "split" or task["max_input_items"] != 0:
            raise ValueError("Invalid non-executable repair grouping")
        if not task["atomic"] and context["remaining_budget"]["current_depth"] >= context["remaining_budget"]["max_depth"]:
            raise ValueError("Repair has broad task at depth limit")
    from graphlib import TopologicalSorter
    if any(not set(task["dependencies"]).issubset(ids) for task in tasks):
        raise ValueError("Repair dependencies must reference siblings")
    tuple(TopologicalSorter({task["id"]: task["dependencies"] for task in tasks}).static_order())


async def probe(target):
    target = Path(target)
    context = json.loads((target / "input.json").read_text(encoding="utf-8"))
    if (target / "probe.json").exists():
        raise ValueError("This probe already has results; use a new artifact directory")
    native = create_swarm_backend("codex", context["model"], max_concurrency=1,
                                  effort=context["effort"], timeout_seconds=180, worker_transport="native")
    broker = InvocationBroker(native, journal=target / "operations.jsonl")
    result = {"status": "repairing", "repair": None, "review": None}

    def snapshot(trace):
        _write_artifact(target / "probe.json", json.dumps(
            {**result, "planning": trace, "usage_calls": broker.usage_calls}, ensure_ascii=False, indent=2))
        for i, call in enumerate(trace["calls"], 1):
            _write_artifact(target / f"prompt-{i}.txt", call["prompt"])

    budget = context["remaining_budget"]
    planner = RecursivePlanner(broker, budget={"max_calls": min(2, budget["max_calls"]),
                                              "max_seconds": budget["max_seconds"]}, on_checkpoint=snapshot)
    planner.deadline = time.monotonic() + budget["max_seconds"]
    started = time.monotonic()
    prompt_dir = Path(__file__).resolve().parents[1] / "prompts"
    try:
        template = (prompt_dir / "TASK_REPAIR.txt").read_text(encoding="utf-8")
        repair = await planner.ask(template.replace("{{repair_context_json}}", json.dumps(context, ensure_ascii=False)),
                                   "Mimir-Task-Repairer", field="repair_json", parent=context["task_contract"]["id"])
        result["repair"] = repair
        validate_repair(repair, context)
        print(json.dumps({"repair_action": repair["action"], "children": len(repair["tasks"])}), flush=True)
        if repair["tasks"]:
            result["status"] = "reviewing"
            review_context = {**context, "proposed_repair": repair,
                              "inherited_prerequisites": context["task_contract"]["dependencies"]}
            template = (prompt_dir / "TASK_SIMPLICITY_REVIEW.txt").read_text(encoding="utf-8")
            review = await planner.ask(template.replace("{{review_context_json}}", json.dumps(review_context, ensure_ascii=False)),
                                       "Mimir-Simplicity-Reviewer", field="review_json", parent=context["task_contract"]["id"])
            result["review"] = review
            if not isinstance(review, dict) or set(review) != {"tasks", "coverage_preserved", "coverage_gaps"}:
                raise ValueError("Invalid simplicity review fields")
            verdicts = review["tasks"]
            if not isinstance(verdicts, list) or len(verdicts) != len(repair["tasks"]):
                raise ValueError("Reviewer omitted or duplicated tasks")
            if {v["id"] for v in verdicts} != {t["id"] for t in repair["tasks"]}:
                raise ValueError("Review ids differ from repair ids")
            if any(v.get("decision") not in {"ACCEPT", "SPLIT", "BLOCKED"} or not v.get("reason") for v in verdicts):
                raise ValueError("Invalid review verdict")
            if type(review["coverage_preserved"]) is not bool or not isinstance(review["coverage_gaps"], list):
                raise ValueError("Invalid coverage verdict")
            result["accepted_by_reviewer"] = review["coverage_preserved"] and not review["coverage_gaps"] and all(v["decision"] == "ACCEPT" for v in verdicts)
        result["status"] = "complete"
    except (ValueError, RuntimeError, TimeoutError) as exc:
        result.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        await broker.aclose()
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        result["reported_tokens"] = sum(c.get("tokens_used") or 0 for c in broker.usage_calls)
        snapshot(planner.state)
        print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir")
    asyncio.run(probe(parser.parse_args().artifact_dir))
