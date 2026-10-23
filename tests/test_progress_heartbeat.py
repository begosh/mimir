"""Liveness during blocked work, without model calls or external searches."""
import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine as mimir
from backend import ClaudeCodeSwarmBackend
from jarvis_memory import JarvisMemory
from research_scout import IntelligenceBrief
from task_graph import TaskGraph, TaskNode


class ProgressHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_pipe_delivers_waiting_before_process_exit(self):
        script = """
import asyncio
import sys
from contextlib import suppress
from mimir import MimirConsole

async def run():
    ui = MimirConsole(progress_format='jsonl')
    ui.print_phase(2, 'Planning')
    heartbeat = asyncio.create_task(ui.heartbeat(interval_seconds=0.02))
    await asyncio.to_thread(sys.stdin.readline)
    heartbeat.cancel()
    with suppress(asyncio.CancelledError):
        await heartbeat

asyncio.run(run())
"""
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-u", "-c", script,
            cwd=str(Path(mimir.__file__).parent), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            first = json.loads(await asyncio.wait_for(process.stdout.readline(), timeout=10))
            waiting = json.loads(await asyncio.wait_for(process.stdout.readline(), timeout=10))
            self.assertEqual(first["event"], "phase_started")
            self.assertEqual(waiting["event"], "run_waiting")
            self.assertEqual(waiting["phase"], 2)
            self.assertIsNone(process.returncode)
        finally:
            process.stdin.write(b"\n")
            await process.stdin.drain()
            _, errors = await asyncio.wait_for(process.communicate(), timeout=10)
        self.assertEqual(process.returncode, 0, errors.decode("utf-8"))

    async def test_waiting_reports_phase_and_counts_and_stops_on_cancel(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            ui = mimir.MimirConsole(progress_format="jsonl")
            ui.print_phase(3, "Swarm of Runes")
            ui.display_agent_submitted(TaskNode("a", "Analyst", "Inspect", "private prompt"))
            ui.completed_tasks = 1
            task = asyncio.create_task(ui.heartbeat(interval_seconds=0.01))
            await asyncio.sleep(0.035)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            final_output = stream.getvalue()
            await asyncio.sleep(0.025)
            self.assertEqual(stream.getvalue(), final_output)

        events = [json.loads(line) for line in final_output.splitlines()]
        waiting = [event for event in events if event["event"] == "run_waiting"]
        self.assertTrue(waiting)
        self.assertEqual(waiting[0]["phase"], 3)
        self.assertEqual(waiting[0]["submitted_tasks"], 1)
        self.assertEqual(waiting[0]["completed_tasks"], 1)
        self.assertEqual(waiting[0]["failed_tasks"], 0)
        self.assertNotIn("private prompt", final_output)
        self.assertEqual([e["sequence"] for e in events], list(range(1, len(events) + 1)))

    async def test_planning_keeps_streaming_without_search_and_failure_stops_heartbeat(self):
        backend = ClaudeCodeSwarmBackend(claude_path="claude")
        async def check():
            return {"model_configured": True}
        backend.check_cli = check
        search_started = threading.Event()
        release_search = threading.Event()
        async def fail_decompose(*args, **kwargs):
            search_started.set()
            while not release_search.is_set():
                await asyncio.sleep(.01)
            raise RuntimeError("fixture decomposition failed")
        heartbeat = mimir.MimirConsole.heartbeat
        async def fast_heartbeat(ui):
            await heartbeat(ui, interval_seconds=0.01)

        with tempfile.TemporaryDirectory() as directory:
            stream = io.StringIO()
            memory = JarvisMemory(str(Path(directory) / "LEARNINGS.md"))
            with patch.object(mimir, "create_swarm_backend", return_value=backend), \
                 patch.object(mimir, "JarvisMemory", return_value=memory), \
                 patch.object(mimir.ResearchScout, "conduct_deep_scout", side_effect=AssertionError("Planning must not search")), \
                 patch.object(mimir.RecursiveDecomposer, "decompose_goal", fail_decompose), \
                 patch.object(mimir.MimirConsole, "heartbeat", fast_heartbeat), redirect_stdout(stream):
                run = asyncio.create_task(mimir.run_mimir(
                    "Inspect architecture", backend="claude", progress_format="jsonl",
                    phase="plan", state_file=str(Path(directory) / "state.json")))
                try:
                    for _ in range(100):
                        if search_started.is_set() and '"run_waiting"' in stream.getvalue():
                            break
                        await asyncio.sleep(0.01)
                    self.assertTrue(search_started.is_set())
                    self.assertFalse(run.done())
                    events = [json.loads(line) for line in stream.getvalue().splitlines()]
                    waiting = next(e for e in events if e["event"] == "run_waiting")
                    self.assertEqual(waiting["phase"], 2)
                    self.assertNotIn("research_completed", [e["event"] for e in events])
                finally:
                    release_search.set()
                    with self.assertRaisesRegex(RuntimeError, "fixture decomposition failed"):
                        await run
                final_output = stream.getvalue()
                await asyncio.sleep(0.025)
                self.assertEqual(stream.getvalue(), final_output)
            events = [json.loads(line) for line in final_output.splitlines()]
            self.assertEqual(events[-1]["event"], "run_failed")
            self.assertFalse((Path(directory) / "state.json").exists())
            self.assertEqual(memory.get_summary_stats()["entries"], 0)


if __name__ == "__main__":
    unittest.main()
