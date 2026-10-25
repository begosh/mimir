"""Quarantine preserves originals and gaps without releasing stale assertions."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import SwarmResult, WorkerFailure
from publication_view import build_publication_view
from test_engine_policy import FixtureBackend
from test_material_finding_gate import BAD, GOOD, finding


def test_quarantine_does_not_change_original_or_drop_sources_and_gaps():
    result = {**finding(BAD), "gaps": ["Condition unresolved"]}
    context = {"findings": {"evidence": result}, "checks": {}}
    original = deepcopy(context)
    view = build_publication_view(context, [{"task_id": "evidence", "reason": "Reversed field association"}])
    assert context == original and "result" not in view["evidence"]
    assert view["evidence"]["sources"] == result["sources"]
    assert view["evidence"]["gaps"] == result["gaps"]
    for entries in ([{"task_id": "unknown", "reason": "bad"}],
                    [{"task_id": "evidence", "reason": " "}],
                    [{"task_id": "evidence", "reason": "a"}, {"task_id": "evidence", "reason": "b"}]):
        with pytest.raises(ValueError): build_publication_view(context, entries)


@pytest.mark.parametrize("approved", [False, True])
def test_publication_quarantine_requires_final_approval(tmp_path, approved):
    class Worker(FixtureBackend):
        def __init__(self): super().__init__(); self.checks = 0
        async def spawn(self, prompt, role="Worker", **options):
            if role == "Domain-Analyst":
                value = {**finding(BAD), "gaps": ["Condition unresolved"]}
            elif role == "Mimir-Synthesizer":
                value = {"answer": GOOD, "limitations": ["Condition unresolved"]}
            elif role == "Mimir-Assembly-Repairer":
                value = {"answer": GOOD, "limitations": ["Condition unresolved", "Evidence task's reversed association quarantined"],
                         "quarantined_tasks": [{"task_id": "evidence", "reason": "Reversed field association; the supplied code assigns critic 180 and specialists 250"}]}
            elif role == "Mimir-Final-Checker":
                self.checks += 1
                payload = json.loads(prompt.split("INPUTS:\n")[1])
                assert payload["task_context"]["findings"]["evidence"]["answer"] == BAD
                entry = payload["publication_view"]["evidence"]
                if self.checks == 1:
                    assert entry["status"] == "accepted"
                    value = {"verdict": "FAIL", "issues": ["Reversed assertion in evidence appendix"]}
                else:
                    assert entry["status"] == "quarantined" and "result" not in entry
                    assert entry["gaps"] == ["Condition unresolved"]
                    value = {"verdict": "PASS" if approved else "FAIL",
                             "issues": [] if approved else ["Quarantine hides a required conflict"]}
            else:
                return await super().spawn(prompt, role=role, **options)
            self.calls.append({"role": role, "prompt": prompt})
            return SwarmResult(role, "SUCCESS", value, json.dumps(value))
    async def run():
        path, report = tmp_path / "state.json", tmp_path / "report.md"
        worker = Worker()
        options = dict(goal="Review limits", mode="review", backend="codex", model="fixture", effort="low",
            worker_transport="native", worker_factory=lambda **kw: worker, state_file=str(path),
            output_path=str(report), skip_web=True, memory_mode="off", progress_format="events")
        with patch.object(engine.JarvisMemory, "record_learning") as learning:
            if approved: await engine.run_mimir(**options)
            else:
                with pytest.raises(WorkerFailure): await engine.run_mimir(**options)
            if not approved:
                learning.assert_not_called()
        state = json.loads(path.read_text(encoding="utf-8"))
        assert state["completed_data"]["evidence"]["result"]["answer"] == BAD
        assert worker.checks == 2
        if approved:
            text = report.read_text(encoding="utf-8")
            assert BAD not in text and GOOD in text and "**quarantined**" in text and "Condition unresolved" in text
            payload = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
            assert payload["task_results"]["evidence"]["result"]["answer"] == BAD
            assert not any(c["task_id"] == "evidence" for c in payload["research"]["claims"])
            assert payload["publication_view"]["evidence"]["status"] == "quarantined"
            assert "Condition unresolved" in [g["description"] for g in payload["research"]["gaps"]]
            before = report.read_bytes()
            calls = len(worker.calls)
            await engine.run_mimir(phase="synthesize", **{k: v for k, v in options.items() if k not in {"goal", "mode"}})
            assert len(worker.calls) == calls and report.read_bytes() == before
        else:
            assert not report.exists() and not report.with_suffix(".json").exists()
    asyncio.run(run())
