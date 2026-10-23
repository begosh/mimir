"""Direct structured outputs; semantic admission still runs locally."""
from task_brief import TASK_BRIEF_SCHEMA
from task_contracts import task_schema


def object_schema(properties):
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


def planning_schema(field):
    string = {"type": "string"}
    strings = {"type": "array", "items": string}
    tasks = {"type": "array", "items": task_schema()}
    coverage = {"coverage_preserved": {"type": "boolean"}, "coverage_gaps": strings}
    schemas = {
        "brief_json": TASK_BRIEF_SCHEMA,
        "tasks_json": object_schema({"tasks": tasks, "planning_error": {"type": ["string", "null"]}}),
        "coverage_json": object_schema(coverage),
        "review_json": object_schema({"tasks": {"type": "array", "items": object_schema({
            "id": string, "decision": {"type": "string", "enum": ["ACCEPT", "SPLIT", "BLOCKED"]}, "reason": string})}, **coverage}),
        "repair_json": object_schema({"action": {"type": "string", "enum": ["REPHRASE", "SPLIT", "BLOCKED", "STOP"]},
            "reason": string, "tasks": tasks, "missing_inputs": strings}),
    }
    if field == "checks_json":
        from post_worker import checker_schema
        return checker_schema()
    return schemas[field]
