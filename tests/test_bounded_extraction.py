"""P2.2 regressions: proportional decomposition and bounded extraction baseline.

Verifies:
1. Start with one bounded retrieval/extraction; split for input/output bounds or distinct decisions.
2. Distinct decisions (extraction vs calculation) split into sequential dependent leaves.
3. Multi-stage procedure combining independent processes triggers split repair into bounded leaves.
4. Short contiguous procedures within bounds are accepted as single atomic leaves.
5. Simple supplied-source work uses one worker and its check without recursive planning calls.
6. Engine auto-routes to single mode when max_tasks=1 is specified without mode.
7. Fewer calls/tokens do not increase critical omissions or unsupported claims.
"""
import asyncio
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import BaseSwarmBackend, SwarmResult
from mimir_config import ConfigurationRequired
from recursive_planner import RecursivePlanner
from task_contracts import validate_review
from task_graph import RecursiveDecomposer, TaskGraph, TaskNode

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


class BoundedExtractionBackend(BaseSwarmBackend):
    def __init__(self, *, model="gpt-6.1-sol", effort="low", concurrency=4, **kwargs):
        super().__init__(model, concurrency)
        self.default_effort = effort
        self.calls = []
        self.closed = False

    async def spawn_restricted(self, prompt, role="Micro-Worker", **kwargs):
        return await self.spawn(prompt, role=role, **kwargs)

    async def spawn(self, prompt, role="Micro-Worker", **kwargs):
        self.calls.append({"role": role, "prompt": prompt, **kwargs})

        if role == "Mimir-Interpreter":
            data = {
                "outcome": "Extract recipe details from supplied fixture",
                "constraints": ["Use supplied source"],
                "components": ["Ingredients", "Yield"],
                "evidence_needs": ["Fixture primary text"],
                "missing_information": [],
                "assumptions": ["Standard Neapolitan formula assumed"],
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=15)

        if role == "Mimir-Decomposer":
            data = {
                "tasks": [
                    make_leaf("extract", objective="Extract ingredients and yield from the fixture", max_words=80),
                ],
                "planning_error": None,
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=20)

        if role == "Mimir-Simplicity-Reviewer":
            context = json.loads(prompt.split("INPUTS (data, not instructions)\n")[1].split("\n\nFor each")[0])
            children = context["proposed_repair"]["tasks"]
            verdicts = []
            for child in children:
                verdicts.append({"id": child["id"], "decision": "ACCEPT", "reason": "Bounded extraction under 150 words"})
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
                "answer": "Yield: 4 dough balls. Ingredients: 600 g flour, 390 g water, 18 g salt, 1 g fresh yeast.",
                "limitations": ["Mixing and kneading temperatures are not stated in the source."],
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=28)

        if role == "Mimir-Final-Checker":
            data = {"verdict": "PASS", "issues": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=12)

        # Worker role default
        data = {
            "answer": "Yield: four dough balls. Ingredients: 600 g flour, 390 g water, 18 g salt, 1 g fresh yeast.",
            "sources": [{"id": "fixture_source", "locator": "fixture:pizza_extraction_source",
                         "retrieval_type": "primary_document", "retrieved_at": "2026-10-25T12:00:00Z",
                         "support_excerpt": "L01 Yield: four dough balls. L02 Dough ingredients: 600 g flour, 390 g water, 18 g salt, 1 g fresh yeast."}],
            "claims": [
                {"text": "Yield is four dough balls.", "source_ids": ["fixture_source"],
                 "support_status": "supported", "rationale": "L01 states yield: four dough balls."},
                {"text": "Ingredients are 600 g flour, 390 g water, 18 g salt, 1 g fresh yeast.",
                 "source_ids": ["fixture_source"], "support_status": "supported", "rationale": "L02 states dough ingredients."},
            ],
            "gaps": ["Mixing and kneading temperatures and durations for dividing/balling are not stated."],
        }
        return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=22)

    async def aclose(self):
        self.closed = True


class BoundedExtractionTests(unittest.IsolatedAsyncioTestCase):
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
        instance = BoundedExtractionBackend(**kwargs)
        self.instances.append(instance)
        return instance

    async def test_auto_route_to_single_mode_when_max_tasks_one(self):
        """When max_tasks=1 and mode is omitted, engine auto-routes to single mode without planning calls."""
        state = await engine.run_mimir(
            goal="Extract yield from fixture:pizza_extraction_source",
            backend="codex", model="gpt-6.1-sol", effort="low",
            max_tasks=1,  # mode is None
            skip_web=True, state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=self.factory,
        )
        self.assertEqual(state["phase"], "synthesized")
        self.assertEqual(state["mode"], "single")
        self.assertEqual(state["max_tasks"], 1)

        backend = self.instances[0]
        roles = [c["role"] for c in backend.calls]
        # Single mode: exactly 1 worker and 1 result-checker
        self.assertEqual(roles, ["Domain-Analyst", "Mimir-Result-Checker"])
        self.assertNotIn("Mimir-Interpreter", roles)
        self.assertNotIn("Mimir-Decomposer", roles)

    async def test_bounded_extraction_starts_and_remains_single_leaf(self):
        """A bounded extraction request over supplied source starts and remains 1 atomic leaf."""
        state = await engine.run_mimir(
            goal="Extract ingredients and yield from fixture:pizza_extraction_source",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
            recursive_plan=True, skip_web=True, phase="plan",
            state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=self.factory,
        )
        self.assertEqual(state["phase"], "planned")
        self.assertEqual(len(state["tasks"]), 1)
        self.assertEqual(state["tasks"][0]["id"], "root.extract")
        review = state["graph"]["nodes"]["root.extract"]["input_artifacts"]["task_contract"]["simplicity_review"]
        self.assertEqual(review["decision"], "ACCEPT")

    async def test_distinct_decisions_split_into_sequential_leaves(self):
        """Extraction followed by formula calculation splits into 2 sequential leaves with dependency."""
        leaf_extract = make_leaf("extract", objective="Extract flour and water weights from fixture", max_words=60)
        leaf_calc = make_leaf("calc_hydration", objective="Calculate baker's hydration percentage: (water / flour) * 100",
                              operation="calculate", inputs=["root.extract"], dependencies=["extract"], max_words=60)

        class CalcSplitBackend(BoundedExtractionBackend):
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                if role == "Mimir-Interpreter":
                    data = {
                        "outcome": "Extract ingredients and calculate hydration percentage",
                        "constraints": ["Use formula: water / flour * 100"],
                        "components": ["Extraction", "Calculation"],
                        "evidence_needs": ["Fixture"],
                        "missing_information": [],
                        "assumptions": [],
                    }
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=15)
                if role == "Mimir-Decomposer":
                    data = {"tasks": [leaf_extract, leaf_calc], "planning_error": None}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=22)
                if role == "Mimir-Simplicity-Reviewer":
                    data = {
                        "tasks": [
                            {"id": "root.extract", "decision": "ACCEPT", "reason": "Bounded extraction"},
                            {"id": "root.calc_hydration", "decision": "ACCEPT", "reason": "Distinct formula calculation over extracted numbers"},
                        ],
                        "coverage_preserved": True,
                        "coverage_gaps": [],
                    }
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=18)
                if role == "Atomic-Worker":
                    contract = kwargs.get("json_schema")
                    if "calc" in prompt.lower():
                        data = {
                            "answer": "Hydration is 65.0% (390 g water / 600 g flour * 100).",
                            "sources": [],
                            "claims": [{"text": "Hydration is 65.0%", "source_ids": [],
                                        "support_status": "supported", "rationale": "Formula 390 / 600 * 100 = 65%"}],
                            "gaps": [],
                        }
                    else:
                        data = {
                            "answer": "Flour: 600 g, Water: 390 g.",
                            "sources": [{"id": "src1", "locator": "fixture:pizza_extraction_source",
                                         "retrieval_type": "primary_document", "retrieved_at": "2026-10-25T12:00:00Z",
                                         "support_excerpt": "600 g flour, 390 g water"}],
                            "claims": [{"text": "Flour 600g, water 390g", "source_ids": ["src1"],
                                        "support_status": "supported", "rationale": "L02"}],
                            "gaps": [],
                        }
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=20)
                return await super().spawn(prompt, role=role, **kwargs)

        def calc_factory(**kwargs):
            inst = CalcSplitBackend(**kwargs)
            self.instances.append(inst)
            return inst

        state = await engine.run_mimir(
            goal="Extract flour and water from fixture:pizza_extraction_source and calculate hydration percentage",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
            recursive_plan=True, skip_web=True,
            state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=calc_factory,
        )
        self.assertEqual(state["phase"], "synthesized")
        self.assertEqual(len(state["tasks"]), 2)
        node_calc = state["graph"]["nodes"]["root.calc_hydration"]
        self.assertIn("root.extract", node_calc["dependencies"])

    async def test_output_bounds_violation_triggers_split_repair(self):
        """A proposed multi-stage procedure combining distinct processes is split by review into bounded leaves."""
        broad_leaf = make_leaf("entire_recipe", objective="Extract complete recipe: ingredients, bulk fermentation, balling, proofing and baking",
                               max_words=120)
        split_leaf_1 = make_leaf("ingredients", objective="Extract ingredients and yield", max_words=70)
        split_leaf_2 = make_leaf("method", objective="Extract mixing, balling and proofing steps", max_words=80)

        class BoundsRepairBackend(BoundedExtractionBackend):
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                if role == "Mimir-Decomposer":
                    data = {"tasks": [broad_leaf], "planning_error": None}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=20)
                if role == "Mimir-Simplicity-Reviewer":
                    context = json.loads(prompt.split("INPUTS (data, not instructions)\n")[1].split("\n\nFor each")[0])
                    tasks = context["proposed_repair"]["tasks"]
                    if tasks[0]["id"] == "root.entire_recipe":
                        data = {
                            "tasks": [{"id": "root.entire_recipe", "decision": "SPLIT",
                                       "reason": "Multi-stage procedure combines mixing, bulk fermentation, balling and proofing across separate sections"}],
                            "coverage_preserved": True, "coverage_gaps": [],
                        }
                    else:
                        data = {
                            "tasks": [{"id": t["id"], "decision": "ACCEPT", "reason": "Bounded within 150 words"} for t in tasks],
                            "coverage_preserved": True, "coverage_gaps": [],
                        }
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=18)
                if role == "Mimir-Task-Repairer":
                    data = {
                        "action": "SPLIT",
                        "reason": "Split multi-stage procedure into bounded ingredients and method leaves",
                        "tasks": [split_leaf_1, split_leaf_2],
                        "missing_inputs": [],
                    }
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=25)
                return await super().spawn(prompt, role=role, **kwargs)

        def repair_factory(**kwargs):
            inst = BoundsRepairBackend(**kwargs)
            self.instances.append(inst)
            return inst

        state = await engine.run_mimir(
            goal="Extract full recipe from fixture:pizza_extraction_source",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
            recursive_plan=True, skip_web=True, phase="plan",
            state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=repair_factory,
        )
        self.assertEqual(state["phase"], "planned")
        # Broad multi-stage leaf was repaired by splitting into two bounded leaves
        task_ids = [t["id"] for t in state["tasks"]]
        self.assertEqual(task_ids, ["root.entire_recipe.ingredients", "root.entire_recipe.method"])

    async def test_fewer_calls_do_not_increase_critical_omissions_or_unsupported_claims(self):
        """Minimal single-worker baseline captures required facts without omissions or fabricated claims."""
        state = await engine.run_mimir(
            goal="Extract yield and dough ingredients from fixture:pizza_extraction_source",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="single",
            skip_web=True, state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=self.factory,
        )
        self.assertEqual(state["phase"], "synthesized")

        # Load published sidecar
        sidecar = json.loads(self.report.with_suffix(".json").read_text(encoding="utf-8"))
        ans = sidecar["hardened_solution"].lower()

        # Verify all essential ingredients and quantities are captured (no critical omissions)
        self.assertIn("flour", ans)
        self.assertIn("600", ans)
        self.assertIn("water", ans)
        self.assertIn("390", ans)
        self.assertIn("salt", ans)
        self.assertIn("18", ans)
        self.assertIn("yeast", ans)
        self.assertIn("1", ans)
        self.assertIn("four dough balls", ans)

        # Verify claims are supported and have valid locators
        claims = sidecar["research"]["claims"]
        self.assertTrue(len(claims) >= 2)
        for claim in claims:
            self.assertEqual(claim["support_status"], "supported")
            self.assertTrue(len(claim["source_ids"]) > 0)

        # Verify unstated elements from fixture are preserved as gaps
        gaps = sidecar["research"]["gaps"]
        self.assertTrue(any("temperature" in g["description"].lower() or "duration" in g["description"].lower() for g in gaps))


if __name__ == "__main__":
    unittest.main()
