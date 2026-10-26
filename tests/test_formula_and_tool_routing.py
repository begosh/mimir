"""P2.3 regressions: deterministic formula computation and explicit tool need routing.

Verifies:
1. Deterministic computation for explicit supported formulas (hydration, baker's percentage, scaling, sum).
2. Missing operands are detected and reported truthfully in gaps without guessing.
3. Deterministic calculation verification rejects contradictory arithmetic results in the result gate.
4. Tasks with needs_tools=False (e.g. critique, text extraction, calculation) route to spawn_restricted.
5. Tasks with needs_tools=True (e.g. evidence, alternatives, retrieve) route to spawn.
"""
import asyncio
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import BaseSwarmBackend, SwarmResult
from formula_engine import (
    can_evaluate_deterministically,
    check_calculation,
    execute_deterministic_calculation,
    extract_quantities,
    identify_formula,
    safe_eval_expression,
)
from mimir_config import ConfigurationRequired
from scheduler import execute_graph
from task_contracts import validate_review
from task_graph import RecursiveDecomposer, TaskGraph, TaskNode

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "pizza_extraction_source.txt"
FIXTURE_SOURCE = FIXTURE_PATH.read_text(encoding="utf-8")


def make_leaf(task_id, *, objective, operation="extract", inputs=("supplied source",),
              blocked_by=(), dependencies=(), max_words=80, formula=None):
    contract = {
        "id": task_id,
        "objective": objective,
        "atomic": True,
        "operation": operation,
        "inputs": list(inputs),
        "expected_output": "Extracted or calculated details",
        "acceptance_check": "Matches source or formula",
        "blocked_by": list(blocked_by),
        "dependencies": list(dependencies),
        "max_input_items": len(inputs),
        "max_output_words": max_words,
    }
    if formula:
        contract["formula"] = formula
    return contract


class RoutingTrackerBackend(BaseSwarmBackend):
    """Tracks whether spawn (native tools) or spawn_restricted (text API) was called per role."""
    def __init__(self, *, model="gpt-6.1-sol", effort="low", concurrency=4, **kwargs):
        super().__init__(model, concurrency)
        self.default_effort = effort
        self.spawn_calls = []
        self.spawn_restricted_calls = []
        self.closed = False

    async def spawn_restricted(self, prompt, role="Micro-Worker", **kwargs):
        self.spawn_restricted_calls.append({"role": role, "prompt": prompt, **kwargs})
        return await self._dispatch_response(prompt, role, restricted=True, **kwargs)

    async def spawn(self, prompt, role="Micro-Worker", **kwargs):
        self.spawn_calls.append({"role": role, "prompt": prompt, **kwargs})
        return await self._dispatch_response(prompt, role, restricted=False, **kwargs)

    async def _dispatch_response(self, prompt, role, restricted, **kwargs):
        if role == "Mimir-Interpreter":
            data = {
                "outcome": "Formula and tool routing test",
                "constraints": [],
                "components": ["Specialists", "Critic"],
                "evidence_needs": ["Fixture"],
                "missing_information": [],
                "assumptions": [],
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=10)

        if role == "Mimir-Result-Checker":
            context = json.loads(prompt.split("INPUTS:\n")[1])
            candidates = context.get("candidates", [])
            data = {"checks": [{"id": c["id"], "verdict": "PASS", "issues": []} for c in candidates]}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=12)

        if role == "Mimir-Synthesizer":
            data = {"answer": "Synthesized review answer", "limitations": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=20)

        if role == "Mimir-Final-Checker":
            data = {"verdict": "PASS", "issues": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=10)

        # Worker roles
        data = {
            "answer": f"Report from {role} (restricted={restricted}): 600 g flour, 390 g water.",
            "sources": [{"id": "src_fixture", "locator": str(FIXTURE_PATH), "retrieval_type": "local_file",
                         "retrieved_at": "2026-10-25T12:00:00Z",
                         "support_excerpt": "SYNTHETIC TEST FIXTURE: not an authentic or recommended pizza recipe."}],
            "claims": [{"text": f"Claim from {role}", "source_ids": ["src_fixture"],
                        "support_status": "supported", "rationale": "Direct rationale"}],
            "gaps": [],
        }
        return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=15)

    async def aclose(self):
        self.closed = True


class FormulaAndToolRoutingTests(unittest.IsolatedAsyncioTestCase):
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
        inst = RoutingTrackerBackend(**kwargs)
        self.instances.append(inst)
        return inst

    def test_extract_quantities_and_ast_evaluation(self):
        """Quantities are correctly extracted from recipe text and evaluated via safe AST expressions."""
        text = "L02 Dough ingredients: 600 g flour, 390 g water, 18 g salt, 1 g fresh yeast. L01 Yield: four dough balls."
        q = extract_quantities(text)
        self.assertEqual(q["flour"], 600.0)
        self.assertEqual(q["water"], 390.0)
        self.assertEqual(q["salt"], 18.0)
        self.assertEqual(q["yeast"], 1.0)
        self.assertEqual(q["yield"], 4.0)

        # Hydration
        hydration = safe_eval_expression("(water / flour) * 100", q)
        self.assertEqual(hydration, 65.0)

        # Salt baker's percentage
        salt_pct = safe_eval_expression("(salt / flour) * 100", q)
        self.assertEqual(salt_pct, 3.0)

        # Total dough weight
        total = safe_eval_expression("flour + water + salt + yeast", q)
        self.assertEqual(total, 1009.0)

        # Scaling to 6 balls
        q["target_yield"] = 6.0
        q["base_yield"] = 4.0
        scaled_flour = safe_eval_expression("flour * (target_yield / base_yield)", q)
        self.assertEqual(scaled_flour, 900.0)

    def test_deterministic_calculation_execution_zero_tokens(self):
        """calculate leaf executes deterministically with exact arithmetic and 0 tokens."""
        node = TaskNode(
            id="calc_hydration", role="Atomic-Worker", title="Calculate hydration",
            prompt="Calculate baker's hydration percentage: (water / flour) * 100",
            input_artifacts={"task_contract": make_leaf("calc_hydration",
                objective="Calculate baker's hydration percentage: (water / flour) * 100",
                operation="calculate")},
            needs_tools=False,
        )
        dep_data = {
            "root.extract": {
                "answer": "Flour: 600 g, Water: 390 g, Salt: 18 g, Yeast: 1 g.",
                "claims": [{"text": "600 g flour, 390 g water"}],
                "sources": [],
            }
        }
        self.assertTrue(can_evaluate_deterministically(node, dep_data))
        res = execute_deterministic_calculation(node, dep_data)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.tokens_used, 0)
        self.assertIn("65.0%", res.data["answer"])
        self.assertEqual(res.data["gaps"], [])

    def test_missing_operands_reported_in_gaps(self):
        """When required operands are absent, deterministic calculation reports missing operands in gaps."""
        node = TaskNode(
            id="calc_hydration", role="Atomic-Worker", title="Calculate hydration",
            prompt="Calculate baker's hydration percentage: (water / flour) * 100",
            input_artifacts={"task_contract": make_leaf("calc_hydration",
                objective="Calculate baker's hydration percentage: (water / flour) * 100",
                operation="calculate")},
            needs_tools=False,
        )
        dep_data = {
            "root.extract": {
                "answer": "Flour: 600 g. Water amount was not specified.",
                "claims": [],
                "sources": [],
            }
        }
        res = execute_deterministic_calculation(node, dep_data)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.tokens_used, 0)
        self.assertIn("missing required operand", res.data["answer"].lower())
        self.assertTrue(any("water" in g.lower() for g in res.data["gaps"]))

    def test_check_calculation_verifies_correct_value_and_fails_contradiction(self):
        """Result gate check_calculation verifies correct arithmetic and fails contradictory numbers."""
        node = TaskNode(
            id="calc_hydration", role="Atomic-Worker", title="Calculate hydration",
            prompt="Calculate baker's hydration percentage: (water / flour) * 100",
            input_artifacts={"task_contract": make_leaf("calc_hydration",
                objective="Calculate baker's hydration percentage: (water / flour) * 100",
                operation="calculate")},
            needs_tools=False,
        )
        dep_data = {
            "root.extract": {
                "answer": "600 g flour, 390 g water.",
                "claims": [], "sources": [],
            }
        }
        # Correct calculation
        good_result = {
            "answer": "Hydration is 65.0% based on 390g water and 600g flour.",
            "claims": [{"text": "Hydration is 65.0%"}],
            "gaps": [],
        }
        verdict = check_calculation(good_result, node, dep_data)
        self.assertEqual(verdict["verdict"], "REVIEW")

        # Contradictory calculation (e.g. 72.5%)
        bad_result = {
            "answer": "Hydration is 72.5% based on 390g water and 600g flour.",
            "claims": [{"text": "Hydration is 72.5%"}],
            "gaps": [],
        }
        verdict_bad = check_calculation(bad_result, node, dep_data)
        self.assertEqual(verdict_bad["verdict"], "FAIL")
        self.assertIn("contradicts", verdict_bad["issues"][0])

    async def test_review_mode_routes_critique_to_spawn_restricted_and_specialists_to_spawn(self):
        """In review mode, specialists route to spawn (native tools) while critique routes to spawn_restricted."""
        state = await engine.run_mimir(
            goal="Review the codebase architecture and evaluate alternatives",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="review",
            skip_web=True, state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=self.factory,
        )
        self.assertEqual(state["phase"], "synthesized")

        backend = self.instances[0]
        # Specialists with needs_tools=True dispatched to spawn
        spawn_roles = [c["role"] for c in backend.spawn_calls]
        self.assertIn("Domain-Analyst", spawn_roles)
        self.assertIn("Code-Architect", spawn_roles)
        self.assertNotIn("Red-Team-Critic", spawn_roles)

        # Critique (needs_tools=False) dispatched to spawn_restricted
        restricted_roles = [c["role"] for c in backend.spawn_restricted_calls]
        self.assertIn("Red-Team-Critic", restricted_roles)
        self.assertIn("Mimir-Synthesizer", restricted_roles)
        self.assertIn("Mimir-Final-Checker", restricted_roles)

    async def test_atomic_tasks_route_by_operation_tool_need(self):
        """Atomic extract and calculate tasks route to spawn_restricted while retrieve routes to spawn."""
        leaf_retrieve = make_leaf("get_source", objective="Retrieve source document", operation="retrieve",
                                  inputs=[str(FIXTURE_PATH)])
        leaf_extract = make_leaf("extract", objective="Extract ingredients", operation="extract", dependencies=["get_source"])
        leaf_calc = make_leaf("calc", objective="Calculate hydration: (water / flour) * 100", operation="calculate", dependencies=["extract"])

        graph = TaskGraph("Test tool need routing")
        graph.add_node(TaskNode("get_source", "Atomic-Worker", "Retrieve", "Retrieve document",
                                dependencies=set(), needs_tools=True,
                                input_artifacts={"task_contract": leaf_retrieve, "worker_wrapper": "atomic_v1"}))
        graph.add_node(TaskNode("extract", "Atomic-Worker", "Extract", "Extract ingredients",
                                dependencies={"get_source"}, needs_tools=False,
                                input_artifacts={"task_contract": leaf_extract, "worker_wrapper": "atomic_v1"}))
        graph.add_node(TaskNode("calc", "Atomic-Worker", "Calc", "Calculate hydration",
                                dependencies={"extract"}, needs_tools=False,
                                input_artifacts={"task_contract": leaf_calc, "worker_wrapper": "atomic_v1"}))

        backend = self.factory()
        results = await execute_graph(graph, backend)
        self.assertIn("get_source", results)
        self.assertIn("extract", results)
        self.assertIn("calc", results)

        # Retrieve used spawn (native tools)
        spawn_roles = [c["role"] for c in backend.spawn_calls]
        self.assertEqual(len(spawn_roles), 1)
        self.assertEqual(spawn_roles[0], "Atomic-Worker")

        # Extract used spawn_restricted (text API)
        restricted_roles = [c["role"] for c in backend.spawn_restricted_calls]
        self.assertIn("Atomic-Worker", restricted_roles)

        # Calc executed deterministically (0 model calls)
        self.assertIn("65.0%", results["calc"]["result"]["answer"])


if __name__ == "__main__":
    unittest.main()
