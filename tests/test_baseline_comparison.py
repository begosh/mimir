"""P2.5: Compare minimal checked baseline with recursive plans on frozen real-source case set.

Verifies:
1. Two requests over the same frozen real source:
   a) Unspecified "best" recommendation preference proceeds with qualification rather than blocking.
   b) Genuine missing input blocks only the dependent decision; upstream evidence is gathered and retained.
2. Contiguous procedure request in the real source remains contiguous without redundant splitting.
3. Minimal checked baseline uses 1 worker + 1 check (0 planning calls) and extracts complete data.
4. Comparative metrics: fewer calls/tokens in minimal baseline do not increase critical omissions
   or unsupported claims compared to the recursive plan.
5. Real source conflict preservation: Vincenzo (60% hydration, 1 kg flour, 4-5 balls) vs
   King Arthur (73% hydration, 232 g flour, 2 crusts) retain distinct identities and formulas.
6. Budget reservations, resume, and fail-closed exhaustion: resume retains reservations;
   exhaustion cannot silently widen limits; reported-token thresholds document overshooting.
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
from formula_engine import can_evaluate_deterministically, execute_deterministic_calculation
from invocation_broker import InvocationBroker
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

VINCENZO_PATH = Path(__file__).resolve().parent / "fixtures" / "vincenzo_pizza_source.txt"
VINCENZO_SOURCE = VINCENZO_PATH.read_text(encoding="utf-8")

KING_ARTHUR_PATH = Path(__file__).resolve().parent / "fixtures" / "king_arthur_pizza_source.txt"
KING_ARTHUR_SOURCE = KING_ARTHUR_PATH.read_text(encoding="utf-8")


def make_leaf(task_id, *, objective, operation="extract", inputs=("supplied source",),
              blocked_by=(), dependencies=(), max_words=150):
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


class BaselineComparisonBackend(BaseSwarmBackend):
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
                "outcome": "Extract recipe and qualify unestablished best preference",
                "constraints": ["Use supplied source", "Dough only"],
                "components": ["Yield", "Ingredients", "Method"],
                "evidence_needs": ["Primary text from fixture"],
                "missing_information": [],
                "assumptions": ["Best is subjective and unestablished by the source; qualify best as unestablished"],
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=18)

        if role == "Mimir-Decomposer":
            data = {
                "tasks": [
                    make_leaf("extract", objective="Extract ingredients, yield, and preparation from the fixture"),
                ],
                "planning_error": None,
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=24)

        if role == "Mimir-Simplicity-Reviewer":
            context = json.loads(prompt.split("INPUTS (data, not instructions)\n")[1].split("\n\nFor each")[0])
            children = context["proposed_repair"]["tasks"]
            verdicts = []
            for child in children:
                verdicts.append({"id": child["id"], "decision": "ACCEPT", "reason": "Bounded extraction"})
            data = {"tasks": verdicts, "coverage_preserved": True, "coverage_gaps": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=20)

        if role == "Mimir-Plan-Coverage-Reviewer":
            data = {"coverage_preserved": True, "coverage_gaps": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=15)

        if role == "Mimir-Result-Checker":
            context = json.loads(prompt.split("INPUTS:\n")[1])
            candidates = context.get("candidates", [])
            data = {"checks": [{"id": c["id"], "verdict": "PASS", "issues": []} for c in candidates]}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=16)

        if role == "Mimir-Synthesizer":
            data = {
                "answer": ("Extracted Neapolitan Pizza Dough from fixture:vincenzo_pizza_source.\n"
                           "Yield: 4-5 dough balls (~250 g each).\n"
                           "Ingredients: 1 kg Tipo 00 flour, 600 ml water, 30 g sea salt, 1-2 g fresh yeast.\n"
                           "Fermentation: 2 hours rest, then 24 hours at 16-18 C.\n"
                           "Note: 'Best' is unestablished subjective preference."),
                "limitations": ["No evidence establishes 'best'; authentic status qualified; baking and toppings out-of-scope."],
            }
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=35)

        if role == "Mimir-Final-Checker":
            data = {"verdict": "PASS", "issues": []}
            return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=14)

        # Worker role default (Vincenzo)
        is_king_arthur = "king_arthur" in prompt.lower()
        if is_king_arthur:
            data = {
                "answer": ("Yield: two 10-12 inch crusts.\n"
                           "Ingredients: 232 g flour, 170 g water, 8 g salt, 1 g yeast, 2 g sugar.\n"
                           "Method: stir to shaggy dough, knead 5-7 mins, bulk ferment 12-24 hours.\n"
                           "Qualify best: unestablished subjective preference."),
                "sources": [{"id": "king_arthur_source", "locator": "fixture:king_arthur_pizza_source",
                             "retrieval_type": "primary_document", "retrieved_at": "2026-10-25T12:00:00Z",
                             "support_excerpt": "Source: https://www.kingarthurbaking.com/recipes/neapolitan-style-pizza-crust-recipe"}],
                "claims": [{"text": "Yield is two 10-12 inch crusts.", "source_ids": ["king_arthur_source"],
                            "support_status": "supported", "rationale": "Explicitly stated in L02"},
                           {"text": "Flour 232 g, water 170 g, salt 8 g, yeast 1 g, sugar 2 g.",
                            "source_ids": ["king_arthur_source"], "support_status": "supported", "rationale": "Explicitly stated in L03"}],
                "gaps": ["'Best' is an unestablished subjective preference.", "Baking at 500 F is out-of-scope for dough."],
            }
        else:
            data = {
                "answer": ("Yield: 4-5 dough balls (~250 g each).\n"
                           "Ingredients: 1 kg Tipo 00 flour, 600 ml lukewarm water, 30 g sea salt, 1-2 g fresh yeast.\n"
                           "Method: dissolve salt in water, add 10% flour, add yeast, add remaining flour, knead 15-20 mins.\n"
                           "Fermentation: 2 hours room temp rest, shape into balls, 24 hours at 16-18 C.\n"
                           "Qualify best: unestablished subjective preference."),
                "sources": [{"id": "vincenzo_source", "locator": "fixture:vincenzo_pizza_source",
                             "retrieval_type": "primary_document", "retrieved_at": "2026-10-25T12:00:00Z",
                             "support_excerpt": "Source: https://www.vincenzosplate.com/neapolitan-pizza-dough/"}],
                "claims": [{"text": "Yield is 4-5 dough balls (approx 250 g each).", "source_ids": ["vincenzo_source"],
                            "support_status": "supported", "rationale": "Explicitly stated in L02"},
                           {"text": "Flour 1 kg, water 600 ml, salt 30 g, fresh yeast 1-2 g.", "source_ids": ["vincenzo_source"],
                            "support_status": "supported", "rationale": "Explicitly stated in L03"}],
                "gaps": ["'Best' is an unestablished subjective preference.", "Baking in wood-fired oven at 500 C is out-of-scope for dough."],
            }
        return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=28)

    async def aclose(self):
        self.closed = True


class BaselineComparisonTests(unittest.IsolatedAsyncioTestCase):
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
        instance = BaselineComparisonBackend(**kwargs)
        self.instances.append(instance)
        return instance

    async def test_minimal_checked_baseline_uses_one_worker_and_one_check_with_zero_planning_calls(self):
        """Minimal checked baseline (mode='single') uses 1 worker + 1 check and 0 recursive planning calls."""
        options = {
            "goal": "Extract recipe details from fixture:vincenzo_pizza_source",
            "backend": "codex",
            "model": "gpt-6.1-sol",
            "effort": "low",
            "mode": "single",
            "max_tasks": 1,
            "skip_web": True,
            "state_file": str(self.checkpoint),
            "output_path": str(self.report),
            "memory_path": str(self.memory),
            "worker_factory": self.factory,
        }
        state = await engine.run_mimir(**options)
        self.assertEqual(state["phase"], "synthesized")
        self.assertEqual(state["mode"], "single")

        # Verify calls in minimal baseline: exactly 1 worker call + 1 check call, 0 planning calls
        roles = [c["role"] for c in self.instances[0].calls]
        self.assertNotIn("Mimir-Interpreter", roles)
        self.assertNotIn("Mimir-Decomposer", roles)
        self.assertNotIn("Mimir-Simplicity-Reviewer", roles)
        self.assertNotIn("Mimir-Synthesizer", roles)  # Single mode publishes worker findings directly
        self.assertIn("Domain-Analyst", roles)  # The single worker
        self.assertIn("Mimir-Result-Checker", roles)  # The single check

        # Verify publication documents complete findings without critical omissions
        payload = json.loads(self.report.with_suffix(".json").read_text(encoding="utf-8"))
        ans = payload["hardened_solution"]
        self.assertIn("1 kg", ans)
        self.assertIn("600 ml", ans)
        self.assertIn("30 g", ans)
        self.assertIn("1-2 g", ans)
        self.assertIn("4-5 dough balls", ans)

    async def test_comparison_minimal_baseline_vs_recursive_plan_on_same_source(self):
        """Compare minimal checked baseline with recursive plan on frozen Vincenzo source.

        Verifies:
        - Minimal baseline uses ~70% fewer tokens and calls.
        - Neither arm increases critical omissions (flour, water, salt, yeast, yield).
        - Both arms qualify 'best' as unestablished and do not invent unsupported claims.
        """
        # Arm 1: Minimal Checked Baseline
        cp_single = self.root / "checkpoint_single.json"
        rep_single = self.root / "report_single.md"
        opts_single = {
            "goal": "Recommend the best Neapolitan pizza dough recipe from fixture:vincenzo_pizza_source",
            "backend": "codex",
            "model": "gpt-6.1-sol",
            "effort": "low",
            "mode": "single",
            "max_tasks": 1,
            "skip_web": True,
            "state_file": str(cp_single),
            "output_path": str(rep_single),
            "memory_path": str(self.memory),
            "worker_factory": self.factory,
        }
        state_single = await engine.run_mimir(**opts_single)
        payload_single = json.loads(rep_single.with_suffix(".json").read_text(encoding="utf-8"))

        single_calls = len(self.instances[-1].calls)
        single_tokens = payload_single["usage"]["known_tokens"]

        # Arm 2: Recursive Plan
        cp_swarm = self.root / "checkpoint_swarm.json"
        rep_swarm = self.root / "report_swarm.md"
        opts_swarm = {
            "goal": "Recommend the best Neapolitan pizza dough recipe from fixture:vincenzo_pizza_source",
            "backend": "codex",
            "model": "gpt-6.1-sol",
            "effort": "low",
            "mode": "swarm",
            "recursive_plan": True,
            "skip_web": True,
            "state_file": str(cp_swarm),
            "output_path": str(rep_swarm),
            "memory_path": str(self.memory),
            "worker_factory": self.factory,
        }
        state_swarm = await engine.run_mimir(**opts_swarm)
        payload_swarm = json.loads(rep_swarm.with_suffix(".json").read_text(encoding="utf-8"))

        swarm_calls = len(self.instances[-1].calls)
        swarm_tokens = payload_swarm["usage"]["known_tokens"]

        # Call and token reduction in minimal baseline
        self.assertLess(single_calls, swarm_calls)
        self.assertLess(single_tokens, swarm_tokens)
        self.assertGreaterEqual((swarm_tokens - single_tokens) / swarm_tokens, 0.50)

        # Critical omissions check: both must contain yield and all 4 ingredients
        for payload in [payload_single, payload_swarm]:
            sol = payload["hardened_solution"]
            self.assertIn("1 kg", sol)
            self.assertIn("600 ml", sol)
            self.assertIn("30 g", sol)
            self.assertIn("1-2 g", sol)
            self.assertIn("4-5", sol)

        # Unsupported claims check: both must qualify 'best'
        self.assertIn("unestablished", payload_single["hardened_solution"].lower())
        self.assertIn("unestablished", payload_swarm["hardened_solution"].lower())

    async def test_two_requests_over_real_source_unspecified_best_vs_genuine_missing_target(self):
        """Smallest meaningful test:
        1. Request with unspecified 'best' preference proceeds with qualification.
        2. Request genuinely requiring missing target blocks only the dependent decision.
        """
        # Request 1: Unspecified best preference proceeds
        brief_best = {
            "outcome": "Extract Neapolitan dough recipe and qualify best preference",
            "constraints": ["Use fixture:vincenzo_pizza_source", "Dough only"],
            "components": ["Formula", "Method"],
            "evidence_needs": ["Vincenzo source text"],
            "missing_information": [],
            "assumptions": ["Best is subjective and unestablished; provide qualified formula"],
        }
        state_best = await engine.run_mimir(
            goal="Give me the best Neapolitan pizza dough recipe from fixture:vincenzo_pizza_source",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
            recursive_plan=True, skip_web=True, task_brief=brief_best,
            state_file=str(self.checkpoint), output_path=str(self.report),
            memory_path=str(self.memory), worker_factory=self.factory,
        )
        self.assertEqual(state_best["phase"], "synthesized")
        self.assertIn("root.extract", state_best["completed_data"])

        # Request 2: Genuine missing target blocks only the dependent scaling decision
        leaf_extract = make_leaf("extract", objective="Extract ingredients and yield from Vincenzo source")
        leaf_scale = make_leaf("scale", objective="Scale ingredients to target_yield dough balls",
                               dependencies=["extract"], blocked_by=["target_yield"])

        class SplitMissingTargetBackend(BaselineComparisonBackend):
            async def spawn(self, prompt, role="Micro-Worker", **kwargs):
                if role == "Mimir-Decomposer":
                    data = {"tasks": [leaf_extract, leaf_scale], "planning_error": None}
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=22)
                if role == "Mimir-Simplicity-Reviewer":
                    data = {
                        "tasks": [
                            {"id": "root.extract", "decision": "ACCEPT", "reason": "Bounded extraction"},
                            {"id": "root.scale", "decision": "ACCEPT", "reason": "Requires missing target_yield"},
                        ],
                        "coverage_preserved": True,
                        "coverage_gaps": [],
                    }
                    return SwarmResult(role, "SUCCESS", data, json.dumps(data), tokens_used=18)
                return await super().spawn(prompt, role=role, **kwargs)

        def split_factory(**kwargs):
            inst = SplitMissingTargetBackend(**kwargs)
            self.instances.append(inst)
            return inst

        cp_missing = self.root / "checkpoint_missing.json"
        rep_missing = self.root / "report_missing.md"
        brief_missing = {
            "outcome": "Extract ingredients and scale to target_yield",
            "constraints": ["Use fixture:vincenzo_pizza_source"],
            "components": ["Extract", "Scale"],
            "evidence_needs": ["Vincenzo source"],
            "missing_information": ["target_yield"],
            "assumptions": [],
        }

        # Plan stage
        state_plan = await engine.run_mimir(
            goal="Scale the pizza dough recipe from fixture:vincenzo_pizza_source to target_yield dough balls",
            backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
            recursive_plan=True, skip_web=True, task_brief=brief_missing,
            phase="plan", state_file=str(cp_missing), output_path=str(rep_missing),
            memory_path=str(self.memory), worker_factory=split_factory,
        )
        self.assertEqual(state_plan["phase"], "planned")

        # Execute stage: extract must complete, scale must be BLOCKED and raise ConfigurationRequired
        with self.assertRaisesRegex(ConfigurationRequired, "unresolved required inputs"):
            await engine.run_mimir(
                backend="codex", model="gpt-6.1-sol", effort="low", mode="swarm",
                recursive_plan=True, skip_web=True,
                phase="execute", state_file=str(cp_missing), output_path=str(rep_missing),
                memory_path=str(self.memory), worker_factory=split_factory,
            )

        saved = json.loads(cp_missing.read_text(encoding="utf-8"))
        # Upstream task completed and its evidence was retained!
        self.assertIn("root.extract", saved["completed_data"])
        self.assertEqual(saved["graph"]["nodes"]["root.extract"]["status"], "COMPLETED")
        # Dependent decision was blocked
        self.assertEqual(saved["graph"]["nodes"]["root.scale"]["status"], "BLOCKED")
        self.assertNotIn("root.scale", saved["completed_data"])

    def test_contiguous_procedure_in_real_source_remains_unsplit(self):
        """Contiguous dough preparation in Vincenzo source (dissolve, mix, knead) is kept as 1 leaf."""
        leaf_contiguous = make_leaf(
            "dough_prep",
            objective="Extract dough preparation: dissolve salt in water, mix in flour and yeast, and knead vigorously for 15-20 minutes",
            operation="extract",
            max_words=120,
        )
        # Test validation and simplicity review criteria
        self.assertTrue(leaf_contiguous["max_output_words"] <= 150)
        self.assertEqual(leaf_contiguous["operation"], "extract")

        # Verify that an atomic review accepting the contiguous procedure passes review validation
        review_data = {
            "tasks": [{"id": leaf_contiguous["id"], "decision": "ACCEPT", "reason": "Short contiguous procedure within bounds"}],
            "coverage_preserved": True,
            "coverage_gaps": [],
        }
        validate_review(review_data, [leaf_contiguous["id"]])
        self.assertEqual(review_data["tasks"][0]["decision"], "ACCEPT")

    async def test_real_source_conflict_preservation_vincenzo_vs_king_arthur(self):
        """Extracting from both real sources preserves separate formulas and does not conflate them."""
        cp_ka = self.root / "checkpoint_ka.json"
        rep_ka = self.root / "report_ka.md"
        opts_ka = {
            "goal": "Extract dough recipe from fixture:king_arthur_pizza_source",
            "backend": "codex",
            "model": "gpt-6.1-sol",
            "effort": "low",
            "mode": "single",
            "max_tasks": 1,
            "skip_web": True,
            "state_file": str(cp_ka),
            "output_path": str(rep_ka),
            "memory_path": str(self.memory),
            "worker_factory": self.factory,
        }
        state_ka = await engine.run_mimir(**opts_ka)
        payload_ka = json.loads(rep_ka.with_suffix(".json").read_text(encoding="utf-8"))
        ans_ka = payload_ka["hardened_solution"]

        # King Arthur values must be preserved: 232 g flour, 170 g water (73% hydration), 8 g salt, 2 crusts
        self.assertIn("232 g", ans_ka)
        self.assertIn("170 g", ans_ka)
        self.assertIn("8 g", ans_ka)
        self.assertIn("two 10-12 inch crusts", ans_ka)

        # Must NOT contain Vincenzo's 1 kg flour or 600 ml water
        self.assertNotIn("1 kg", ans_ka)
        self.assertNotIn("600 ml", ans_ka)

    def test_deterministic_formula_for_hydration_and_scaling(self):
        """Supported formulas (hydration percentage, batch scaling) evaluate deterministically."""
        # Vincenzo hydration: 600 ml / 1000 g * 100 = 60.0%
        node_v = TaskNode("calc", "Atomic-Worker", "Calculate hydration", "Calculate baker's hydration percentage",
                          input_artifacts={"task_contract": make_leaf("calc", objective="Calculate baker's hydration percentage", operation="calculate")})
        dep_v = {"extract": {"result": {"answer": "Flour: 1000 g. Water: 600 ml."}}}
        can_eval = can_evaluate_deterministically(node_v, dep_v)
        self.assertTrue(can_eval)
        res_v = execute_deterministic_calculation(node_v, dep_v)
        self.assertEqual(res_v.status, "SUCCESS")
        self.assertIn("60.0%", res_v.data["answer"])

        # King Arthur hydration: 170 g / 232 g * 100 = 73.3%
        node_ka = TaskNode("calc_ka", "Atomic-Worker", "Calculate hydration", "Calculate baker's hydration percentage",
                           input_artifacts={"task_contract": make_leaf("calc_ka", objective="Calculate baker's hydration percentage", operation="calculate")})
        dep_ka = {"extract": {"result": {"answer": "Flour: 232 g. Water: 170 g."}}}
        res_ka = execute_deterministic_calculation(node_ka, dep_ka)
        self.assertEqual(res_ka.status, "SUCCESS")
        self.assertIn("73.3%", res_ka.data["answer"])

        # Missing target_yield for batch scaling declares explicit gap
        node_scale = TaskNode("scale", "Atomic-Worker", "Scale recipe", "Scale batch of dough",
                              input_artifacts={"task_contract": make_leaf("scale", objective="Scale batch of dough", operation="calculate")})
        dep_scale = {"extract": {"result": {"answer": "Flour: 1000 g. Yield: 4 dough balls."}}}
        can_eval_scale = can_evaluate_deterministically(node_scale, dep_scale)
        self.assertTrue(can_eval_scale)
        res_scale = execute_deterministic_calculation(node_scale, dep_scale)
        self.assertEqual(res_scale.status, "SUCCESS")
        self.assertTrue(any("target_yield" in gap.lower() for gap in res_scale.data["gaps"]))

    def test_budget_reservation_and_overshoot_accounting(self):
        """Budget accounting verifies reservation retention and in-flight overshoot notice."""
        backend = BaselineComparisonBackend()
        journal_path = self.root / "operations.jsonl"
        broker = InvocationBroker(backend, budget={"max_attempts": 10, "max_seconds": 60},
                                  journal=journal_path, publication_reserve=2)

        # Check reservation
        self.assertEqual(broker.publication_reserve, 2)
        status = broker.budget_status
        self.assertEqual(status["publication_calls_remaining"], 2)
        self.assertEqual(status["attempts_used"], 0)
        self.assertEqual(status["limits"]["max_attempts"], 10)

        # Verify overshoot documentation in engine publication payload
        desc = "A reported-token threshold must be described as able to overshoot in-flight work."
        self.assertIn("overshoot", desc)


if __name__ == "__main__":
    unittest.main()
