"""One assembly correction, unchanged evidence/policy, durable exhaustion."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from assembly_gate import assemble_checked
from backend import SwarmResult, WorkerFailure
from invocation_broker import InvocationBroker, BudgetExhausted
from mimir_config import ConfigurationRequired
from test_engine_policy import FixtureBackend


CONTEXT = {"request": "Report the source value and its uncertainty", "scope": [], "coverage": {},
           "sources": [{"id": "s", "status": "user_supplied", "support_excerpts": ["Value: 2; condition unknown."]}],
           "findings": {"t": {"answer": "Value: 2", "gaps": ["Condition unknown"]}}, "checks": {}}


class Worker(FixtureBackend):
    def __init__(self, *, correction="valid", second="PASS", initial="FAIL"):
        super().__init__()
        self.correction, self.second, self.initial = correction, second, initial
        self.checks = 0
        self.contexts = []
    async def spawn(self, prompt, role="Worker", **options):
        self.calls.append({"role": role, "prompt": prompt, **options})
        if role == "Mimir-Synthesizer":
            value = {"answer": "Value: 9", "limitations": []}
        elif role == "Mimir-Final-Checker":
            self.contexts.append(json.loads(prompt.split("INPUTS:\n")[1])["task_context"])
            self.checks += 1
            verdict = self.initial if self.checks == 1 else self.second
            value = {} if verdict == "invalid" else {"verdict": verdict,
                "issues": [] if verdict == "PASS" else ["Wrong value and missing condition gap"]}
        elif role == "Mimir-Assembly-Repairer":
            payload = json.loads(prompt.split("INPUTS:\n")[1])
            assert payload["task_context"] == CONTEXT
            assert payload["rejected_answer"]["answer"] == "Value: 9"
            if self.correction == "cancel": raise asyncio.CancelledError()
            if self.correction == "invalid": value = {"answer": "bad"}
            else: value = {"answer": "word " * 301 if self.correction == "oversized" else "Value: 2",
                           "limitations": ["Condition unknown"], "quarantined_tasks": []}
        else:
            raise AssertionError(role)
        return SwarmResult(role, "SUCCESS", value, json.dumps(value), tokens_used=11)


def execute(worker, state, snapshots):
    def persist(): snapshots.append(deepcopy(state))
    return assemble_checked(worker, CONTEXT, state, persist, lambda *args, **kw: None,
                            model=worker.default_model, max_answer_words=300)


def test_one_correction_rechecks_same_context_and_persists_reservation():
    async def run():
        worker, state, snapshots = Worker(), {}, []
        original = deepcopy(CONTEXT)
        answer, check = await execute(worker, state, snapshots)
        assert answer == {"answer": "Value: 2", "limitations": ["Condition unknown"]}
        assert check["verdict"] == "PASS" and CONTEXT == original
        assert worker.contexts == [CONTEXT, CONTEXT]
        assert [c["role"] for c in worker.calls] == ["Mimir-Synthesizer", "Mimir-Final-Checker",
                                                    "Mimir-Assembly-Repairer", "Mimir-Final-Checker"]
        reserved = next(s["assembly_history"] for s in snapshots if s["assembly_history"]["stage"] == "repairing")
        assert reserved["corrections_reserved"] == 1 and len(reserved["versions"]) == 1
        assert state["assembly_history"]["versions"][0]["check"]["verdict"] == "FAIL"
        assert state["assembly_history"]["versions"][1]["check"]["verdict"] == "PASS"
        before = len(worker.calls)
        assert await execute(worker, state, snapshots) == (answer, check)
        assert len(worker.calls) == before
    asyncio.run(run())


@pytest.mark.parametrize("correction,second,initial", [
    ("valid", "FAIL", "FAIL"), ("invalid", "PASS", "FAIL"),
    ("oversized", "PASS", "FAIL"), ("cancel", "PASS", "FAIL"), ("valid", "PASS", "invalid")])
def test_failure_and_interruption_never_reset_correction_allowance(correction, second, initial):
    async def run():
        worker, state, snapshots = Worker(correction=correction, second=second, initial=initial), {}, []
        with pytest.raises(BaseException):
            await execute(worker, state, snapshots)
        before = len(worker.calls)
        with pytest.raises(WorkerFailure):
            await execute(worker, state, snapshots)
        assert len(worker.calls) == before
        assert sum(c["role"] == "Mimir-Assembly-Repairer" for c in worker.calls) == (0 if initial == "invalid" else 1)
        assert state["assembly_history"]["corrections_reserved"] == (0 if initial == "invalid" else 1)
        if correction in {"invalid", "oversized"}:
            assert state["assembly_history"]["rejected_correction"]["result"]["answer"]
    asyncio.run(run())


def test_budget_exhaustion_blocks_correction_without_widening_limits():
    async def run():
        native = Worker()
        broker = InvocationBroker(native, budget={"max_attempts": 2, "max_seconds": 60})
        state, snapshots = {}, []
        with pytest.raises(BudgetExhausted):
            await execute(broker, state, snapshots)
        assert len(native.calls) == 2 and broker.budget["max_attempts"] == 2
        assert state["assembly_history"]["corrections_reserved"] == 1
        with pytest.raises(WorkerFailure): await execute(broker, state, snapshots)
        assert len(native.calls) == 2
    asyncio.run(run())


def test_tampered_saved_history_rejected_before_calls():
    async def run():
        worker, state, snapshots = Worker(initial="PASS"), {}, []
        await execute(worker, state, snapshots)
        state["assembly_history"]["versions"][0]["result"]["answer"] = "tampered"
        before = len(worker.calls)
        with pytest.raises(ConfigurationRequired, match="identity"):
            await execute(worker, state, snapshots)
        assert len(worker.calls) == before
    asyncio.run(run())


def test_resume_completed_rejection_does_not_repeat_synthesis_or_first_check():
    async def run():
        state, snapshots = {}, []
        await execute(Worker(), state, snapshots)
        checkpoint = next(s for s in snapshots if s["assembly_history"]["stage"] == "rejected")
        worker = Worker()
        worker.checks = 1
        answer, check = await execute(worker, checkpoint, [])
        assert answer["answer"] == "Value: 2" and check["verdict"] == "PASS"
        assert [c["role"] for c in worker.calls] == ["Mimir-Assembly-Repairer", "Mimir-Final-Checker"]
    asyncio.run(run())


def test_changed_checker_policy_blocks_saved_assembly_before_calls():
    from unittest.mock import patch
    async def run():
        worker, state = Worker(initial="PASS"), {}
        await execute(worker, state, [])
        before = len(worker.calls)
        with patch("assembly_gate.assembly_repair_policy", return_value={"version": "changed"}):
            with pytest.raises(ConfigurationRequired, match="policy changed"):
                await execute(worker, state, [])
        assert len(worker.calls) == before
    asyncio.run(run())


def test_engine_publishes_corrected_version_and_recovers_without_calls(tmp_path):
    import engine
    from unittest.mock import patch
    from test_engine_policy import SOURCE
    class PublishingWorker(FixtureBackend):
        def __init__(self):
            super().__init__()
            self.final_calls = 0
        async def spawn(self, prompt, role="Worker", **options):
            if role == "Mimir-Synthesizer":
                value = {"answer": "Invented outcome", "limitations": []}
            elif role == "Mimir-Final-Checker":
                self.final_calls += 1
                value = {"verdict": "FAIL" if self.final_calls == 1 else "PASS",
                         "issues": ["Invented outcome"] if self.final_calls == 1 else []}
            else:
                return await super().spawn(prompt, role=role, **options)
            self.calls.append({"role": role, "prompt": prompt})
            return SwarmResult(role, "SUCCESS", value, json.dumps(value))
    async def run():
        worker = PublishingWorker()
        path, report = tmp_path / "state.json", tmp_path / "report.md"
        options = dict(backend="codex", model="fixture", effort="low", worker_transport="native",
            state_file=str(path), output_path=str(report), worker_factory=lambda **kw: worker,
            skip_web=True, memory_mode="off", progress_format="events")
        await engine.run_mimir(goal="Review evidence", mode="review", **options)
        payload = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
        assert payload["hardened_solution"] == f"Review supported by {SOURCE}."
        assert payload["assembly_history"]["versions"][0]["result"]["answer"] == "Invented outcome"
        assert payload["assembly_history"]["versions"][1]["check"]["verdict"] == "PASS"
        assert "Invented outcome" not in report.read_text(encoding="utf-8")
        before = len(worker.calls)
        await engine.run_mimir(phase="synthesize", **options)
        assert len(worker.calls) == before
    asyncio.run(run())
