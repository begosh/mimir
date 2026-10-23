"""Unit tests for Mímir discrete phased execution (--phase plan|execute|synthesize)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine as mimir
from backend import ClaudeCodeSwarmBackend, SwarmResult
from jarvis_memory import JarvisMemory
from task_graph import TaskGraph, TaskNode


class PhasedExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_phase_discrete_pipeline(self):
        backend = ClaudeCodeSwarmBackend(claude_path="claude", default_effort="low")
        graph = TaskGraph("Test phased execution")
        graph.add_node(TaskNode("t1", "Domain-Analyst", "Analyze", "Prompt 1"))
        graph.add_node(TaskNode("t2", "Executive-Synthesizer", "Synthesize", "Prompt 2", dependencies={"t1"}))

        async def fake_check():
            return {"model_configured": True}

        async def fake_decompose(*args, **kwargs):
            return graph

        async def fake_spawn(prompt, role="Micro-Worker", *args, **kwargs):
            if role == "Mimir-Final-Checker":
                return SwarmResult(role, "SUCCESS", {"verdict":"PASS","issues":[]}, "raw")
            if role == "Mimir-Synthesizer":
                return SwarmResult(role, "SUCCESS", {"answer": "Phased hardened solution", "limitations": []}, "raw")
            return SwarmResult(role, "SUCCESS", f"Result from {role}", f"Raw from {role}", duration_seconds=0.1)

        backend.check_cli = fake_check
        backend.spawn = fake_spawn

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            report_file = Path(tmpdir) / "report.md"
            memory = JarvisMemory(str(Path(tmpdir) / "LEARNINGS.md"))

            with patch.object(mimir, "create_swarm_backend", return_value=backend), \
                 patch.object(mimir, "JarvisMemory", return_value=memory), \
                 patch.object(mimir.RecursiveDecomposer, "decompose_goal", fake_decompose):

                # 1. Phase: plan
                await mimir.run_mimir(
                    goal="Test phased execution",
                    backend="claude",
                    skip_web=True,
                    enable_jev=False,
                    phase="plan",
                    state_file=str(state_file),
                    progress_format="jsonl"
                )
                self.assertTrue(state_file.exists())
                state1 = json.loads(state_file.read_text(encoding="utf-8"))
                self.assertEqual(state1["phase"], "planned")
                self.assertEqual(len(state1["tasks"]), 2)

                # 2. Phase: execute
                await mimir.run_mimir(
                    backend="claude",
                    phase="execute",
                    state_file=str(state_file),
                    progress_format="jsonl"
                )
                state2 = json.loads(state_file.read_text(encoding="utf-8"))
                self.assertEqual(state2["phase"], "executed")
                self.assertEqual(len(state2["completed_data"]), 2)

                # 3. Phase: synthesize
                await mimir.run_mimir(
                    backend="claude",
                    output_path=str(report_file),
                    phase="synthesize",
                    state_file=str(state_file),
                    progress_format="jsonl"
                )
                self.assertTrue(report_file.exists())
                self.assertTrue(report_file.with_suffix(".json").exists())
                report_text = report_file.read_text(encoding="utf-8")
                self.assertIn("Phased hardened solution", report_text)


if __name__ == "__main__":
    unittest.main()
