"""Direct behavioral tests at the AdmissionAndAssemblyGate interface seam."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from admission_and_assembly_gate import AdmissionAndAssemblyGate
from backend import SwarmResult
from evidence_provenance import EvidenceProvenance
from task_graph import TaskGraph, TaskNode


class FakeGateBackend:
    default_model = "fixture"
    default_effort = "low"
    max_concurrency = 2
    batch_result_checks = False

    def __init__(self, *, check_verdicts=("FAIL", "PASS"), repair_action="REPHRASE"):
        self.check_verdicts = list(check_verdicts)
        self.repair_action = repair_action
        self.calls: list[dict] = []

    async def spawn_restricted(self, prompt: str, role: str = "Worker", **options):
        self.calls.append({"role": role, "prompt": prompt})
        if role == "Mimir-Result-Checker":
            verdict = self.check_verdicts.pop(0) if self.check_verdicts else "PASS"
            payload = {
                "checks": [
                    {
                        "id": "candidate_1",
                        "verdict": verdict,
                        "issues": [] if verdict == "PASS" else ["Missing qualification from source"],
                    }
                ]
            }
            return SwarmResult(role, "SUCCESS", payload, json.dumps(payload), tokens_used=5)
        if role == "Mimir-Result-Repairer":
            payload = {
                "action": self.repair_action,
                "objective": "Include source qualification" if self.repair_action == "REPHRASE" else "",
                "reason": "Qualification omitted",
            }
            return SwarmResult(role, "SUCCESS", payload, json.dumps(payload), tokens_used=5)
        if role == "Mimir-Synthesizer":
            payload = {"answer": "Initial synthesis with bad task", "limitations": ["Minor gap"]}
            return SwarmResult(role, "SUCCESS", payload, json.dumps(payload), tokens_used=8)
        if role == "Mimir-Final-Checker":
            verdict = self.check_verdicts.pop(0) if self.check_verdicts else "PASS"
            payload = {
                "verdict": verdict,
                "issues": [] if verdict == "PASS" else ["Task t_bad contradicts bound source"],
            }
            return SwarmResult(role, "SUCCESS", payload, json.dumps(payload), tokens_used=6)
        if role == "Mimir-Assembly-Repairer":
            payload = {
                "answer": "Corrected synthesis relying only on t_good.",
                "limitations": ["t_bad quarantined"],
                "quarantined_tasks": [{"task_id": "t_bad", "reason": "Contradicts bound source"}],
            }
            return SwarmResult(role, "SUCCESS", payload, json.dumps(payload), tokens_used=7)
        raise AssertionError(f"Unexpected role: {role}")

    spawn = spawn_restricted


def test_admit_or_repair_task_reserves_retry_and_constructs_rephrased_prompt():
    """admit_or_repair_task gates a worker response, reserves retry_count before repair, and returns next_prompt."""
    backend = FakeGateBackend(check_verdicts=("FAIL", "PASS"), repair_action="REPHRASE")
    graph = TaskGraph("Investigate timeout policy")
    node = TaskNode("t1", "Domain-Analyst", "Check timeout", "Investigate timeout")
    graph.add_node(node)

    AdmissionAndAssemblyGate.bind_graph_policies(graph, mode="review")
    assert "result_gate" in node.input_artifacts
    assert "result_repair" in node.input_artifacts

    valid_finding = {
        "answer": "Timeout is 15s.",
        "sources": [
            {
                "id": "s1",
                "locator": "config.py:L10",
                "retrieval_type": "local_file",
                "retrieved_at": "2026-10-26T12:00:00+00:00",
                "support_excerpt": "timeout = 15",
            }
        ],
        "claims": [
            {
                "text": "Timeout is 15s.",
                "source_ids": ["s1"],
                "support_status": "supported",
                "rationale": "Explicit constant",
            }
        ],
        "gaps": [],
    }

    async def run():
        async with AdmissionAndAssemblyGate(backend) as gate:
            # First attempt fails model check -> triggers repair and returns next_prompt
            resp1 = SwarmResult("Domain-Analyst", "SUCCESS", deepcopy(valid_finding), json.dumps(valid_finding))
            review1, next_prompt = await gate.admit_or_repair_task(
                node,
                resp1,
                {},
                fingerprint="fp1",
                prompt=node.prompt,
                goal=graph.goal,
            )
            assert review1["verdict"] == "FAIL"
            assert node.retry_count == 1
            assert next_prompt is not None
            assert "Include source qualification" in next_prompt

            # Second attempt passes model check -> returns (review, None)
            resp2 = SwarmResult("Domain-Analyst", "SUCCESS", deepcopy(valid_finding), json.dumps(valid_finding))
            review2, next_prompt2 = await gate.admit_or_repair_task(
                node,
                resp2,
                {},
                fingerprint="fp2",
                prompt=next_prompt,
                goal=graph.goal,
            )
            assert review2["verdict"] == "PASS"
            assert next_prompt2 is None
            assert resp2.status == "SUCCESS"
            assert len(node.result_attempts) == 2

    asyncio.run(run())


def test_assemble_publication_quarantines_faulty_task_and_projects_published_data():
    """assemble_publication runs synthesis, 1-shot assembly repair with QuarantinedFinding overlay, and projects published_data."""
    backend = FakeGateBackend(check_verdicts=("FAIL", "PASS"))
    state = {
        "goal": "Summarize service configuration",
        "mode": "review",
        "graph": {
            "nodes": {
                "t_good": {"id": "t_good", "input_artifacts": {}},
                "t_bad": {"id": "t_bad", "input_artifacts": {}},
            }
        },
        "completed_data": {
            "t_good": {
                "role": "Domain-Analyst",
                "result": {
                    "answer": "Port is 8080.",
                    "sources": [{"id": "s1", "locator": "cfg.py", "retrieval_type": "local_file", "retrieved_at": "2026-10-26T12:00:00+00:00", "support_excerpt": "PORT=8080"}],
                    "claims": [{"text": "Port is 8080", "source_ids": ["s1"], "support_status": "supported", "rationale": "Line 1"}],
                    "gaps": [],
                },
            },
            "t_bad": {
                "role": "Domain-Analyst",
                "result": {
                    "answer": "Hallucinated port 9999.",
                    "sources": [{"id": "s2", "locator": "cfg.py", "retrieval_type": "local_file", "retrieved_at": "2026-10-26T12:00:00+00:00", "support_excerpt": "PORT=8080"}],
                    "claims": [{"text": "Port is 9999", "source_ids": ["s2"], "support_status": "supported", "rationale": "Wrong"}],
                    "gaps": ["Unverified"],
                },
            },
        },
    }

    snapshots: list[dict] = []

    async def run():
        gate = AdmissionAndAssemblyGate(backend)
        hardened, reflection, published_data = await gate.assemble_publication(
            state,
            persist=lambda: snapshots.append(deepcopy(state)),
            emit=lambda *a, **kw: None,
            model="fixture",
        )
        assert hardened == "Corrected synthesis relying only on t_good."
        assert "One targeted assembly correction passed rechecking" in reflection
        assert state["publication_view"]["t_good"]["status"] == "accepted"
        assert state["publication_view"]["t_bad"]["status"] == "quarantined"
        assert published_data["t_bad"]["result"]["claims"] == []
        assert "Contradicts bound source" in published_data["t_bad"]["result"]["gaps"]
        # Original completed_data remains immutable in state
        assert len(state["completed_data"]["t_bad"]["result"]["claims"]) == 1

    asyncio.run(run())
