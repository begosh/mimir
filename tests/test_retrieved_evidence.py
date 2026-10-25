"""Dynamic capture uses engine reads, frozen spans and admission before release."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import SwarmResult
from post_worker import result_gate_policy
from retrieved_evidence import capture_result_evidence, validate_capture_packet
from scheduler import execute_graph, validate_retained
from source_store import SourceStore, identity
from task_graph import TaskGraph, TaskNode, TaskStatus


def finding(locator, excerpt):
    return {"answer": "Critic 180; specialists 250.", "sources": [{"id": "worker_id", "locator": str(locator),
        "retrieval_type": "local_file", "retrieved_at": "invented", "support_excerpt": excerpt}],
        "claims": [{"text": "Critic 180; specialists 250.", "source_ids": ["worker_id"],
                    "support_status": "supported", "rationale": "Conditional expression"}], "gaps": []}


def real_span():
    path = Path(__file__).resolve().parents[1] / "scripts" / "task_graph.py"
    text = path.read_text(encoding="utf-8")
    return path, next(line for line in text.splitlines() if '(180 if t["id"] == "critique" else 250)' in line)


def test_engine_identity_exact_spans_and_frozen_reuse(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("unrelated\nCritic 180; specialists 250.\ntrailing", encoding="utf-8")
    result, sources, spans = capture_result_evidence(finding(path, "Critic 180; specialists 250."), workspace=tmp_path)
    sid = sources[0]["id"]
    assert sid.startswith("capture_") and sid != "worker_id"
    assert result["sources"][0]["retrieved_at"] != "invented"
    assert result["claims"][0]["source_ids"] == [sid]
    assert spans[0]["text"] == sources[0]["text"][spans[0]["start"]:spans[0]["end"]]
    path.write_text("Changed live page", encoding="utf-8")
    with patch.object(SourceStore, "capture_reference", side_effect=AssertionError("No refetch")):
        _, reused, _ = capture_result_evidence(finding(path, spans[0]["text"]), workspace=tmp_path, frozen=sources)
    assert reused == sources


def test_missing_and_ambiguous_excerpts_do_not_create_captures(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("same same", encoding="utf-8")
    for excerpt in ("invented", "same", ""):
        with pytest.raises(ValueError):
            capture_result_evidence(finding(path, excerpt), workspace=tmp_path)


def test_workspace_and_remote_capture_boundaries(tmp_path):
    with pytest.raises(ValueError, match="outside the workspace"):
        SourceStore.capture_reference(__file__, workspace=tmp_path)
    with patch("urllib.request.build_opener") as network:
        with pytest.raises(ValueError, match="allowlist"):
            SourceStore.capture_reference("https://unapproved.example/page", workspace=tmp_path)
        network.assert_not_called()


def test_approved_https_capture_retains_exact_response_content(tmp_path):
    from email.message import Message
    from io import BytesIO
    response = BytesIO(b"Original page bytes: Port 42")
    response.headers = Message()
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    with patch("urllib.request.build_opener") as opener:
        opener.return_value.open.return_value = response
        captured = SourceStore.capture_reference("https://docs.example/page#part", workspace=tmp_path,
                                                  allowed_domains=["docs.example"])
    assert captured["text"] == "Original page bytes: Port 42"
    assert captured["locator"] == "https://docs.example/page" and captured["retrieval_type"] == "web_page"


def test_cancelled_capture_joins_its_owned_reader():
    import threading
    from retrieved_evidence import capture_async
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def reader(*args, **kwargs):
        started.set()
        release.wait(timeout=2)
        finished.set()
        return {}, [], []
    async def run():
        with patch("retrieved_evidence.capture_result_evidence", reader):
            task = asyncio.create_task(capture_async({}, workspace=Path.cwd()))
            await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert finished.is_set()
    asyncio.run(run())


@pytest.mark.parametrize("accepted", [False, True])
def test_real_source_parent_releases_only_frozen_checked_span(accepted):
    path, span = real_span()
    graph = TaskGraph("Review limits")
    graph.add_node(TaskNode("retrieve", "Retriever", "Read source", "Read source", input_artifacts={
        "task_contract": {"objective": "Read limits", "operation": "retrieve", "inputs": [str(path)],
            "expected_output": "Review word limits", "acceptance_check": "Correct limits"},
        "result_gate": result_gate_policy()}))
    graph.add_node(TaskNode("child", "Child", "Use limits", "Use frozen evidence", dependencies={"retrieve"}))
    graph.add_node(TaskNode("grandchild", "Child", "Retain evidence", "Retain frozen evidence", dependencies={"child"}))
    class Worker:
        default_model = "fixture"
        default_effort = "low"
        max_concurrency = 1
        def __init__(self): self.calls = []
        async def spawn_restricted(self, prompt, role, **options):
            context = json.loads(prompt.split("INPUTS:\n")[1])
            assert context["source_registry"][0]["text"] == span
            value = {"checks": [{"id": "candidate_1", "verdict": "PASS" if accepted else "FAIL",
                                 "issues": [] if accepted else ["Wrong association"]}]}
            return SwarmResult(role, "SUCCESS", value, json.dumps(value))
        async def spawn(self, prompt, role, **options):
            self.calls.append(role)
            if role == "Retriever":
                value = finding(path, span)
            else:
                assert json.dumps(span)[1:-1] in prompt and "frozen_dependency_span" in prompt
                value = "Uses checked limits"
            return SwarmResult(role, "SUCCESS", value, json.dumps(value))
    async def run():
        worker = Worker()
        saved = []
        result = await execute_graph(graph, worker, on_result_commit=lambda n, e: saved.append(n.id))
        if accepted:
            packet = result["retrieve"]["captured_evidence"]
            validate_capture_packet(packet)
            assert saved == ["retrieve", "child", "grandchild"]
            assert result["grandchild"]["frozen_evidence"] == [packet]
            validate_retained(graph, worker, result)
            before = list(worker.calls)
            await execute_graph(graph, worker, retained_results=result)
            assert worker.calls == before
            corrupt = deepcopy(result)
            corrupt["retrieve"]["captured_evidence"]["spans"][0]["text"] = "corrupt"
            with pytest.raises(ValueError, match="identity"):
                validate_retained(graph, worker, corrupt)
        else:
            assert result == {} and saved == [] and worker.calls == ["Retriever"]
            assert graph.nodes["child"].status == TaskStatus.CANCELLED
    asyncio.run(run())


def test_span_offsets_are_validated_even_if_packet_hash_is_recomputed(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("Port 42", encoding="utf-8")
    _, sources, spans = capture_result_evidence(finding(path, "Port 42"), workspace=tmp_path)
    spans[0]["start"] = 1
    packet = {"sources": sources, "spans": spans}
    packet["hash"] = identity(packet)
    with pytest.raises(ValueError, match="span identity"):
        validate_capture_packet(packet)
