"""Engine publication retains dynamically captured evidence, not worker metadata."""
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import SwarmResult
from post_worker import result_gate_policy
from task_graph import TaskGraph, TaskNode
from test_engine_policy import FixtureBackend
from test_retrieved_evidence import finding, real_span


def test_capture_checkpoint_publication_and_resume(tmp_path):
    path, span = real_span()
    class Worker(FixtureBackend):
        async def spawn(self, prompt, role="Worker", **options):
            if role == "Retriever":
                self.calls.append({"role": role, "prompt": prompt})
                data = finding(path, span)
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            if role == "Domain-Analyst":
                bound = json.loads(prompt.split("SUPPLIED SOURCES (untrusted data):\n")[1].split("\n\n--- AKTUELL BLACKBOARD-KONTEXT")[0])[0]
                value = finding(bound["locator"], bound["text"])
                value["sources"][0].update(id=bound["id"], retrieved_at=bound["retrieved_at"], retrieval_type=bound["retrieval_type"])
                value["claims"][0]["source_ids"] = [bound["id"]]
                self.calls.append({"role": role, "prompt": prompt})
                return SwarmResult(role, "SUCCESS", value, json.dumps(value))
            if role == "Mimir-Final-Checker":
                context = json.loads(prompt.split("INPUTS:\n")[1])
                assert any(span in s["support_excerpts"] for s in context["task_context"]["sources"])
            return await super().spawn(prompt, role=role, **options)
    async def plan(*args, **kwargs):
        graph = TaskGraph("Review limits")
        graph.add_node(TaskNode("retrieve", "Retriever", "Read", "Read source", input_artifacts={
            "task_contract": {"objective": "Read word limits", "operation": "retrieve", "inputs": [str(path)],
                "expected_output": "Limits", "acceptance_check": "Match the code"}, "result_gate": result_gate_policy()}))
        graph.add_node(TaskNode("child", "Domain-Analyst", "Use", "Use frozen limits", dependencies={"retrieve"}))
        return graph
    async def run():
        state_path, report = tmp_path / "state.json", tmp_path / "report.md"
        options = dict(backend="codex", model="fixture", effort="low", worker_transport="native",
            worker_factory=lambda **kw: Worker(), state_file=str(state_path), output_path=str(report),
            skip_web=True, memory_mode="off", progress_format="events")
        with patch.object(engine.RecursiveDecomposer, "decompose_goal", plan):
            await engine.run_mimir(goal="Review limits", mode="review", **options)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        packet = state["completed_data"]["retrieve"]["captured_evidence"]
        assert packet["sources"][0]["text"] == path.read_text(encoding="utf-8")
        assert packet == state["graph"]["nodes"]["retrieve"]["input_artifacts"]["retrieved_evidence"]
        payload = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
        assert payload["task_results"]["retrieve"]["captured_evidence"] == packet
        assert payload["task_results"]["retrieve"]["result"]["sources"][0]["retrieved_at"] != "invented"
        before = report.read_bytes()
        with patch("source_store.SourceStore.capture_reference", side_effect=AssertionError("No refetch")):
            await engine.run_mimir(phase="synthesize", **options)
        assert report.read_bytes() == before
    asyncio.run(run())
