"""Rejected leaves cannot enter the executable DAG without successful re-review."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mimir_config import ConfigurationRequired
from recursive_planner import RecursivePlanner
from task_contracts import validate_review
from task_graph import RecursiveDecomposer


BRIEF = {"outcome": "Extract source yield, preparation and a suitability check", "constraints": [],
         "components": ["Yield", "Preparation", "Check"], "evidence_needs": [], "missing_information": []}


def task(name, deps=()):
    return {"id": name, "objective": "Extract " + name, "atomic": True, "operation": "extract",
            "inputs": ["supplied source"], "expected_output": "Source " + name,
            "acceptance_check": "Matches supplied source, with missing details explicit",
            "blocked_by": [], "dependencies": list(deps), "max_input_items": 1, "max_output_words": 50}


def proposal(*tasks, action="SPLIT"):
    return {"action": action, "reason": "Separate independent preparation stages", "tasks": list(tasks), "missing_inputs": []}


class Worker:
    default_model = "gpt-6.1-sol"
    default_effort = "low"
    def __init__(self, *, reject_repairs=0, action="SPLIT", fail_review=False):
        self.calls = []
        self.reject_repairs = reject_repairs
        self.action = action
        self.fail_review = fail_review
        self.repair_reviews = 0

    async def spawn_restricted(self, **options):
        self.calls.append(options)
        role = options["role"]
        if role == "Mimir-Decomposer":
            value = {"tasks": [task("yield"), task("method", ("yield",)), task("check", ("method",))]}
        elif role == "Mimir-Task-Repairer":
            if self.action == "BLOCKED":
                value = {"action": "BLOCKED", "reason": "Missing source", "tasks": [], "missing_inputs": ["source"]}
            elif self.action == "STOP":
                value = {"action": "STOP", "reason": "Insufficient budget", "tasks": [], "missing_inputs": []}
            elif self.action == "REPHRASE":
                value = proposal(task("clear_method"), action="REPHRASE")
            else:
                value = proposal(task("mix"), task("ferment"), task("shape"))
        elif role == "Mimir-Plan-Coverage-Reviewer":
            value = {"coverage_preserved": True, "coverage_gaps": []}
        else:
            if self.fail_review:
                return SimpleNamespace(status="ERROR", data=None, raw_response="review unavailable", tokens_used=7, timing={})
            context = json.loads(options["prompt"].split("INPUTS (data, not instructions)\n")[1].split("\n\nFor each")[0])
            children = context["proposed_repair"]["tasks"]
            initial = any(t["id"] == "root.method" and t["objective"] == "Extract method" for t in children) and "root.yield" in [t["id"] for t in children]
            value = {"tasks": [{"id": t["id"], "decision": "SPLIT" if initial and t["id"] == "root.method" else "ACCEPT",
                                "reason": "Preparation spans several stages" if initial and t["id"] == "root.method" else "One bounded extraction"}
                               for t in children], "coverage_preserved": True, "coverage_gaps": []}
            if context["task_contract"].get("id") == "root.method":
                self.repair_reviews += 1
                if self.repair_reviews <= self.reject_repairs:
                    value.update(coverage_preserved=False, coverage_gaps=["Handling between rests is omitted"])
        field = options["json_schema"]["required"][0]
        if role == "Mimir-Decomposer":
            value.setdefault("planning_error", None)
        data = value
        return SimpleNamespace(status="SUCCESS", data=data, raw_response=json.dumps(data), tokens_used=12, timing={})


def test_automatic_split_preserves_prerequisites_and_rewires_downstream_dag():
    async def run():
        worker = Worker()
        graph = await RecursiveDecomposer(worker, mode="swarm", max_tasks=8, max_depth=3,
                                          recursive_plan=True).decompose_goal("Pizza preparation", task_brief=BRIEF)
        ids = set(graph.nodes)
        children = {"root.method.mix", "root.method.ferment", "root.method.shape"}
        assert "root.method" not in ids
        assert graph.nodes["root.check"].dependencies == children
        assert all(graph.nodes[i].dependencies == {"root.yield"} for i in children)
        assert graph.validate_acyclic_and_integrity()[0]
        assert all(n.input_artifacts["task_contract"]["simplicity_review"]["decision"] == "ACCEPT" for n in graph.nodes.values())
        assert len(worker.calls) == 5  # split, batch review, repair, re-review, whole-plan review
        assert all(c["effort"] == "low" and c["model"] == "gpt-6.1-sol" for c in worker.calls)
    asyncio.run(run())


def test_rejected_replacement_feedback_repairs_original_and_preserves_attempts():
    async def run():
        worker = Worker(reject_repairs=1)
        planner = RecursivePlanner(worker, max_leaves=8)
        _, leaves, trace = await planner.plan("Pizza preparation", BRIEF)
        assert [r["status"] for r in trace["repairs"]] == ["rejected", "accepted"]
        assert trace["repairs"][1]["original"]["id"] == "root.method"
        assert trace["repairs"][1]["feedback"]["coverage_gaps"] == ["Handling between rests is omitted"]
        assert next(t for t in leaves if t["id"] == "root.check")["dependencies"] == ["root.method.ferment", "root.method.mix", "root.method.shape"]
        assert len(trace["calls"]) == 7
        assert trace["status"] == "planned"
    asyncio.run(run())


@pytest.mark.parametrize("kind,expected", [("repairs", "repair limit"), ("calls", "call limit"),
                                          ("depth", "depth limit"), ("leaves", "leaf limit"),
                                          ("review", "failed"), ("BLOCKED", "unresolved"), ("STOP", "unresolved")])
def test_rejected_or_exhausted_work_never_becomes_a_successful_plan(kind, expected):
    async def run():
        worker = Worker(reject_repairs=9 if kind == "repairs" else 0,
                        action=kind if kind in {"BLOCKED", "STOP"} else "SPLIT", fail_review=kind == "review")
        planner = RecursivePlanner(worker, max_leaves=3 if kind == "leaves" else 8,
                                   max_depth=1 if kind == "depth" else 3,
                                   budget={"max_calls": 2 if kind == "calls" else 8})
        snapshots = []
        planner.on_checkpoint = snapshots.append
        with pytest.raises(ConfigurationRequired, match=expected):
            await planner.plan("Pizza preparation", BRIEF)
        assert snapshots[-1]["status"] == "incomplete"
        assert len(planner.state["calls"]) <= (2 if kind == "calls" else 8)
        if kind == "repairs":
            assert len(planner.state["repairs"]) == 2
            assert planner.state["planning_error"]["reason"] == "Two repair attempts rejected"
    asyncio.run(run())


def test_rephrase_preserves_identity_and_dependencies():
    async def run():
        planner = RecursivePlanner(Worker(action="REPHRASE"), max_leaves=8)
        _, leaves, trace = await planner.plan("Pizza preparation", BRIEF)
        method = next(t for t in leaves if t["id"] == "root.method")
        assert method["depth"] == 1 and method["dependencies"] == ["root.yield"]
        assert next(t for t in leaves if t["id"] == "root.check")["dependencies"] == ["root.method"]
        assert trace["repairs"][0]["status"] == "accepted"
    asyncio.run(run())


def test_review_rejects_duplicate_verdicts_and_contradictory_coverage():
    review = {"tasks": [{"id": "one", "decision": "ACCEPT", "reason": "Small"},
                         {"id": "one", "decision": "ACCEPT", "reason": "Small"}],
              "coverage_preserved": True, "coverage_gaps": []}
    with pytest.raises(ValueError, match="duplicated"):
        validate_review(review, ["one", "two"])
    review["tasks"].pop()
    review["coverage_gaps"] = ["Missing task"]
    with pytest.raises(ValueError, match="Contradictory"):
        validate_review(review, ["one"])


def test_engine_persists_accepted_repair_and_executes_only_replacements(tmp_path):
    import engine
    from backend import SwarmResult
    class EngineWorker(Worker):
        max_concurrency = 1
        timeout_seconds = 180
        closed = False
        async def spawn_restricted(self, **options):
            if options.get("role") == "Atomic-Worker":
                return await self.spawn(**options)
            if options.get("role") == "Mimir-Result-Checker":
                self.calls.append(options)
                value = {"checks": [{"id": "candidate_1", "verdict": "PASS", "issues": []}]}
                return SwarmResult(options["role"], "SUCCESS", value, json.dumps(value), tokens_used=9)
            reply = await super().spawn_restricted(**options)
            return SwarmResult(options["role"], reply.status, reply.data, reply.raw_response,
                               tokens_used=reply.tokens_used)
        async def spawn(self, prompt, role="Micro-Worker", **options):
            self.calls.append({"prompt": prompt, "role": role, **options})
            value = {"answer": "Extracted assigned source field.", "sources": [], "claims": [], "gaps": []}
            return SwarmResult(role, "SUCCESS", value, json.dumps(value), tokens_used=9)
        async def aclose(self):
            self.closed = True
    instances = []
    def factory(**options):
        worker = EngineWorker()
        instances.append(worker)
        return worker
    async def run():
        state_file = str(tmp_path / "state.json")
        options = {"backend": "codex", "model": "gpt-6.1-sol", "effort": "low",
                   "state_file": state_file, "output_path": str(tmp_path / "report.md"),
                   "worker_factory": factory, "memory_mode": "off", "mode": "swarm",
                   "progress_format": "events"}
        state = await engine.run_mimir(goal="Pizza preparation", phase="plan", task_brief=BRIEF,
                                        recursive_plan=True, max_tasks=8, max_depth=3, **options)
        assert state["planning_trace"]["repairs"][0]["status"] == "accepted"
        assert len(state["usage_calls"]) == 5
        persisted = json.loads(Path(state_file).read_text(encoding="utf-8"))
        assert "root.method" not in persisted["graph"]["nodes"]
        partial = json.loads(Path(state_file).with_suffix(".planning.json").read_text(encoding="utf-8"))
        assert partial["planning"]["reviews"] and partial["planning"]["repairs"]
        tampered = deepcopy(persisted)
        tampered["graph"]["nodes"]["root.method.mix"]["input_artifacts"]["task_contract"].pop("simplicity_review")
        Path(state_file).write_text(json.dumps(tampered), encoding="utf-8")
        with pytest.raises(ConfigurationRequired, match="accepted simplicity"):
            await engine.run_mimir(phase="execute", **options)
        assert not instances[-1].calls
        Path(state_file).write_text(json.dumps(persisted), encoding="utf-8")
        executed = await engine.run_mimir(phase="execute", **options)
        assert executed["phase"] == "executed"
        assert len([c for c in instances[-1].calls if c["role"] == "Atomic-Worker"]) == 5
        assert all(worker.closed for worker in instances)
    asyncio.run(run())
