"""
scripts/jev_gate.py
System 1 Fast Decision Model and Joint Expected Value (JEV) Evaluator.
Inspired by TypeSafe AI's Jev and decision theory. Provides sub-second typed
calibrated decisions, DAG pruning via JEV, and anti-hallucination gating.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend import BaseSwarmBackend, SwarmResult


@dataclass
class JevDecision:
    decision: str
    calibrated_prob: float
    reasoning_hint: str = ""
    joint_expected_value: float = 0.0


class JevDecisionGate:
    """
    Implements System 1 decision gating and Joint Expected Value (JEV) computation.
    Evaluates application state to make typed, bounded decisions without the latency
    and token overhead of generative text models.
    """

    def __init__(self, swarm: Any, confidence_threshold: float = 0.70):
        self.swarm = swarm
        self.confidence_threshold = confidence_threshold

    async def evaluate_choice(
        self,
        context: str,
        question: str,
        choices: List[str],
    ) -> JevDecision:
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
            effort="low",
            json_schema=schema,
        )

        chosen = choices[0]
        prob = 0.75

        if isinstance(res.data, dict):
            candidate = res.data.get("choice")
            if candidate in choices:
                chosen = candidate
            prob = float(res.data.get("confidence", 0.75))
            prob = max(0.0, min(1.0, prob))

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
        Computes the Joint Expected Value (JEV) for a prospective DAG node:
        JEV = P(Critical Impact) * Estimated Information Gain - Computational Overhead Penalty
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
        ÖVERGRIPANDE MÅL: "{goal}"
        DELUPPGIFT: "{task_title}"
        INSTRUKTION: "{task_prompt[:500]}"
        BEROR PÅ: {parent_dependencies}

        UPPGIFT:
        Bedöm uppgiftens Joint Expected Value (JEV):
        1. 'criticality': Hur avgörande är denna uppgift för målet? (0.0 = onödig/trivial, 1.0 = oumbärlig).
        2. 'redundancy_penalty': Hur mycket överlappar den med standardkunskap eller andra noder? (0.0 = unik, 1.0 = helt redundant).
        Svara i ren JSON enligt schemat.
        """

        res = await self.swarm.spawn(
            prompt=prompt,
            role="Jev-Optimizer",
            effort="low",
            json_schema=schema,
        )

        criticality = 0.8
        redundancy = 0.2

        if isinstance(res.data, dict):
            criticality = float(res.data.get("criticality", 0.8))
            redundancy = float(res.data.get("redundancy_penalty", 0.2))

        net_jev = round(criticality * (1.0 - 0.5 * redundancy), 2)
        return max(0.05, min(1.0, net_jev))

    async def screen_evidence_contract(
        self,
        role: str,
        result_payload: Any,
        raw_evidence_hash: str,
    ) -> Tuple[bool, float, str]:
        payload_str = str(result_payload)[:800]
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
        BEVIS-HASH: sha256:{raw_evidence_hash[:12]}
        LEVERERAT RESULTAT:
        {payload_str}

        FRÅGA:
        Är detta resultat sakligt, logiskt sammanhängande och fritt från uppenbara hallucinationer?
        Välj:
        - "APPROVE": Resultatet är solitt och kan committas direkt till Blackboard.
        - "AUDIT_REQUIRED": Osäkert eller gränsfall; kräver obligatorisk Red-Team-granskning.
        - "REJECT": Uppenbart felaktigt, tomt eller havererat.

        Svara i ren JSON enligt schemat.
        """

        res = await self.swarm.spawn(
            prompt=prompt,
            role="Jev-Evidence-Screen",
            effort="low",
            json_schema=schema,
        )

        decision = "APPROVE"
        confidence = 0.85

        if isinstance(res.data, dict):
            decision = res.data.get("decision", "APPROVE")
            confidence = float(res.data.get("confidence", 0.85))

        is_approved = (decision == "APPROVE") and (confidence >= self.confidence_threshold)
        return is_approved, confidence, decision
