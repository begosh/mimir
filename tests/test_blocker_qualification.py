"""P2.1 regressions: distinguish genuine required-input blockers from ambiguity.

Verifies:
1. Two requests over the same frozen source: an unspecified "best" preference proceeds
   with qualification; a genuinely missing target blocks only its dependent decision.
2. Upstream evidence gathering completes and is retained even when a dependent decision is blocked.
3. Contiguous procedures in the source remain contiguous without redundant splitting.
4. Simple supplied-source work uses one worker and one check without recursive planning calls.
5. Uncertainty classification correctly separates subjective preferences from required blockers.
6. Reported-token thresholds explicitly document overshooting of in-flight work.
"""
import asyncio
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import BaseSwarmBackend, SwarmResult, WorkerFailure
from mimir_config import ConfigurationRequired
from recursive_planner import RecursivePlanner
from task_brief import (
    TASK_BRIEF_SCHEMA,
    classify_uncertainty,
    is_genuine_blocker,
    validate_task_brief,
)
from task_contracts import validate_review
from task_graph import RecursiveDecomposer, TaskGraph, TaskNode, TaskStatus

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "pizza_extraction_source.txt"
FIXTURE_SOURCE = FIXTURE_PATH.read_text(encoding="utf-8")


def make_leaf(task_id, *, objective, operation="extract", inputs=("supplied source",),
              blocked_by=(), dependencies=(), max_words=80):
    return {
        "id": task_id,
        "objective": objective,
        "atomic": True,
        "operation": operation,
        "inputs": list(inputs),
        "expected_output": "Extracted details",
        "acceptance_check": "Matches supplied source",
        "blocked_by": list(blocked_by),
        "dependencies": list(dependencies),
        "max_input_items": len(inputs),
        "max_output_words": max_words,
    }


class BlockerFixtureBackend(BaseSwarmBackend):
    def __init__(self, *, model="gpt-6.1-sol", effort="low", concurrency=4, **kwargs):
        super().__init__(model, concurrency)
        self.default_effort = effort
        self.calls = []
        self.closed = False

    async def spawn_restricted(self, prompt, role="Micro-Worker", **kwargs):
        return await self.spawn(prompt, role=role, **kwargs)

    async def spawn(self, prompt, role="Micro-Worker", **kwargs):
        self.calls.append({"role": role, "prompt": prompt, **kwargs})
        field = (kwargs.get("json_schema") or {}).get("required", [None])[0]

        if role == "Mimir-Interpreter":
            data = {
                "outcome": "Extract recipe and qualify unestablished best preference",
                "constraints": ["Use supplied source"],
                "components": ["Ingredients", "Method"],
                "evidence_needs": ["Primary text from fixture"],
                "missing_information": [],
                "assumptions": ["Best is subjective and unestablished by the fixture; assume standard formula"],
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=15)

        if role == "Mimir-Decomposer":
            # Decompose into extraction task
            data = {
                "tasks": [
                    make_leaf("extract", objective="Extract ingredients and yield from the fixture"),
                ],
                "planning_error": None,
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=25)

        if role == "Mimir-Simplicity-Reviewer":
            context = json.loads(prompt.split("INPUTS (data, not instructions)\n")[1].split("\n\nFor each")[0])
            children = context["proposed_repair"]["tasks"]
            verdicts = []
            for child in children:
                verdicts.append({"id": child["id"], "decision": "ACCEPT", "reason": "Bounded extraction"})
            data = {"tasks": verdicts, "coverage_preserved": True, "coverage_gaps": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=18)

        if role == "Mimir-Plan-Coverage-Reviewer":
            data = {"coverage_preserved": True, "coverage_gaps": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=12)

        if role == "Mimir-Result-Checker":
            context = json.loads(prompt.split("INPUTS:\n")[1])
            candidates = context.get("candidates", [])
            data = {"checks": [{"id": c["id"], "verdict": "PASS", "issues": []} for c in candidates]}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=14)

        if role == "Mimir-Synthesizer":
            data = {
                "answer": "Extracted recipe from fixture:pizza_extraction_source. Note that 'best' is unestablished by the synthetic fixture.",
                "limitations": ["No evidence establishes 'best'; fixture explicitly disclaims authenticity."],
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=30)

        if role == "Mimir-Final-Checker":
            data = {"verdict": "PASS", "issues": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=12)

        # Worker role default
        data = {
            "answer": "L01 Yield: four dough balls. L02 Ingredients: 600 g flour, 390 g water, 18 g salt, 1 g yeast. Qualify best: unestablished.",
            "sources": [{"id": "fixture_source", "locator": "fixture:pizza_extraction_source",
                         "retrieval_type": "primary_document", "retrieved_at": "2026-10-25T12:00:00Z",
                         "support_excerpt": "SYNTHETIC TEST FIXTURE: not an authentic or recommended pizza recipe."}],
            "claims": [{"text": "Yield is four dough balls.", "source_ids": ["fixture_source"],
                        "support_status": "supported", "rationale": "Explicitly stated in L01"}],
            "gaps": ["Best is unestablished by the synthetic fixture."],
        }
        return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=22)

    async def aclose(self):
        self.closed = True


class BlockerQualificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.checkpoint = self.root / "checkpoint.json"
        self.report = self.root / "report.md"
        self.memory = self.root / "guidance" / "LEARNINGS.md"
        self.instances = []

    def tearDown(self):
        self.temporary.cleanup()

    def factory(self, **kwargs):
        instance = BlockerFixtureBackend(**kwargs)
        self.instances.append(instance)
        return instance

    def test_uncertainty_classification(self):
        """Unspecified preferences are distinguished from genuine required blockers."""
        self.assertEqual(classify_uncertainty("What is the best dough recipe"), "unspecified_preference")
        self.assertEqual(classify_uncertainty("Optimal fermentation time"), "unspecified_preference")
        self.assertEqual(classify_uncertainty("User's recommended style"), "unspecified_preference")
        self.assertEqual(classify_uncertainty("Favorite topping"), "unspecified_preference")
        self.assertEqual(classify_uncertainty("Target batch size in dough balls"), "required_input_blocker")
        self.assertEqual(classify_uncertainty("User's oven maximum temperature"), "required_input_blocker")
        self.assertEqual(classify_uncertainty("Oven type (wood-fired vs home electric)"), "required_input_blocker")
        self.assertFalse(is_genuine_blocker("best recipe choice"))
        self.assertTrue(is_genuine_blocker("target quantity"))

    def test_task_brief_schema_accepts_assumptions(self):
        """Task brief schema accepts explicit assumptions while requiring core fields."""
        brief = {
            "outcome": "Neapolitan recipe",
            "constraints": ["Dough only"],
            "components": ["Formula"],
            "evidence_needs": ["Fixture"],
            "missing_information": [],
            "assumptions": ["Assuming 65% hydration standard formula; qualify best as unestablished"],
        }
        validated = validate_task_brief(brief)
        self.assertEqual(validated["assumptions"], brief["assumptions"])

    async def test_request_with_unspecified_best_preference_proceeds_with_qualification(self):
        """Request 1: Unspecified 'best' preference does not block retrieval and proceeds with qualification."""
        options = {
            "goal": "Recommend the best Neapolitan pizza dough recipe from fixture:pizza_extraction_source",
            "backend": "codex",
            "model": "gpt-6.1-sol",
            "effort": "low",
            "mode": "swarm",
            "recursive_plan": True,
            "skip_web": True,
            "state_file": str(self.checkpoint),
            "output_path": str(self.report),
            "memory_path": str(self.memory),
            "worker_factory": self.factory,
        }
        state = await engine.run_mimir(**options)
        self.assertEqual(state["phase"], "synthesized")
        self.assertIn("root.extract", state["completed_data"])

        # Verify publication documents qualification of "best"
        payload = json.loads(self.report.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertIn("best", payload["hardened_solution"].lower())
        self.assertIn("unestablished", payload["hardened_solution"].lower())
        self.assertTrue(any("best" in gap.lower() for gap in payload["synthesis_result"]["limitations"]))

        # Verify token scope describes overshooting
        self.assertIn("overshoot", payload["usage"]["token_scope"])

    async def test_genuine_missing_target_blocks_only_dependent_decision(self):
        """Request 2: Missing target blocks only the dependent decision; upstream evidence is gathered and retained."""
        brief = {
            "outcome": "Extract ingredients and scale for target batch size",
            "constraints": ["Use fixture"],
            "components": ["Extract", "Scale"],
            "evidence_needs": ["Fixture source"],
            "missing_information": ["Target batch quantity"],
            "assumptions": [],
        }

        # Graph has two nodes:
        # 1. extract: can run, inputs from source, NO blocked_by
        # 2. scale: depends on extract, blocked_by = ["Target batch quantity"]
        leaf_extract = make_leaf("extract", objective="Extract ingredients and yield from fixture")
        leaf_scale = make_leaf("scale", objective="Scale ingredients for target batch quantity",
                               dependencies=["extract"],
                               blocked_by=["Target batch quantity"])

        class SplitPlannerBackend(BlockerFixtureBackend):
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                if role == "Mimir-Decomposer":
                    data = {"tasks": [leaf_extract, leaf_scale], "planning_error": None}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=20)
                if role == "Mimir-Simplicity-Reviewer":
                    data = {
                        "tasks": [
                            {"id": "root.extract", "decision": "ACCEPT", "reason": "Bounded extraction"},
                            {"id": "root.scale", "decision": "ACCEPT", "reason": "Requires target batch quantity"},
                        ],
                        "coverage_preserved": True,
                        "coverage_gaps": [],
                    }
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=18)
                return await super().spawn(prompt, role=role, **kwargs)

        def split_factory(**kwargs):
            inst = SplitPlannerBackend(**kwargs)
            self.instances.append(inst)
            return inst

        # Run plan stage
        state = await engine.run_mimir(
            goal="Extract recipe from fixture:pizza_extraction_source and scale for target batch quantity",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
            recursive_plan=True, skip_web=True, task_brief=brief,
            phase="plan", state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=split_factory,
        )
        self.assertEqual(state["phase"], "planned")

        # Run execute stage: upstream extract should succeed; scale should block
        with self.assertRaisesRegex(ConfigurationRequired, "unresolved required inputs"):
            await engine.run_mimir(phase="execute", state_file=str(self.checkpoint), worker_factory=split_factory)

        saved = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        # Upstream task completed and its evidence was retained!
        self.assertIn("root.extract", saved["completed_data"])
        self.assertEqual(saved["graph"]["nodes"]["root.extract"]["status"], "COMPLETED")
        # Dependent decision was blocked
        self.assertEqual(saved["graph"]["nodes"]["root.scale"]["status"], "BLOCKED")
        self.assertNotIn("root.scale", saved["completed_data"])

    async def test_contiguous_procedure_case_preserves_single_operation_without_redundant_split(self):
        """Contiguous mixing and kneading procedure remains one bounded leaf rather than redundantly split."""
        leaf_contiguous = make_leaf("mix_knead",
                                    objective="Extract the contiguous mixing and kneading procedure (L03-L04) from the fixture",
                                    max_words=80)

        class ContiguousBackend(BlockerFixtureBackend):
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                if role == "Mimir-Decomposer":
                    data = {"tasks": [leaf_contiguous], "planning_error": None}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=15)
                if role == "Mimir-Simplicity-Reviewer":
                    # Verify review accepts contiguous procedure without requiring split
                    context = json.loads(prompt.split("INPUTS (data, not instructions)\n")[1].split("\n\nFor each")[0])
                    tasks = context["proposed_repair"]["tasks"]
                    assert len(tasks) == 1
                    assert tasks[0]["id"] == "root.mix_knead"
                    data = {"tasks": [{"id": "root.mix_knead", "decision": "ACCEPT",
                                       "reason": "Short contiguous procedure requiring faithful extraction"}],
                            "coverage_preserved": True, "coverage_gaps": []}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=18)
                return await super().spawn(prompt, role=role, **kwargs)

        def contiguous_factory(**kwargs):
            inst = ContiguousBackend(**kwargs)
            self.instances.append(inst)
            return inst

        state = await engine.run_mimir(
            goal="Extract dough mixing and kneading from fixture:pizza_extraction_source",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
            recursive_plan=True, skip_web=True, phase="plan",
            state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=contiguous_factory,
        )
        self.assertEqual(len(state["tasks"]), 1)
        self.assertEqual(state["tasks"][0]["id"], "root.mix_knead")
        # Simplicity review accepted it as one leaf without forcing a split
        review = state["graph"]["nodes"]["root.mix_knead"]["input_artifacts"]["task_contract"]["simplicity_review"]
        self.assertEqual(review["decision"], "ACCEPT")

    async def test_simple_supplied_source_work_uses_single_worker_and_check(self):
        """Simple supplied-source work uses one worker and its check without recursive planning calls."""
        state = await engine.run_mimir(
            goal="Extract declared yield from fixture:pizza_extraction_source",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="single",
            skip_web=True, state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=self.factory,
        )
        self.assertEqual(state["phase"], "synthesized")
        backend_instance = self.instances[0]
        # In single mode: exactly one domain-analyst worker and one result-checker
        roles = [c["role"] for c in backend_instance.calls]
        self.assertEqual(roles, ["Domain-Analyst", "Mimir-Result-Checker"])
        # Zero planning/decomposition calls
        self.assertNotIn("Mimir-Interpreter", roles)
        self.assertNotIn("Mimir-Decomposer", roles)
        self.assertNotIn("Mimir-Simplicity-Reviewer", roles)


if __name__ == "__main__":
    unittest.main()
