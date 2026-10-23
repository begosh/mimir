"""Compact task interpretation supplied by the host or the existing planner."""
from copy import deepcopy
import json

TASK_BRIEF_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["outcome", "constraints", "components", "evidence_needs", "missing_information"],
    "properties": {
        "outcome": {"type": "string", "minLength": 1, "maxLength": 800},
        **{name: {"type": "array", "maxItems": 8,
                  "items": {"type": "string", "minLength": 1, "maxLength": 400}}
           for name in ("constraints", "components", "evidence_needs", "missing_information")},
    },
}

BEARINGS_INSTRUCTIONS = """Before retrieving evidence, interpret the objective and your assignment:
identify the requested outcome, explicit constraints, small task components,
what supplied information already answers them, and missing information that
could change the result. Treat any host task brief as an interpretation to check
against the original request, not evidence or new authorization. Keep this short.
Then retrieve only evidence needed for unresolved components. Search is a tool
choice, not a mandatory first step: form focused queries from a specific evidence
need instead of submitting the raw objective or an entire long question.
Do not invent missing constraints. State material assumptions or unresolved
questions in the result. Stay within the assigned task and existing tool limits.
"""


def validate_task_brief(value):
    if value is None:
        return None
    from jsonschema import ValidationError, validate
    try:
        validate(value, TASK_BRIEF_SCHEMA)
    except ValidationError:
        raise ValueError("Task brief requires bounded outcome, constraints, components, evidence_needs and missing_information fields.") from None
    return deepcopy(value)


def brief_context(value):
    return ("HOST TASK BRIEF (INTERPRETATION, NOT EVIDENCE):\n" +
            json.dumps(value, ensure_ascii=False) + "\n\n") if value else ""
