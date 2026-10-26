"""Targeted tests for RunCheckpoint deep module."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from failure_store import FailureStore
from mimir_config import ConfigurationRequired
from run_checkpoint import RunCheckpoint
from task_graph import TaskGraph, TaskNode, TaskStatus


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _valid_task_result(answer: str, raw: str = "raw evidence") -> dict:
    payload = {
        "answer": answer,
        "sources": [{"id": "s1", "locator": "test.txt", "retrieval_type": "local_file", "support_excerpt": "excerpt"}],
        "claims": [{"text": answer, "source_ids": ["s1"], "support_status": "supported", "rationale": "Direct evidence"}],
        "gaps": [],
    }
    content = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return {
        "result": payload,
        "raw_response": raw,
        "result_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "evidence_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "input_fingerprint": hashlib.sha256(b"fingerprint").hexdigest(),
    }


class RunCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state_file = self.root / "state.json"
        self.report_file = self.root / "report.md"

    def tearDown(self):
        self.tmp.cleanup()

    def test_exclusive_lock_creates_and_releases_lock_file(self):
        with RunCheckpoint.lock(str(self.state_file)):
            lock_path = self.state_file.with_name(self.state_file.name + ".lock")
            self.assertTrue(lock_path.exists())
            # Concurrent acquisition on same file fails closed
            from run_locks import RunBusyError
            with self.assertRaises(RunBusyError):
                with RunCheckpoint.lock(str(self.state_file)):
                    pass

    def test_atomic_write_artifact_creates_parent_and_cleans_temporary_files(self):
        nested = self.root / "sub" / "artifact.txt"
        RunCheckpoint.write_artifact(nested, "content test")
        self.assertEqual(nested.read_text(encoding="utf-8"), "content test")
        self.assertEqual(list(nested.parent.glob("*.tmp")), [])

    def test_save_strips_transient_in_memory_keys(self):
        graph = TaskGraph("Test Graph")
        graph.add_node(TaskNode("t1", "Analyst", "Title", "Prompt", status=TaskStatus.COMPLETED))
        state = {
            "version": 1,
            "goal": "Goal",
            "phase": "planned",
            "graph": graph.to_dict(),
            "task_graph_obj": graph,
            "blackboard": MagicMock(),
        }
        RunCheckpoint.save(state, str(self.state_file))
        saved = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertNotIn("task_graph_obj", saved)
        self.assertNotIn("blackboard", saved)
        self.assertEqual(saved["goal"], "Goal")

    def test_validate_output_paths_rejects_collisions(self):
        # Report is identical to state_file
        with self.assertRaisesRegex(ValueError, "Report, JSON sidecar and state paths must be distinct"):
            RunCheckpoint.validate_output_paths(str(self.state_file), str(self.state_file))

        # Report JSON sidecar collides with state_file
        with self.assertRaisesRegex(ValueError, "Report, JSON sidecar and state paths must be distinct"):
            RunCheckpoint.validate_output_paths(str(self.state_file), str(self.state_file.with_suffix("")))

    def test_recover_published_artifacts_recovers_when_hashes_match(self):
        out_path = self.report_file
        json_path = out_path.with_suffix(".json")
        out_path.write_text("# Report", encoding="utf-8")
        json_path.write_text('{"ok": true}', encoding="utf-8")

        state = {
            "version": 1,
            "goal": "Goal",
            "phase": "synthesized",
            "total_elapsed_seconds": 12.5,
            "completed_data": {"t1": {"role": "Agent", "title": "Task"}},
            "publication": {
                "report_path": str(out_path.resolve()),
                "report_hash": _sha256("# Report"),
                "sidecar_hash": _sha256('{"ok": true}'),
            },
        }

        ui = MagicMock()
        recovered = RunCheckpoint.recover_published_artifacts(state, str(out_path), 12.5, ui=ui)
        self.assertIsNotNone(recovered)
        ui.emit.assert_called_once_with(
            "publication_recovered",
            report_path=str(out_path.resolve()),
            json_path=str(json_path.resolve()),
            task_count=1,
            duration_seconds=12.5,
            recovered=True,
        )

    def test_recover_published_artifacts_rejects_tampered_artifact(self):
        out_path = self.report_file
        json_path = out_path.with_suffix(".json")
        out_path.write_text("# Tampered", encoding="utf-8")
        json_path.write_text('{"ok": true}', encoding="utf-8")

        state = {
            "version": 1,
            "goal": "Goal",
            "phase": "synthesized",
            "publication": {
                "report_path": str(out_path.resolve()),
                "report_hash": _sha256("# Original"),
                "sidecar_hash": _sha256('{"ok": true}'),
            },
        }

        with self.assertRaisesRegex(ConfigurationRequired, "Published artifact identity changed"):
            RunCheckpoint.recover_published_artifacts(state, str(out_path), 5.0)

    def test_publish_artifacts_writes_both_files_and_records_quarantine_in_failure_store(self):
        graph = TaskGraph("Goal")
        graph.add_node(TaskNode("t1", "Analyst", "Task 1", "p1", status=TaskStatus.COMPLETED))
        task_res = _valid_task_result("Finding 1")

        fstore_path = self.root / "failures.jsonl"
        state = {
            "version": 1,
            "goal": "Goal of review",
            "phase": "executed",
            "mode": "review",
            "completed_data": {"t1": {"role": "Domain-Analyst", "title": "Inspect code", "result": task_res["result"]}},
            "publication_view": {
                "t1": {"status": "quarantined", "reason": "Unsupported claim in task 1", "sources": [], "gaps": []}
            },
            "failure_store_path": str(fstore_path),
            "memory_mode": "off",
        }

        memory = MagicMock()
        memory.memory_path = self.root / "LEARNINGS.md"
        memory.candidate_path = self.root / "candidates.jsonl"

        swarm = MagicMock()
        swarm.usage_calls = [{"phase": "synthesis", "tokens_used": 150, "usage_details": {"input_tokens": 100, "output_tokens": 50}}]
        swarm.budget_status = {"spent": 0.01}

        out_path, json_path, hardened_str, memory_saved = RunCheckpoint.publish_artifacts(
            state,
            final_out_path=str(self.report_file),
            hardened_solution="Hardened Executive Summary",
            reflection="Reflective assembly notes",
            published_data={},
            combined_critique="",
            red_team_critiques=[],
            memory=memory,
            swarm=swarm,
            backend_display="MockSwarm",
            active_backend="mock",
            active_model="mock-model",
            active_effort="low",
            total_elapsed=4.2,
            synthesis_started_at=100.0,
            is_en=True,
            state_file=str(self.state_file),
            ui=MagicMock(),
        )

        self.assertTrue(out_path.exists())
        self.assertTrue(json_path.exists())
        self.assertEqual(state["phase"], "synthesized")
        self.assertIn("report_hash", state["publication"])
        self.assertIn("sidecar_hash", state["publication"])

        # Quarantine notice present in Markdown report
        report_text = out_path.read_text(encoding="utf-8")
        self.assertIn("Publication: **quarantined**", report_text)
        self.assertIn("Unsupported claim in task 1", report_text)

        # Quarantined finding ingested into FailureStore
        self.assertTrue(fstore_path.exists())
        fstore = FailureStore(str(fstore_path))
        packets = fstore.list_packets()
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].task_id, "t1")
        self.assertEqual(packets[0].failure_kind, "result_check_failure")


if __name__ == "__main__":
    unittest.main()
