"""Recursive plan contracts, dependency rewiring and bounded failures."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from recursive_planner import RecursivePlanner
from task_graph import RecursiveDecomposer, TaskGraph
from mimir_config import ConfigurationRequired

BRIEF = {"outcome": "Neapolitan dough recipe", "constraints": [],
         "components": ["Formula", "Fermentation"], "evidence_needs": ["Coherent recipe source"],
         "missing_information": ["Oven temperature"]}


def task(name, *, atomic=True, deps=(), operation="extract", blocked=()):
    return {"id": name, "objective": f"Extract only {name} from the supplied recipe",
            "atomic": atomic, "operation": operation if atomic else "split",
            "inputs": ["one selected recipe page"] if atomic else [],
            "expected_output": "one named quantity" if atomic else "",
            "acceptance_check": "quantity and unit match the cited excerpt" if atomic else "",
            "blocked_by": list(blocked), "dependencies": list(deps),
            "max_input_items": 1 if atomic else 0, "max_output_words": 80}


class Fake:
    default_model = "agreed"
    default_effort = "low"
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
    async def spawn_restricted(self, **options):
        self.calls.append(options)
        field = options["json_schema"]["required"][0]
        if options["role"] == "Mimir-Plan-Coverage-Reviewer":
            reply = {"coverage_preserved": True, "coverage_gaps": []}
        elif options["role"] == "Mimir-Simplicity-Reviewer":
            # Existing contract tests accept semantic review; repair tests below
            # explicitly inject rejection/coverage decisions.
            context = json.loads(options["prompt"].split("INPUTS (data, not instructions)\n")[1].split("\n\nFor each")[0])
            reply = {"tasks": [{"id": t["id"], "decision": "ACCEPT", "reason": "One bounded extraction"}
                                for t in context["proposed_repair"]["tasks"]],
                     "coverage_preserved": True, "coverage_gaps": []}
        else:
            reply = self.replies.pop(0)
        if options["role"] == "Mimir-Decomposer":
            reply.setdefault("planning_error", None)
        data = reply
        return SimpleNamespace(status="SUCCESS", data=data, raw_response=json.dumps(data), tokens_used=12, timing={})


def test_interpretation_is_consumed_then_recursive_dependencies_are_rewired():
    async def run():
        worker = Fake([BRIEF, {"tasks": [task("formula", atomic=False), task("schedule", deps=("formula",))]},
                       {"tasks": [task("water"), task("hydration", deps=("water",), operation="calculate")]}])
        snapshots = []
        planner = RecursivePlanner(worker, max_leaves=4, max_depth=2, on_checkpoint=snapshots.append)
        brief, leaves, trace = await planner.plan("Give me the best Napoli dough recipe")
        assert worker.calls[0]["role"] == "Mimir-Interpreter"
        assert worker.calls[1]["role"] == "Mimir-Decomposer"
        assert json.dumps(BRIEF) in worker.calls[1]["prompt"]
        assert len(worker.calls) == 4
        assert leaves[-1]["dependencies"] == ["root.formula.hydration", "root.formula.water"]
        assert leaves[1]["dependencies"] == ["root.formula.water"]
        assert trace["tree"][0]["children"]
        assert trace["status"] == "planned"
        assert any(s["interpretation"] == BRIEF and s["status"] == "decomposing" for s in snapshots)
        assert all(c["effort"] == "low" and c["model"] == "agreed" for c in worker.calls)
    asyncio.run(run())


@pytest.mark.parametrize("limit,expected", [("calls", "call limit"), ("depth", "depth limit"), ("leaves", "leaf limit")])
def test_limits_never_admit_broad_or_extra_tasks(limit, expected):
    async def run():
        worker = Fake([{"tasks": [task("formula", atomic=False)]}, {"tasks": [task("water"), task("flour")]}])
        snapshots = []
        planner = RecursivePlanner(worker, max_leaves=1 if limit == "leaves" else 4,
                                  max_depth=1 if limit == "depth" else 2,
                                  budget={"max_calls": 1 if limit == "calls" else 4}, on_checkpoint=snapshots.append)
        with pytest.raises(ConfigurationRequired, match=expected):
            await planner.plan("Dough", BRIEF)
        assert snapshots[-1]["status"] == "incomplete"
    asyncio.run(run())


@pytest.mark.parametrize("change", [{"acceptance_check": ""}, {"operation": "split"}, {"max_input_items": 50}, {"max_input_items": 0}, {"max_output_words": 0}, {"inputs": []}, {"inputs": ["one", "two"]}])
def test_invalid_atomic_contract_cannot_execute(change):
    async def run():
        worker = Fake([{"tasks": [{**task("water"), **change}]}])
        with pytest.raises(ValueError):
            await RecursivePlanner(worker).plan("Dough", BRIEF)
    asyncio.run(run())


def test_cycles_are_rejected_before_leaf_allocation():
    async def run():
        worker = Fake([{"tasks": [task("water", deps=("flour",)), task("flour", deps=("water",))]}])
        planner = RecursivePlanner(worker)
        with pytest.raises(ValueError, match="cyclic"):
            await planner.plan("Dough", BRIEF)
        assert not planner.leaves
    asyncio.run(run())


def test_parent_missing_inputs_survive_recursive_split_and_partial_checkpoint():
    async def run():
        worker = Fake([{"tasks": [task("formula", atomic=False, blocked=("oven",))]},
                       {"tasks": [task("water")]}])
        planner = RecursivePlanner(worker, max_leaves=1)
        await planner.plan("Dough", BRIEF)
        assert planner.state["leaves"][0]["blocked_by"] == ["oven"]
        assert planner.state["status"] == "planned"
    asyncio.run(run())


def test_leaf_reservations_retain_completed_work_and_prevent_branch_overallocation():
    async def run():
        worker = Fake([{"tasks": [task("first"), task("group", atomic=False), task("last")]},
                       {"tasks": [task("water"), task("flour")]}])
        planner = RecursivePlanner(worker, max_leaves=3)
        with pytest.raises(ConfigurationRequired, match="leaf limit"):
            await planner.plan("Dough", BRIEF)
        assert [leaf["id"] for leaf in planner.state["leaves"]] == ["root.first"]
        assert "Leaf budget available to this branch: 1" in worker.calls[1]["prompt"]
        assert planner.state["status"] == "incomplete"
    asyncio.run(run())


def test_domain_rules_are_explicit_context_and_parent_outputs_are_available():
    async def run():
        worker = Fake([{"tasks": [task("source"), task("group", atomic=False, deps=("source",))]},
                       {"tasks": [task("water")]}])
        planner = RecursivePlanner(worker, domain_rules="Dough only: no toppings.")
        await planner.plan("Dough", BRIEF)
        assert "Dough only: no toppings." in worker.calls[0]["prompt"]
        assert '"id": "root.source"' in worker.calls[1]["prompt"]
        assert '"expected_output": "one named quantity"' in worker.calls[1]["prompt"]
        assert planner.state["calls"][0]["prompt"] == worker.calls[0]["prompt"]
        plain_worker = Fake([{"tasks": [task("value")]}])
        await RecursivePlanner(plain_worker).plan("A generic request", BRIEF)
        assert "recipe" not in plain_worker.calls[0]["prompt"].split("INPUT\n")[0].lower()
    asyncio.run(run())


def test_explicit_planning_failure_is_retained_without_fabricating_leaves():
    async def run():
        worker = Fake([{"tasks": [], "planning_error": "One remaining slot cannot cover the component."}])
        planner = RecursivePlanner(worker)
        with pytest.raises(ConfigurationRequired, match="cannot fit"):
            await planner.plan("Dough", BRIEF)
        assert planner.state["planning_error"]["parent"] == "root"
        assert planner.state["status"] == "incomplete"
        assert not planner.leaves
    asyncio.run(run())


def test_non_executable_grouping_may_declare_zero_output_words():
    async def run():
        worker = Fake([{"tasks": [{**task("group", atomic=False), "max_output_words": 0}]},
                       {"tasks": [task("value")]}])
        _, leaves, trace = await RecursivePlanner(worker).plan("Dough", BRIEF)
        assert len(leaves) == 1
        assert trace["tree"][0]["max_output_words"] == 0
    asyncio.run(run())


def test_recursive_contracts_survive_graph_checkpoint_and_preserve_blockers():
    async def run():
        worker = Fake([{"tasks": [task("oven", operation="clarify", blocked=("Oven temperature",))]}])
        graph = await RecursiveDecomposer(worker, mode="swarm", recursive_plan=True).decompose_goal("Dough", task_brief=BRIEF)
        restored = TaskGraph.from_dict(graph.to_dict())
        contract = restored.nodes["root.oven"].input_artifacts["task_contract"]
        assert contract["blocked_by"] == ["Oven temperature"]
        assert restored.nodes["root.oven"].max_answer_words == 80
        assert graph.goal == "Dough"
    asyncio.run(run())


def test_deadline_and_unrestricted_backend_fail_without_research():
    class Slow(Fake):
        async def spawn_restricted(self, **options):
            await asyncio.sleep(2)
    async def run():
        planner = RecursivePlanner(Slow([]), budget={"max_seconds": 1})
        with pytest.raises(TimeoutError):
            await planner.plan("Dough")
        assert planner.state["status"] == "incomplete"
    asyncio.run(run())
    with pytest.raises(ConfigurationRequired, match="text-only"):
        RecursivePlanner(SimpleNamespace())
