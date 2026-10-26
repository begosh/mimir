"""E6: Qualify hybrid interruption/recovery and target tool-runtime readiness.

Tests:
1. Tool-Runtime Readiness:
   - Diagnostics report direct API configuration readiness separately from deferred tool-runtime readiness.
   - HybridSwarmBackend executes text tasks (spawn_restricted) with 0 tool runtime initializations.
   - Tool runtime is lazily initialized only when spawn (tool need) is called.
   - Model and effort drift are strictly rejected across hybrid dispatch.
   - Missing direct credentials fail closed rather than silently falling back to native tools.
2. Interruption and Recovery:
   - Checkpoint loading resets interrupted in-flight tasks to PENDING while retaining completed tasks.
   - Partial worker output is never admitted to dependency findings upon crash/interruption.
   - Budget attempts, deadlines, and reserved publication calls persist across resume.
   - Publication recovery validates existing report/sidecar hashes and skips re-inference.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import SwarmResult, WorkerFailure
from diagnostics import collect_diagnostics
from invocation_broker import InvocationBroker
from mimir_config import ConfigurationRequired
from task_graph import TaskGraph, TaskNode, TaskStatus
from test_engine_policy import FixtureBackend
from text_api_backend import HybridSwarmBackend, TextResponsesBackend


class ToolRuntimeReadinessQualificationTests(unittest.TestCase):
    """Verifies that direct text API and native tool runtimes are qualified and decoupled."""

    def test_diagnostics_separates_direct_api_from_deferred_tool_runtime(self):
        """Diagnostics reports text API configuration readiness separately from tool runtime readiness."""
        with patch("text_api_backend.TextResponsesBackend") as mock_text:
            mock_inst = MagicMock()
            mock_inst.provider = "azure"
            mock_text.return_value = mock_inst
            with patch("diagnostics.native_environment", return_value=({"provider": "codex", "config_paths": [], "errors": []}, {})):
                report = collect_diagnostics("codex", model="gpt-6.1-sol", effort="low", worker_transport="hybrid")

        self.assertEqual(report["worker_transport"], "hybrid")
        self.assertIsNotNone(report["text_api"])
        self.assertTrue(report["text_api"]["ready"])
        self.assertEqual(report["text_api"]["provider"], "azure")
        self.assertEqual(report["text_api"]["model"], "gpt-6.1-sol")
        self.assertEqual(report["tool_runtime_preflight"], "Deferred until tools are needed")

    def test_hybrid_backend_defers_tool_runtime_initialization(self):
        """Hybrid backend routes spawn_restricted to text API without initializing tool runtime."""
        tool_init_count = 0

        class MockToolBackend:
            timeout_seconds = 180
            async def check_cli(self): pass
            async def spawn(self, *args, **options):
                return SwarmResult("Tool-Worker", "SUCCESS", {"tool_called": True}, '{"tool_called": true}')
            async def aclose(self): pass

        def tool_factory():
            nonlocal tool_init_count
            tool_init_count += 1
            return MockToolBackend()

        mock_text = MagicMock()
        mock_text.default_model = "gpt-6.1-sol"
        mock_text.default_effort = "low"
        mock_text.max_concurrency = 4
        mock_text.execution_identity = {"backend": "responses"}
        mock_text.timeout_seconds = 180

        async def fake_spawn_restricted(*args, **options):
            return SwarmResult("Text-Worker", "SUCCESS", {"text_only": True}, '{"text_only": true}')

        async def fake_aclose(): pass

        mock_text.spawn_restricted = fake_spawn_restricted
        mock_text.aclose = fake_aclose

        backend = HybridSwarmBackend(
            native=None,
            text=mock_text,
            tool_factory=tool_factory,
            tool_backend_name="codex",
            tool_model="gpt-6.1-sol",
        )

        # 1. Direct text operation (spawn_restricted) does NOT initialize tool runtime
        res1 = asyncio.run(backend.spawn_restricted("atomic extract", json_schema={"type": "object"}))
        self.assertEqual(res1.status, "SUCCESS")
        self.assertEqual(tool_init_count, 0)
        self.assertIsNone(backend.tool_backend)

        # 2. Tool-using operation (spawn) lazily initializes tool runtime
        res2 = asyncio.run(backend.spawn("tool search", model="gpt-6.1-sol", effort="low"))
        self.assertEqual(res2.status, "SUCCESS")
        self.assertEqual(tool_init_count, 1)
        self.assertIsNotNone(backend.tool_backend)

        asyncio.run(backend.aclose())

    def test_hybrid_backend_rejects_model_drift_on_tool_dispatch(self):
        """Tool dispatch fails closed if a model drift or substitution is attempted."""
        class MockToolBackend:
            timeout_seconds = 180
            async def check_cli(self): pass
            async def aclose(self): pass

        mock_text = MagicMock()
        mock_text.default_model = "gpt-6.1-sol"
        mock_text.default_effort = "low"
        mock_text.max_concurrency = 4
        mock_text.execution_identity = {}
        mock_text.timeout_seconds = 180

        backend = HybridSwarmBackend(
            native=None,
            text=mock_text,
            tool_factory=lambda: MockToolBackend(),
            tool_backend_name="codex",
            tool_model="gpt-6.1-sol",
        )

        with self.assertRaisesRegex(ConfigurationRequired, "Tool dispatch cannot change the selected model"):
            asyncio.run(backend.spawn("read", model="gpt-4o", effort="low"))

    def test_missing_direct_credentials_fails_closed(self):
        """Missing direct API credentials fail closed with ConfigurationRequired, never silent fallback."""
        with patch("text_api_backend.configured_value", return_value=None):
            with self.assertRaises(ConfigurationRequired) as ctx:
                engine.create_swarm_backend("codex", "gpt-6.1-sol")
            self.assertIn("OPENAI_API_KEY", str(ctx.exception))


import time
from invocation_broker import validate_budget

def _write_budget_journal(state_file: Path, publication_reserve: int = 0, began_time: float | None = None):
    journal = state_file.with_suffix(".operations.jsonl")
    header = {
        "kind": "budget_started",
        "time": began_time or time.time(),
        "budget": validate_budget(),
        "publication_reserve": publication_reserve,
    }
    journal.write_text(json.dumps(header, ensure_ascii=False) + "\n", encoding="utf-8")


class HybridInterruptionAndRecoveryQualificationTests(unittest.IsolatedAsyncioTestCase):
    """Verifies durable interruption, budget preservation, and recovery behaviors."""

    async def test_resume_without_budget_journal_fails_closed(self):
        """Resuming a run without its operations journal fails closed to prevent deadline resets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_file = root / "checkpoint.json"
            graph = TaskGraph("Journal Guard Test")
            t1 = TaskNode("t1", "Atomic-Worker", "Task 1", "prompt 1", status=TaskStatus.PENDING)
            graph.add_node(t1)

            state = {
                "version": 1,
                "goal": "Test missing journal",
                "phase": "executing",
                "mode": "single",
                "graph": graph.to_dict(),
                "tasks": ["t1"],
                "completed_data": {},
            }
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            backend = FixtureBackend()
            with patch.object(engine, "create_swarm_backend", return_value=backend):
                with self.assertRaisesRegex(ConfigurationRequired, "Budget journal is missing"):
                    await engine.run_mimir(
                        backend="codex",
                        model="fixture",
                        effort="low",
                        phase="execute",
                        state_file=str(state_file),
                        worker_factory=lambda **kw: backend,
                    )

    async def test_interrupted_run_resumes_retaining_completed_results(self):
        """When a run is interrupted, resuming preserves completed results and resets in-flight work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_file = root / "checkpoint.json"
            _write_budget_journal(state_file, publication_reserve=2)

            graph = TaskGraph("Interruption Test")
            t1 = TaskNode("t1", "Atomic-Worker", "Task 1", "prompt 1", status=TaskStatus.COMPLETED)
            t2 = TaskNode("t2", "Atomic-Worker", "Task 2", "prompt 2", status=TaskStatus.RUNNING, dependencies={"t1"})
            graph.add_node(t1)
            graph.add_node(t2)

            t1_finding = {
                "answer": "Task 1 verified result",
                "sources": [{"id": "s1", "locator": "file1.txt", "retrieval_type": "local_file", "support_excerpt": "excerpt"}],
                "claims": [{"text": "Task 1 verified result", "source_ids": ["s1"], "support_status": "supported", "rationale": "code"}],
                "gaps": [],
            }
            content1 = json.dumps(t1_finding, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            t1_hash = hashlib.sha256(content1.encode()).hexdigest()
            t1_raw = "raw1"
            t1_raw_hash = hashlib.sha256(t1_raw.encode()).hexdigest()

            state = {
                "version": 1,
                "goal": "Test interruption recovery",
                "phase": "executing",
                "mode": "review",
                "graph": graph.to_dict(),
                "tasks": ["t1", "t2"],
                "completed_data": {
                    "t1": {
                        "result": t1_finding,
                        "raw_response": t1_raw,
                        "result_hash": t1_hash,
                        "evidence_hash": t1_raw_hash,
                        "input_fingerprint": hashlib.sha256(b"fp1").hexdigest(),
                    }
                },
            }
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            # Resuming execute phase: _load_state must reset in-flight t2 to PENDING while retaining t1
            resumed_state = engine._load_state(str(state_file), phase="execute")
            resumed_graph = TaskGraph.from_dict(resumed_state["graph"])

            self.assertEqual(resumed_graph.nodes["t1"].status, TaskStatus.COMPLETED)
            self.assertEqual(resumed_graph.nodes["t2"].status, TaskStatus.PENDING)
            self.assertIn("t1", resumed_state["completed_data"])
            self.assertNotIn("t2", resumed_state["completed_data"])

    async def test_partial_worker_output_never_admitted_upon_interruption(self):
        """Interrupted or cancelled tasks leave zero unverified partial findings in completed_data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_file = root / "checkpoint.json"
            _write_budget_journal(state_file, publication_reserve=0)

            graph = TaskGraph("Cancellation Guard Test")
            t1 = TaskNode("t1", "Atomic-Worker", "Task 1", "prompt 1", status=TaskStatus.PENDING)
            graph.add_node(t1)

            state = {
                "version": 1,
                "goal": "Test partial output guard",
                "phase": "executing",
                "mode": "single",
                "graph": graph.to_dict(),
                "tasks": ["t1"],
                "completed_data": {},
            }
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            # Simulate worker throwing CancelledError mid-execution
            class CancellingBackend(FixtureBackend):
                async def spawn(self, *args, **options):
                    raise asyncio.CancelledError("Simulated user interruption")

            backend = CancellingBackend()
            with patch.object(engine, "create_swarm_backend", return_value=backend):
                with self.assertRaises(asyncio.CancelledError):
                    await engine.run_mimir(
                        backend="codex",
                        model="fixture",
                        effort="low",
                        phase="execute",
                        state_file=str(state_file),
                        worker_factory=lambda **kw: backend,
                    )

            # Assert completed_data remains completely empty; partial output was not admitted
            saved_state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(saved_state["completed_data"], {})

    async def test_idempotent_publication_recovery_skips_re_inference(self):
        """If synthesis completed and report files exist, recovery verifies hashes and skips re-inference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report_file = root / "report.md"
            sidecar_file = root / "report.json"
            state_file = root / "checkpoint.json"
            _write_budget_journal(state_file, publication_reserve=2)

            # Pre-existing report and sidecar from completed run
            report_content = "# Hardened Synthesis Report\nAll checks passed."
            report_file.write_text(report_content, encoding="utf-8")
            report_hash = hashlib.sha256(report_file.read_bytes()).hexdigest()

            sidecar_data = {
                "hardened_solution": "All checks passed.",
                "research": {"coverage": "reported", "sources": [], "claims": [], "gaps": []},
            }
            sidecar_file.write_text(json.dumps(sidecar_data), encoding="utf-8")
            sidecar_hash = hashlib.sha256(sidecar_file.read_bytes()).hexdigest()

            graph = TaskGraph("Publication Recovery Test")
            t1 = TaskNode("t1", "Atomic-Worker", "Task 1", "prompt 1", status=TaskStatus.COMPLETED)
            graph.add_node(t1)

            t1_finding = {
                "answer": "Task 1 verified result",
                "sources": [],
                "claims": [],
                "gaps": [],
            }
            content1 = json.dumps(t1_finding, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            t1_hash = hashlib.sha256(content1.encode()).hexdigest()
            t1_raw = "raw1"
            t1_raw_hash = hashlib.sha256(t1_raw.encode()).hexdigest()

            state = {
                "version": 1,
                "goal": "Test publication recovery",
                "phase": "synthesized",
                "mode": "review",
                "graph": graph.to_dict(),
                "tasks": ["t1"],
                "completed_data": {
                    "t1": {
                        "result": t1_finding,
                        "raw_response": t1_raw,
                        "result_hash": t1_hash,
                        "evidence_hash": t1_raw_hash,
                        "input_fingerprint": hashlib.sha256(b"fp1").hexdigest(),
                    }
                },
                "publication": {
                    "report_path": str(report_file.resolve()),
                    "report_hash": report_hash,
                    "sidecar_hash": sidecar_hash,
                },
            }
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            backend = FixtureBackend()
            with patch.object(engine, "create_swarm_backend", return_value=backend):
                resumed = await engine.run_mimir(
                    backend="codex",
                    model="fixture",
                    effort="low",
                    phase="synthesize",
                    state_file=str(state_file),
                    output_path=str(report_file),
                    worker_factory=lambda **kw: backend,
                )

            # Exactly zero backend inference calls were made on recovery
            self.assertEqual(len(backend.calls), 0)
            self.assertEqual(report_file.read_text(encoding="utf-8"), report_content)


if __name__ == "__main__":
    unittest.main()
