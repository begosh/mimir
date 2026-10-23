"""Admission checks shared by recursive planning and task repair."""
from graphlib import TopologicalSorter

OPERATIONS = ("clarify", "retrieve", "extract", "calculate", "compare", "check")


def task_schema():
    properties = {
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,19}$"},
        "objective": {"type": "string", "minLength": 1, "maxLength": 500},
        "atomic": {"type": "boolean"}, "operation": {"enum": [*OPERATIONS, "split"]},
        **{key: {"type": "array", "maxItems": 4, "items": {"type": "string", "minLength": 1, "maxLength": 300}}
           for key in ("inputs", "blocked_by", "dependencies")},
        **{key: {"type": "string", "maxLength": 400} for key in ("expected_output", "acceptance_check")},
        "max_input_items": {"type": "integer", "minimum": 0, "maximum": 2},
        "max_output_words": {"type": "integer", "minimum": 0, "maximum": 150}}
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


def validate_tasks(tasks):
    from jsonschema import validate, ValidationError
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 4:
        raise ValueError("A recursive split must contain 1-4 children")
    schema = task_schema()
    ids = set()
    for task in tasks:
        try:
            validate(task, schema)
        except ValidationError:
            raise ValueError("Invalid recursive task contract; no worker admitted") from None
        if task["id"] in ids:
            raise ValueError("Duplicate recursive sibling task id")
        ids.add(task["id"])
        if task["atomic"]:
            if task["operation"] == "split" or not task["inputs"] or not task["max_input_items"] or not task["max_output_words"] or not task["acceptance_check"].strip() or not task["expected_output"].strip():
                raise ValueError("Atomic tasks require one operation, bounded inputs, output and acceptance check")
            if len(task["inputs"]) > task["max_input_items"]:
                raise ValueError("Atomic task inputs exceed the declared item bound")
        elif task["operation"] != "split" or task["max_input_items"] != 0:
            raise ValueError("Non-atomic groupings require operation split and max_input_items=0")
    if any(not set(task["dependencies"]).issubset(ids) for task in tasks):
        raise ValueError("Unknown or cyclic recursive sibling dependencies")
    try:
        tuple(TopologicalSorter({task["id"]: task["dependencies"] for task in tasks}).static_order())
    except ValueError:
        raise ValueError("Unknown or cyclic recursive sibling dependencies") from None


def validate_review(review, task_ids):
    if not isinstance(review, dict) or set(review) != {"tasks", "coverage_preserved", "coverage_gaps"}:
        raise ValueError("Invalid simplicity review fields")
    verdicts = review["tasks"]
    if not isinstance(verdicts, list) or len(verdicts) != len(task_ids):
        raise ValueError("Reviewer omitted or duplicated tasks")
    seen = set()
    for verdict in verdicts:
        if not isinstance(verdict, dict) or set(verdict) != {"id", "decision", "reason"}:
            raise ValueError("Invalid simplicity verdict")
        if verdict["id"] in seen or verdict["decision"] not in {"ACCEPT", "SPLIT", "BLOCKED"}:
            raise ValueError("Invalid or duplicated simplicity verdict")
        if not isinstance(verdict["reason"], str) or not verdict["reason"].strip() or len(verdict["reason"]) > 500:
            raise ValueError("Simplicity verdict requires a bounded reason")
        seen.add(verdict["id"])
    if seen != set(task_ids):
        raise ValueError("Review ids differ from proposed tasks")
    if type(review["coverage_preserved"]) is not bool or not isinstance(review["coverage_gaps"], list):
        raise ValueError("Invalid coverage verdict")
    if any(not isinstance(gap, str) or not gap.strip() or len(gap) > 500 for gap in review["coverage_gaps"]) or len(review["coverage_gaps"]) > 8:
        raise ValueError("Invalid coverage gaps")
    if review["coverage_preserved"] == bool(review["coverage_gaps"]):
        raise ValueError("Contradictory coverage verdict")


def validate_repair(result):
    if not isinstance(result, dict) or set(result) != {"action", "reason", "tasks", "missing_inputs"}:
        raise ValueError("Invalid repair response fields")
    action = result["action"]
    if action not in {"REPHRASE", "SPLIT", "BLOCKED", "STOP"}:
        raise ValueError("Unknown repair action")
    if not isinstance(result["reason"], str) or not result["reason"].strip() or len(result["reason"]) > 500:
        raise ValueError("Repair requires a bounded reason")
    missing = result["missing_inputs"]
    if not isinstance(missing, list) or len(missing) > 4 or any(not isinstance(i, str) or not i.strip() or len(i) > 300 for i in missing):
        raise ValueError("Invalid repair missing inputs")
    tasks = result["tasks"]
    if action in {"BLOCKED", "STOP"}:
        if tasks != [] or (action == "BLOCKED" and not missing):
            raise ValueError("Blocked/stopped repairs require no tasks and explicit missing inputs when blocked")
        return
    validate_tasks(tasks)
    if (action == "REPHRASE" and (len(tasks) != 1 or not tasks[0]["atomic"])) or (action == "SPLIT" and len(tasks) < 2):
        raise ValueError("Invalid repair child count or rephrasing contract")
    if missing:
        raise ValueError("Executable repair cannot hide missing inputs")
