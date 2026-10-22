"""
scripts/jev_gate.py
System 1 Fast Decision Model and Joint Expected Value (JEV) Evaluator.
Inspired by TypeSafe AI's Jev and decision theory. Provides model-estimated
decision confidence, heuristic DAG pruning, and evidence screening.
"""

from __future__ import annotations

import math
import json
from dataclasses import dataclass
from typing import Any, List, Tuple


def _unit_number(value: Any, name: str) -> float:
    """Accept schema numbers only; NaN, infinity and coercions are invalid."""
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError(f"{name} must be a finite number within [0, 1]")
    return float(value)


def _successful_data(result: Any) -> dict:
    if result.status != "SUCCESS" or not isinstance(result.data, dict):
        raise ValueError("Decision worker failed or returned an invalid JSON object")
    return result.data


@dataclass
class JevDecision:
    decision: str
    calibrated_prob: float
    reasoning_hint: str = ""
    joint_expected_value: float = 0.0


class JevDecisionGate:
    """
    Implements System 1 decision gating and Joint Expected Value (JEV) computation.
    Evaluates state using worker calls. Confidence is model-estimated and has
    not been statistically calibrated; screening does not verify source facts.
    """

    def __init__(self, swarm: Any, confidence_threshold: float = 0.70):
        self.swarm = swarm
        self.confidence_threshold = _unit_number(confidence_threshold, "Confidence threshold")

    async def evaluate_choice(
        self,
        context: str,
        question: str,
        choices: List[str],
    ) -> JevDecision:
        if not isinstance(choices, list) or not choices or any(not isinstance(c, str) or not c.strip() for c in choices):
            raise ValueError("Choices must be a nonempty list of strings")
        schema = {
            "type": "object",
            "required": ["choice", "confidence"],
            "properties": {
                "choice": {"type": "string", "enum": choices},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        }

        prompt = f"""
        BESLUTSFATTANDE (SYSTEM 1):
        KONTEXT: {context[:1200]}
        FRÅGA: {question}
        VAL: {choices}

        Välj det optimala alternativet och ange en strikt kalibrerad sannolikhet (0.0 till 1.0).
        Svara enbart i JSON enligt schemat.
        """

        res = await self.swarm.spawn(
            prompt=prompt,
            role="Jev-System1-Gate",
            effort=None,
            json_schema=schema,
        )

        data = _successful_data(res)
        chosen = data.get("choice")
        if chosen not in choices:
            raise ValueError("Decision worker selected an unsupported choice")
        prob = _unit_number(data.get("confidence"), "Confidence")

        return JevDecision(
            decision=chosen,
            calibrated_prob=prob,
            reasoning_hint=f"System-1 gate ({res.duration_seconds:.2f}s)",
        )

    async def evaluate_task_jev(
        self,
        task_title: str,
        task_prompt: str,
        goal: str,
        parent_dependencies: List[str],
    ) -> float:
        """
        Computes a heuristic importance score for a prospective DAG node:
        criticality * (1 - 0.5 * redundancy_penalty).
        Inputs are worker estimates; this is not measured information gain.
        Returns a score in [0.0, 1.0].
        """
        schema = {
            "type": "object",
            "required": ["criticality", "redundancy_penalty"],
            "properties": {
                "criticality": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "redundancy_penalty": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        }

        prompt = f"""
        JEV EVALUATION:
        OVERALL OBJECTIVE: "{goal}"
        SUBTASK: "{task_title}"
        INSTRUCTION: "{task_prompt}"
        DEPENDENCIES: {parent_dependencies}

        TASK:
        Assess the task's Joint Expected Value (JEV):
        1. 'criticality': How critical is this task for the goal? (0.0 = trivial/redundant, 1.0 = indispensable).
        2. 'redundancy_penalty': Overlap with general knowledge or other tasks? (0.0 = unique, 1.0 = completely redundant).
        Respond strictly in valid JSON matching the schema.
        """

        res = await self.swarm.spawn(
            prompt=prompt,
            role="Jev-Optimizer",
            effort=None,
            json_schema=schema,
        )

        data = _successful_data(res)
        criticality = _unit_number(data.get("criticality"), "Criticality")
        redundancy = _unit_number(data.get("redundancy_penalty"), "Redundancy penalty")

        return criticality * (1.0 - 0.5 * redundancy)

    async def screen_evidence_contract(
        self,
        role: str,
        result_payload: Any,
        raw_evidence_hash: str,
    ) -> Tuple[bool, float, str]:
        # Review the complete payload. A prefix review cannot approve unseen claims.
        payload_str = json.dumps(result_payload, ensure_ascii=False) if isinstance(result_payload, (dict, list)) else str(result_payload)
        schema = {
            "type": "object",
            "required": ["decision", "confidence"],
            "properties": {
                "decision": {"type": "string", "enum": ["APPROVE", "AUDIT_REQUIRED", "REJECT"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        }

        prompt = f"""
        EVIDENCE CONTRACT SYSTEM 1 SCREENING:
        AGENT: {role}
        EVIDENCE HASH: sha256:{raw_evidence_hash[:12]}
        DELIVERED RESULT:
        {payload_str}

        QUESTION:
        Screen this result for logical coherence and obvious unsupported assertions.
        The hash establishes output identity only; it is not factual verification.
        Treat missing source evidence or retrieval gaps as uncertainty.
        Choose:
        - "APPROVE": Result is solid and can be committed directly to Blackboard.
        - "AUDIT_REQUIRED": Uncertain or borderline; requires mandatory Red-Team review.
        - "REJECT": Obviously flawed, empty, or failed.

        Respond strictly in valid JSON matching the schema.
        """

        res = await self.swarm.spawn(
            prompt=prompt,
            role="Jev-Evidence-Screen",
            effort=None,
            json_schema=schema,
        )

        try:
            data = _successful_data(res)
            decision = data.get("decision")
            if decision not in {"APPROVE", "AUDIT_REQUIRED", "REJECT"}:
                raise ValueError("Unsupported evidence screening decision")
            confidence = _unit_number(data.get("confidence"), "Confidence")
        except (ValueError, TypeError):
            return False, 0.0, "AUDIT_REQUIRED"

        is_approved = (decision == "APPROVE") and (confidence >= self.confidence_threshold)
        return is_approved, confidence, decision
