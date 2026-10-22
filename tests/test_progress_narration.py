"""Narration through the public run interface without model calls."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_manager import RunManager


class NarratedProgress(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.sink = None

        async def runner(**options):
            self.sink = options["event_sink"]
            self.sink({"event": "task_submitted", "sequence": 1,
                       "node_id": "evidence", "title": "private goal"})
            self.started.set()
            await self.release.wait()
            self.sink({"event": "plan_completed", "sequence": 4})

        self.manager = RunManager(Path(self.temp.name), runner=runner)
        self.run = (await self.manager.start(goal="private"))["run_id"]
        await self.started.wait()

    async def asyncTearDown(self):
        await self.manager.aclose()
        self.temp.cleanup()

    async def test_compact_view_keeps_raw_output_private_and_events_opt_in(self):
        view = await self.manager.progress(self.run, wait_seconds=0)
        self.assertTrue(view["updates"])
        self.assertNotIn("events", view)
        self.assertNotIn("latest_event", view)
        self.assertNotIn("private goal", json.dumps(view))
        self.assertEqual(view["next_sequence"], 1)
        detailed = await self.manager.progress(self.run, wait_seconds=0, include_events=True)
        self.assertEqual(detailed["events"][0]["title"], "private goal")
        self.assertEqual(view["updates"], detailed["updates"])

    async def test_heartbeats_do_not_wake_wait_and_cursor_still_advances(self):
        waiting = asyncio.create_task(self.manager.progress(self.run, 1, wait_seconds=0.12))
        await asyncio.sleep(0.01)
        self.sink({"event": "run_waiting", "sequence": 2,
                   "completed_tasks": 0, "submitted_tasks": 1})
        await asyncio.sleep(0.03)
        self.assertFalse(waiting.done())
        view = await asyncio.wait_for(waiting, 1)
        self.assertEqual(view["updates"], [])
        self.assertEqual(view["next_sequence"], 2)
        self.assertEqual(view["status"], "running")

    async def test_returned_worker_findings_wake_wait_without_leaking_excerpt(self):
        waiting = asyncio.create_task(self.manager.progress(self.run, 1, wait_seconds=5))
        await asyncio.sleep(0.01)
        self.sink({"event": "task_completed", "sequence": 2,
                   "node_id": "evidence", "output_excerpt": "untrusted SECRET"})
        view = await asyncio.wait_for(waiting, 1)
        self.assertEqual(view["updates"][0]["sequence"], 2)
        self.assertNotIn("SECRET", json.dumps(view))
        self.assertEqual(view["status"], "running")

    async def test_artifact_readiness_does_not_claim_completed_cleanup(self):
        self.sink({"event": "artifacts_ready", "sequence": 2})
        view = await self.manager.progress(self.run, 1, wait_seconds=0)
        self.assertEqual(view["status"], "running")
        self.assertTrue(view["updates"])
        self.assertEqual(view["completed_phase"], None)

    async def test_completion_wakes_wait_and_narrates_current_phase(self):
        waiting = asyncio.create_task(self.manager.progress(self.run, 1, wait_seconds=5))
        await asyncio.sleep(0.01)
        self.release.set()
        view = await asyncio.wait_for(waiting, 1)
        self.assertEqual(view["status"], "completed")
        self.assertEqual(view["completed_phase"], "plan")
        self.assertEqual(view["next_sequence"], 2)
        self.assertTrue(view["narration"])

    async def test_paging_keeps_meaningful_changes_and_status_reads_do_not_write(self):
        self.sink({"event": "task_submitted", "sequence": 2, "node_id": "alternatives"})
        self.sink({"event": "task_submitted", "sequence": 3, "node_id": "critique"})
        root = self.manager.root / self.run
        before = {name: (root / name).read_bytes() for name in ("run.json", "events.jsonl")}
        first = await self.manager.progress(self.run, limit=1, wait_seconds=0)
        second = await self.manager.progress(self.run, first["next_sequence"], limit=1, wait_seconds=0)
        third = await self.manager.progress(self.run, second["next_sequence"], limit=1, wait_seconds=0)
        self.assertTrue(first["has_more"])
        self.assertTrue(second["has_more"])
        self.assertFalse(third["has_more"])
        self.assertEqual([v["updates"][0]["sequence"] for v in [first, second, third]], [1, 2, 3])
        self.assertEqual(before, {name: (root / name).read_bytes() for name in before})

    async def test_invalid_wait_is_rejected(self):
        for value in [True, -1, 26, float("nan"), float("inf"), "20"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.manager.progress(self.run, wait_seconds=value)


if __name__ == "__main__":
    unittest.main()
