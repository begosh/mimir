"""Regression tests for phase checkpoints and adversarial failure handling."""
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine as mimir
from backend import BaseSwarmBackend, ClaudeCodeSwarmBackend, SwarmResult
from gepa_optimizer import CandidateProgram, EvaluationSample, GepaOptimizer
from jarvis_memory import JarvisMemory
from task_graph import TaskGraph, TaskNode
from research_program import prepare_research


class ReviewHardeningTests(unittest.IsolatedAsyncioTestCase):
    def test_json_examples_do_not_replace_prose_review(self):
        prose = 'Finding: mutation accepts invalid output.\n```json\n{"mutated_content": {"instruction": "..."}}\n```\nFix: validate the content type.'
        self.assertEqual(BaseSwarmBackend.parse_json_from_text(prose), prose)
        self.assertEqual(BaseSwarmBackend.parse_json_from_text('```json\n{"ok": true}\n```'), {"ok": True})
        self.assertEqual(BaseSwarmBackend.parse_json_from_text('{"ok": true}'), {"ok": True})
    def make_state(self, directory, phase="planned"):
        graph = TaskGraph("Review fixture")
        graph.add_node(TaskNode("a", "Domain-Analyst", "Inspect", "Inspect"))
        graph.add_node(TaskNode("b", "Executive-Synthesizer", "Combine", "Combine", {"a"}))
        state = dict(version=1, phase=phase, goal=graph.goal, graph=graph.to_dict(),
                     backend="claude", model="haiku", effort="low", worker_timeout=27,
                     max_concurrency=2, output_path=str(Path(directory) / "planned.md"),
                     completed_data={})
        if phase == "executed":
            state["completed_data"] = {n.id: dict(role=n.role, title=n.title, result="Finding") for n in graph.nodes.values()}
        target = Path(directory) / "state.json"
        config, _, fingerprint = prepare_research("native", None, None, None, {}, Path(directory))
        state.update(research_program="native", research_config=config, research_identity=fingerprint)
        target.with_suffix(".operations.jsonl").write_text(json.dumps({
            "kind": "budget_started", "time": time.time(), "budget": config["budget"],
            "publication_reserve": 2}) + "\n", encoding="utf-8")
        mimir._save_state(state, str(target))
        return state, target

    async def test_legacy_budgetless_resume_is_rejected_before_native_setup(self):
        from mimir_config import ConfigurationRequired
        with tempfile.TemporaryDirectory() as directory:
            state, target = self.make_state(directory)
            state["research_config"]["budget"] = None
            mimir._save_state(state, str(target))
            with patch.object(mimir, "create_swarm_backend") as factory, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ConfigurationRequired, "Legacy run has no durable budget"):
                    await mimir.run_mimir(phase="execute", state_file=str(target), progress_format="jsonl")
            factory.assert_not_called()

    async def test_resume_uses_state_settings_without_profile_and_preserves_output(self):
        backend = ClaudeCodeSwarmBackend(claude_path="claude")
        async def check():
            return {}
        async def spawn(prompt, role="Worker", **kwargs):
            return SwarmResult(role, "SUCCESS", "Finding", "Finding")
        backend.check_cli, backend.spawn = check, spawn
        with tempfile.TemporaryDirectory() as directory:
            _, target = self.make_state(directory)
            with patch.dict(os.environ, {}, clear=True), patch.object(mimir, "create_swarm_backend", return_value=backend) as factory, redirect_stdout(io.StringIO()):
                await mimir.run_mimir(phase="execute", state_file=str(target), progress_format="jsonl")
            args = factory.call_args.kwargs
            self.assertEqual((args["backend_type"], args["model"], args["effort"], args["timeout_seconds"], args["max_concurrency"]),
                             ("claude", "haiku", "low", 27, 2))
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["phase"], "executed")
            self.assertEqual(args["worker_transport"], "cli")
            self.assertEqual(saved["worker_transport"], "cli")
            self.assertTrue(all(n["status"] == "COMPLETED" for n in saved["graph"]["nodes"].values()))
            self.assertEqual(saved["output_path"], str(Path(directory) / "planned.md"))

    async def test_partial_synthesis_and_path_collision_fail_before_worker_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            state, target = self.make_state(directory, "executed")
            del state["completed_data"]["a"]
            mimir._save_state(state, str(target))
            with patch.object(mimir, "create_swarm_backend") as factory, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "every planned task"):
                    await mimir.run_mimir(phase="synthesize", state_file=str(target), progress_format="jsonl")
                factory.assert_not_called()
            with patch.dict(os.environ, {}, clear=True), patch.object(mimir, "create_swarm_backend") as factory, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "paths must be distinct"):
                    await mimir.run_mimir("Review", backend="claude", output_path=str(Path(directory) / "report.json"),
                                          state_file=str(target), progress_format="jsonl")
                factory.assert_not_called()
            with patch.dict(os.environ, {}, clear=True), patch.object(mimir, "create_swarm_backend") as factory, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "paths must be distinct"):
                    await mimir.run_mimir("Review", backend="claude", output_path=str(target)+".lock",
                                          state_file=str(target), progress_format="jsonl")
                factory.assert_not_called()

    def test_checkpoint_write_failure_keeps_previous_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state, target = self.make_state(directory)
            before = target.read_bytes()
            state["invalid_number"] = float("nan")
            with self.assertRaises(ValueError):
                mimir._save_state(state, str(target))
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(list(target.parent.glob("*.tmp")), [])

    async def test_concurrent_phase_rejected_without_removing_owned_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            _, target = self.make_state(directory)
            with mimir._checkpoint_lock(str(target)):
                with patch.object(mimir, "create_swarm_backend") as factory, redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, "already in use"):
                        await mimir.run_mimir(phase="execute", state_file=str(target), progress_format="jsonl")
                    factory.assert_not_called()
                self.assertTrue(target.with_name("state.json.lock").exists())
            # Lock file remains, but the OS lease is released.
            with mimir._checkpoint_lock(str(target)):
                pass

    async def test_heartbeat_error_still_releases_backend_and_checkpoint(self):
        backend = ClaudeCodeSwarmBackend(claude_path="claude")
        cleaned = []
        async def check():
            import asyncio
            await asyncio.sleep(.01)
            raise RuntimeError("fixture check failed")
        async def heartbeat(ui):
            raise RuntimeError("fixture heartbeat failed")
        backend.check_cli = check
        backend.cleanup = lambda: cleaned.append(True)
        with tempfile.TemporaryDirectory() as directory:
            _, target = self.make_state(directory)
            with patch.dict(os.environ, {}, clear=True), patch.object(mimir, "create_swarm_backend", return_value=backend), patch.object(mimir.MimirConsole, "heartbeat", heartbeat), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "heartbeat failed"):
                    await mimir.run_mimir(phase="execute", state_file=str(target), progress_format="jsonl")
            self.assertEqual(cleaned, [True])
            # Lock file remains, but the OS lease is released.
            with mimir._checkpoint_lock(str(target)):
                pass

    async def test_full_worker_output_and_critique_survive_report_generation(self):
        backend = ClaudeCodeSwarmBackend(claude_path="claude")
        long_output = "Evidence " * 450 + "LAST REQUIRED SOURCE https://example.org/source"
        async def check():
            return {}
        async def spawn(prompt, role="Worker", **kwargs):
            self.assertIn("LAST REQUIRED SOURCE", prompt)
            return SwarmResult(role, "SUCCESS", {"verdict":"PASS","issues":[]} if role == "Mimir-Final-Checker" else {"answer": "Reviewed findings", "limitations": ["Source retained"]}, "raw")
        backend.check_cli, backend.spawn = check, spawn
        with tempfile.TemporaryDirectory() as directory:
            state, target = self.make_state(directory, "executed")
            state["completed_data"]["b"]["result"] = long_output
            mimir._save_state(state, str(target))
            memory = JarvisMemory(str(Path(directory) / "LEARNINGS.md"))
            with patch.dict(os.environ, {}, clear=True), patch.object(mimir, "create_swarm_backend", return_value=backend), patch.object(mimir, "JarvisMemory", return_value=memory), redirect_stdout(io.StringIO()):
                await mimir.run_mimir(phase="synthesize", state_file=str(target), progress_format="jsonl")
            self.assertIn(long_output, (Path(directory) / "planned.md").read_text(encoding="utf-8"))
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["phase"], "synthesized")

    async def test_reflection_failure_cannot_publish_or_record_learning(self):
        backend = ClaudeCodeSwarmBackend(claude_path="claude")
        async def check():
            return {}
        async def fail(*args, **kwargs):
            return SwarmResult("GEPA-Evolver", "ERROR", None, "Authentication failed")
        backend.check_cli, backend.spawn = check, fail
        with tempfile.TemporaryDirectory() as directory:
            _, target = self.make_state(directory, "executed")
            memory = JarvisMemory(str(Path(directory) / "LEARNINGS.md"))
            before = memory.memory_path.read_bytes()
            stream = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), patch.object(mimir, "create_swarm_backend", return_value=backend), patch.object(mimir, "JarvisMemory", return_value=memory), redirect_stdout(stream):
                with self.assertRaisesRegex(RuntimeError, "synthesis worker failed: authentication failed"):
                    await mimir.run_mimir(phase="synthesize", state_file=str(target), progress_format="jsonl")
            self.assertFalse((Path(directory) / "planned.md").exists())
            self.assertEqual(memory.memory_path.read_bytes(), before)
            self.assertEqual(json.loads(stream.getvalue().splitlines()[-1])["event"], "run_failed")

    async def test_gepa_mutations_keep_the_correct_parent_when_other_candidates_pass(self):
        class Swarm:
            async def parallel(self, tasks):
                return [SwarmResult(t.role, "SUCCESS", {"mutated_content": "fixed failing candidate", "reflection": "Correct parent"}, "raw") for t in tasks]
        candidates = [CandidateProgram("passing", "good", "pass"), CandidateProgram("failing", "bad", "fail")]
        optimizer = GepaOptimizer(Swarm(), max_generations=2, pareto_keys=["accuracy", "speed"])
        def evaluate(candidate, sample):
            return (1.0, {"accuracy": 1.0, "speed": 0.0}, "") if candidate.id == "passing" else (0.5, {"accuracy": 0.5, "speed": 1.0}, "Failure")
        result = await optimizer.optimize(candidates, [EvaluationSample("in", "out")], evaluate)
        self.assertIn("failing_gen1", {c.id for c in result})
        self.assertNotIn("passing_gen1", {c.id for c in result})

    async def test_gepa_mutation_ids_cannot_collide_with_existing_candidates(self):
        class Swarm:
            async def parallel(self, tasks):
                return [SwarmResult(t.role, "SUCCESS", {"mutated_content": "fix", "reflection": "why"}, "raw") for t in tasks]
        candidates = [CandidateProgram("a", "bad", "fixture"), CandidateProgram("a_gen1", "also bad", "fixture")]
        result = await GepaOptimizer(Swarm()).optimize(candidates, [EvaluationSample("in", "out")], lambda *args: (.5, {}, "miss"))
        ids = [candidate.id for candidate in result]
        self.assertEqual(len(ids), len(set(ids)))

    async def test_pareto_selection_retains_full_precision(self):
        candidates = [CandidateProgram("best", "x", "fixture"), CandidateProgram("worse", "x", "fixture")]
        result = await GepaOptimizer(object(), max_generations=1).optimize(
            candidates, [EvaluationSample("in", "out")],
            lambda c, s: (.9004 if c.id == "best" else .9001, {}, "miss"))
        self.assertEqual([c.id for c in result], ["best"])

    async def test_empty_structured_reflection_is_rejected(self):
        class Swarm:
            async def spawn(self, **kwargs):
                return SwarmResult("GEPA", "SUCCESS", {"hardened_solution": "", "reflection": "Done"}, "raw")
        with self.assertRaisesRegex(ValueError, "no valid solution"):
            await GepaOptimizer(Swarm()).reflective_evolve("draft", "goal", "critique")

    async def test_gepa_rejects_missing_or_nonfinite_evaluation(self):
        optimizer = GepaOptimizer(object(), pareto_keys=["speed"])
        candidate = CandidateProgram("a", "candidate", "fixture")
        sample = EvaluationSample("in", "out")
        with self.assertRaisesRegex(ValueError, "nonempty evaluation"):
            await optimizer.optimize([candidate], [], lambda *args: (1.0, {}, ""))
        with self.assertRaisesRegex(ValueError, "all configured Pareto"):
            await optimizer.optimize([candidate], [sample], lambda *args: (1.0, {}, ""))
        with self.assertRaisesRegex(ValueError, "finite"):
            await optimizer.optimize([candidate], [sample], lambda *args: (float("nan"), {"speed": 1}, ""))
        with self.assertRaisesRegex(ValueError, "cannot be overridden"):
            await optimizer.optimize([candidate], [sample], lambda *args: (1.0, {"primary_accuracy": -100, "speed": 1}, ""))
