"""Policy budgets and source-to-claim qualification, without live models."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research_contract import aggregate_research_results, audit_final_references, normalize_worker_result, worker_result_schema
from task_graph import RecursiveDecomposer, TaskGraph


def result(**changes):
    value = {"answer": "Behavior is documented at https://example.test/doc.",
             "sources": [{"id": "doc", "locator": "https://example.test/doc", "retrieval_type": "primary_document",
                          "retrieved_at": "2026-10-22T00:00:00Z", "support_excerpt": "Behavior is explicit."}],
             "claims": [{"text": "Behavior is documented.", "source_ids": ["doc"], "support_status": "supported", "rationale": "Direct documentation."}],
             "gaps": []}
    value.update(changes)
    return value


class Worker:
    def __init__(self, tasks=None):
        self.calls = []
        self.tasks = tasks

    async def spawn(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(status="SUCCESS", data={"tasks": self.tasks}, raw_response="")


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_and_review_are_deterministic_without_planning_calls(self):
        for mode, count in (("single", 1), ("review", 3)):
            worker = Worker()
            graph = await RecursiveDecomposer(worker, mode=mode).decompose_goal("Investigate current code")
            self.assertFalse(worker.calls)
            self.assertEqual(len(graph.nodes), count)
            self.assertTrue(all(n.json_schema == worker_result_schema(n.max_answer_words) for n in graph.nodes.values()))
            self.assertEqual(TaskGraph.from_dict(graph.to_dict()).to_dict(), graph.to_dict())
            if mode == "review":
                self.assertEqual(graph.nodes["critique"].dependencies, {"evidence", "alternatives"})
                self.assertTrue(graph.nodes["critique"].required_evidence)
            self.assertFalse(any("Synthesizer" in n.role for n in graph.nodes.values()))

    async def test_swarm_enforces_budget_even_if_provider_ignores_schema(self):
        tasks = [{"id": str(i), "role": "Domain-Analyst", "title": "Investigate", "objective": "Read evidence", "dependencies": []} for i in range(5)]
        worker = Worker(tasks)
        with self.assertRaisesRegex(ValueError, "budget"):
            await RecursiveDecomposer(worker, mode="swarm", max_tasks=4).decompose_goal("review")
        self.assertEqual(worker.calls[0]["json_schema"]["properties"]["tasks"]["maxItems"], 4)

    async def test_swarm_interprets_before_task_decomposition_with_restricted_planning(self):
        brief = {"outcome": "Recipe", "constraints": [], "components": ["Dough", "Baking"],
                 "evidence_needs": ["Dough method"], "missing_information": ["Oven temperature"]}
        class Planner(Worker):
            async def spawn_restricted(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(status="SUCCESS", data={"task_brief": brief, "tasks": [
                    {"id": "dough", "role": "Analyst", "title": "Dough", "objective": "Resolve dough method", "dependencies": []}]}, raw_response="")
        worker = Planner()
        graph = await RecursiveDecomposer(worker, mode="swarm").decompose_goal("Pizza recipe")
        self.assertEqual(len(worker.calls), 1)
        self.assertIn("Do not search", worker.calls[0]["prompt"])
        self.assertIn("task_brief", worker.calls[0]["json_schema"]["required"])
        self.assertIn("Oven temperature", graph.nodes["dough"].prompt)
        self.assertIn("Before retrieving evidence", graph.nodes["dough"].prompt)

    def test_invalid_task_brief_is_rejected_without_inventing_constraints(self):
        from task_brief import validate_task_brief
        with self.assertRaisesRegex(ValueError, "Task brief requires"):
            validate_task_brief({"outcome": "Pizza", "invented": "Use home oven"})

    async def test_swarm_missing_brief_never_executes_tasks(self):
        worker = Worker([{"id": "dough", "role": "Analyst", "title": "Dough", "objective": "Resolve dough", "dependencies": []}])
        with self.assertRaisesRegex(ValueError, "must return a task_brief"):
            await RecursiveDecomposer(worker, mode="swarm").decompose_goal("Pizza")
        self.assertEqual(len(worker.calls), 1)

    async def test_role_assignments_are_isolated_without_losing_shared_constraints(self):
        goal = ("Inspect only approved.py.\n\n"
                "Evidence specialist: EVIDENCE ONLY. Alternatives specialist: ALTERNATIVES ONLY. "
                "Critic: CRITIC ONLY. Final synthesis: SYNTHESIS ONLY.\n\n"
                "Keep conflicts. Do not change files.")
        graph = await RecursiveDecomposer(Worker(), mode="review").decompose_goal(goal)
        assignments = {"evidence": "EVIDENCE ONLY", "alternatives": "ALTERNATIVES ONLY", "critique": "CRITIC ONLY"}
        for key, node in graph.nodes.items():
            self.assertIn(assignments[key], node.prompt)
            self.assertIn("Inspect only approved.py", node.prompt)
            self.assertIn("Keep conflicts. Do not change files.", node.prompt)
            self.assertNotIn("SYNTHESIS ONLY", node.prompt)
            for other, instruction in assignments.items():
                if other != key:
                    self.assertNotIn(instruction, node.prompt)
        self.assertEqual(graph.goal, goal)
        self.assertEqual(graph.nodes["critique"].max_answer_words, 180)

    def test_unlabelled_role_mentions_are_preserved(self):
        from task_graph import separate_review_assignments
        goal = "The text says Critic: is a role.\n\nPreserve this shared constraint."
        self.assertEqual(separate_review_assignments(goal), (goal, {}))

    async def test_swarm_cannot_add_redundant_executive(self):
        worker = Worker([{"id": "exec", "role": "Executive-Synthesizer", "title": "Combine", "objective": "Combine"}])
        with self.assertRaisesRegex(ValueError, "redundant"):
            await RecursiveDecomposer(worker, mode="swarm").decompose_goal("review")

    def test_invalid_and_too_small_policy_budgets_are_explicit(self):
        for value in (True, 0, -1, 17, "4"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RecursiveDecomposer(Worker(), max_tasks=value)
        with self.assertRaisesRegex(ValueError, "three"):
            RecursiveDecomposer(Worker(), max_tasks=2)


class ResearchContractTests(unittest.TestCase):
    def test_well_formed_support_is_reported_never_verified_or_complete(self):
        value = result()
        value["independently_verified"] = True
        normalized = normalize_worker_result(value)
        self.assertEqual(normalized["evidence_summary"]["coverage"], "reported")
        self.assertFalse(normalized["evidence_summary"]["independently_verified"])
        self.assertEqual(normalized["evidence_summary"]["reported_supported_claims"], 1)

    def test_legacy_and_empty_structured_evidence_stay_unknown(self):
        for value in ("Plausible answer [citation]", {"answer": "Recommendation", "sources": [], "claims": [], "gaps": []}):
            self.assertEqual(normalize_worker_result(value)["evidence_summary"]["coverage"], "unknown")

    def test_gap_missing_links_discovery_conflicts_and_duplicates_are_partial(self):
        variants = [result(gaps=["Required primary source inaccessible"])]
        value = result(); value["claims"][0]["source_ids"] = ["missing"]; variants.append(value)
        value = result(); value["sources"][0]["retrieval_type"] = "search_snippet"; variants.append(value)
        value = result(); value["claims"][0]["support_status"] = "contradicted"; variants.append(value)
        value = result(); value["sources"].append(dict(value["sources"][0])); variants.append(value)
        value = result(); value["sources"][0]["retrieved_at"] = ""; variants.append(value)
        for value in variants:
            with self.subTest(value=value):
                summary = normalize_worker_result(value)["evidence_summary"]
                self.assertEqual(summary["coverage"], "partial")
                self.assertFalse(summary["independently_verified"])

    def test_aggregation_retains_task_identity_and_gaps_and_audits_reference_presence(self):
        registry = aggregate_research_results({"a": {"result": result()}, "b": {"result": result(gaps=["Missing private record"])}})
        self.assertEqual(registry["coverage"], "partial")
        self.assertEqual([s["id"] for s in registry["sources"]], ["a:doc", "b:doc"])
        self.assertEqual(registry["claims"][0]["source_ids"], ["a:doc"])
        self.assertEqual(registry["gaps"], [{"task_id": "b", "description": "Missing private record"}])
        self.assertFalse(audit_final_references("No citations", registry)["reference_presence_passed"])
        self.assertTrue(audit_final_references("https://example.test/doc", registry)["reference_presence_passed"])
        self.assertFalse(registry["independently_verified"])

    def test_malformed_records_do_not_promote_support(self):
        value = result(sources=[None], claims=[{"text": "unsupported"}], gaps="none")
        normalized = normalize_worker_result(value)
        self.assertEqual(normalized["evidence_summary"]["coverage"], "partial")
        self.assertEqual(normalized["evidence_summary"]["linked_claims"], 0)
        value = result()
        value["claims"][0]["support_status"] = {"supported": True}
        self.assertEqual(normalize_worker_result(value)["evidence_summary"]["coverage"], "partial")

    def test_retrieval_timestamp_format_is_checked_without_asserting_actual_read(self):
        for timestamp in ("yesterday", "2026-10-22", "2026-10-22T12:00:00"):
            value = result()
            value["sources"][0]["retrieved_at"] = timestamp
            with self.subTest(timestamp=timestamp):
                self.assertEqual(normalize_worker_result(value)["evidence_summary"]["coverage"], "partial")

    def test_scoped_source_ids_cannot_collide_on_separator_characters(self):
        value = result()
        value["sources"][0]["id"] = "b:doc"
        value["claims"][0]["source_ids"] = ["b:doc"]
        registry = aggregate_research_results({"a:b": {"result": result()}, "a": {"result": value}})
        self.assertEqual(len({s["id"] for s in registry["sources"]}), 2)


if __name__ == "__main__":
    unittest.main()
