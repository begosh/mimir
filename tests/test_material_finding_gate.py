"""Ordinary policies reject wrong associations before release or publication."""
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import SwarmResult, WorkerFailure
from post_worker import check_material_records
from test_engine_policy import FixtureBackend


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "task_graph.py"
TEXT = SOURCE.read_text(encoding="utf-8")
SPAN = next(line.strip() for line in TEXT.splitlines() if '(180 if t["id"] == "critique" else 250)' in line)
GOOD = "The review critic limit is 180 words; specialist limits are 250 words."
BAD = "The review critic limit is 250 words; specialist limits are 180 words."


def finding(answer):
    return {"answer": answer, "sources": [{"id": "limits", "locator": str(SOURCE),
        "retrieval_type": "local_file", "retrieved_at": "", "support_excerpt": SPAN}],
        "claims": [{"text": answer, "source_ids": ["limits"], "support_status": "supported",
                    "rationale": "Assigned limits in the supplied code span."}], "gaps": []}


@pytest.mark.parametrize("mode", ["single", "review"])
@pytest.mark.parametrize("repair", [False, True])
def test_wrong_association_is_blocked_or_checked_before_publication(tmp_path, mode, repair):
    class Worker(FixtureBackend):
        async def spawn(self, prompt, role="Worker", **options):
            self.calls.append({"role": role, "prompt": prompt, **options})
            if role == "Mimir-Result-Checker":
                context = json.loads(prompt.split("INPUTS:\n")[1])
                checks = []
                for candidate in context["candidates"]:
                    # Both numbers occur in the real source. Association is the defect.
                    bad = candidate["result"]["answer"] == BAD
                    if bad:
                        assert "180" in SPAN and "250" in SPAN
                    checks.append({"id": candidate["id"], "verdict": "FAIL" if bad else "PASS",
                                   "issues": ["Critic and specialist field association reversed"] if bad else []})
                value = {"checks": checks}
            elif role == "Mimir-Result-Repairer":
                value = {"action": "REPHRASE" if repair else "STOP",
                         "objective": "Preserve the critic 180 and specialist 250 association." if repair else "",
                         "reason": "Correct the reversed association"}
            elif role == "Mimir-Synthesizer":
                assert BAD not in prompt
                value = {"answer": GOOD, "limitations": []}
            elif role == "Mimir-Final-Checker":
                value = {"verdict": "PASS", "issues": []}
            else:
                value = finding(BAD if role == "Domain-Analyst" and "TARGETED REPAIR" not in prompt else GOOD)
            return SwarmResult(role, "SUCCESS", value, json.dumps(value), tokens_used=11)

    async def run():
        worker = Worker()
        state_path, report = tmp_path / "state.json", tmp_path / "report.md"
        original = engine.RecursiveDecomposer.decompose_goal
        async def plan(self, *args, **kwargs):
            graph = await original(self, *args, **kwargs)
            for node in graph.nodes.values():
                node.input_artifacts["supplied_sources"] = [{"id": "limits", "text": SPAN,
                    "locator": str(SOURCE), "retrieval_type": "local_file", "retrieved_at": "",
                    "status": "user_supplied"}]
            return graph
        options = dict(goal="State the review critic and specialist word limits from the supplied code.",
            mode=mode, backend="codex", model="fixture", effort="low", worker_transport="native",
            worker_factory=lambda **kw: worker, state_file=str(state_path), output_path=str(report),
            skip_web=True, memory_mode="off", progress_format="events")
        with patch.object(engine.RecursiveDecomposer, "decompose_goal", plan):
            if repair:
                await engine.run_mimir(**options)
            else:
                with pytest.raises(WorkerFailure):
                    await engine.run_mimir(**options)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        nid = "research" if mode == "single" else "evidence"
        attempts = state["graph"]["nodes"][nid]["result_attempts"]
        assert attempts[0]["result"]["answer"] == BAD
        assert attempts[0]["status"] == "FAIL"
        if not repair:
            assert nid not in state["completed_data"]
            assert not any(c["role"] == "Red-Team-Critic" for c in worker.calls)
            assert not report.exists() and not report.with_suffix(".json").exists()
        else:
            assert state["completed_data"][nid]["result"]["answer"] == GOOD
            assert attempts[-1]["status"] == "PASS"
            text = report.read_text(encoding="utf-8")
            assert BAD not in text and "Rejected attempts quarantined in the checkpoint: 1" in text
            assert state["final_answer_check"]["verdict"] == "PASS"
            if mode == "single":
                assert not any(c["role"] == "Mimir-Synthesizer" for c in worker.calls)
            else:
                critic = next(c for c in worker.calls if c["role"] == "Red-Team-Critic")
                assert BAD not in critic["prompt"]
    asyncio.run(run())


def test_unknown_source_links_fail_structural_gate_without_semantic_verdict():
    result = finding(GOOD)
    result["claims"][0]["source_ids"] = ["unknown"]
    assert check_material_records(result)["verdict"] == "FAIL"
    assert check_material_records(finding(GOOD))["verdict"] == "REVIEW"


def test_qualified_inference_is_not_structurally_rejected():
    result = finding(GOOD)
    result["claims"][0]["support_status"] = "inference"
    assert check_material_records(result)["verdict"] == "REVIEW"


def test_corrected_summary_cannot_publish_a_stale_appendix_assertion(tmp_path):
    class Worker(FixtureBackend):
        async def spawn(self, prompt, role="Worker", **options):
            if role == "Domain-Analyst":
                value = finding(BAD)  # Admission checker misses the semantic defect.
            elif role == "Mimir-Synthesizer":
                value = {"answer": GOOD, "limitations": []}
            elif role == "Mimir-Final-Checker":
                assert "task-result appendix" in prompt
                context = json.loads(prompt.split("INPUTS:\n")[1])
                assert context["task_context"]["findings"]["evidence"]["answer"] == BAD
                assert context["assembled"]["answer"] == GOOD
                value = {"verdict": "FAIL", "issues": ["Corrected summary leaves the reversed appendix assertion"]}
            elif role == "Mimir-Assembly-Repairer":
                value = {"answer": GOOD, "limitations": [], "quarantined_tasks": []}
            else:
                return await super().spawn(prompt, role=role, **options)
            return SwarmResult(role, "SUCCESS", value, json.dumps(value))
    async def run():
        path, report = tmp_path / "state.json", tmp_path / "report.md"
        with patch.object(engine.JarvisMemory, "record_learning") as learning:
            with pytest.raises(WorkerFailure):
                await engine.run_mimir(goal="State the review word limits", mode="review", backend="codex",
                    model="fixture", effort="low", worker_transport="native", worker_factory=lambda **kw: Worker(),
                    state_file=str(path), output_path=str(report), skip_web=True, memory_mode="off", progress_format="events")
            learning.assert_not_called()
        state = json.loads(path.read_text(encoding="utf-8"))
        assert state["rejected_synthesis"]["result"]["answer"] == GOOD
        assert state["final_answer_check"]["verdict"] == "FAIL"
        assert not report.exists() and not report.with_suffix(".json").exists()
    asyncio.run(run())
