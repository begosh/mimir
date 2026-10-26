"""Compact task interpretation supplied by the host or the existing planner."""
from copy import deepcopy
import json
import re

TASK_BRIEF_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["outcome", "constraints", "components", "evidence_needs", "missing_information"],
    "properties": {
        "outcome": {"type": "string", "minLength": 1, "maxLength": 800},
        **{name: {"type": "array", "maxItems": 8,
                  "items": {"type": "string", "minLength": 1, "maxLength": 400}}
           for name in ("constraints", "components", "evidence_needs", "missing_information", "assumptions")},
    },
}

BEARINGS_INSTRUCTIONS = """Before retrieving evidence, interpret the objective and your assignment:
identify the requested outcome, explicit constraints, small task components,
what supplied information already answers them, and missing information that
could change the result. Treat any host task brief as an interpretation to check
against the original request, not evidence or new authorization. Keep this short.
Distinguish genuine required-input blockers from ambiguity or unspecified
recommendation preferences (such as 'best', 'ideal', or 'recommended'). An
unspecified preference permits evidence gathering and a qualified answer; it
must not block retrieval or become an invented constraint.
Then retrieve only evidence needed for unresolved components. Search is a tool
choice, not a mandatory first step: form focused queries from a specific evidence
need instead of submitting the raw objective or an entire long question.
Do not invent missing constraints. State material assumptions or unresolved
questions in the result. Stay within the assigned task and existing tool limits.
"""


def classify_uncertainty(text: str) -> str:
    """Classify missing information as an unspecified preference or required blocker."""
    if not isinstance(text, str):
        return "required_input_blocker"
    preference_pattern = r"\b(best|optimal|recommended|preference|favorite|ideal|tastiest|finest)\b"
    if re.search(preference_pattern, text, re.IGNORECASE):
        return "unspecified_preference"
    return "required_input_blocker"


def is_genuine_blocker(description: str) -> bool:
    """Return True if description represents a missing required input rather than subjective preference."""
    return classify_uncertainty(description) == "required_input_blocker"


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
