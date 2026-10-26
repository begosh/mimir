"""Tests for engine-owned source capture across mixed research workers and downstream span completeness (P1.2)."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import SwarmResult, WorkerFailure
from post_worker import material_finding_contract, result_gate_policy
from retrieved_evidence import (
    capture_async,
    capture_result_evidence,
    inline_spans,
    validate_capture_packet,
    validate_downstream_span_completeness,
)
from scheduler import execute_graph, validate_retained
from source_store import SourceStore, identity
from task_graph import TaskGraph, TaskNode, TaskStatus


def test_ordinary_research_worker_source_capture_and_dependent_binding(tmp_path):
    """An ordinary research worker citing a workspace file has evidence captured and frozen for dependents."""
    doc = tmp_path / "system_spec.txt"
    doc.write_text("Overview\nThroughput: 5000 rps; P99 latency: 12ms.\nFooter.", encoding="utf-8")
    excerpt = "Throughput: 5000 rps; P99 latency: 12ms."

    graph = TaskGraph("System metrics analysis")
    graph.add_node(TaskNode("research", "Domain-Analyst", "Analyze system specs", "Analyze system specs",
                            input_artifacts={"task_contract": {"objective": "Analyze system specs", "operation": "research",
                                                               "inputs": [str(doc)], "expected_output": "Throughput and latency",
                                                               "acceptance_check": "Exact metrics from spec"},
                                             "result_gate": result_gate_policy()},
                            required_evidence=True))
    graph.add_node(TaskNode("dependent", "Code-Architect", "Design architecture", "Design architecture",
                            dependencies={"research"},
                            input_artifacts={"task_contract": {"objective": "Design architecture", "operation": "research",
                                                               "inputs": ["system_spec.txt"], "expected_output": "Target design",
                                                               "acceptance_check": "Grounded in spec"}}))

    worker_calls = []

    class MockWorker:
        default_model = "fixture"
        default_effort = "low"
        max_concurrency = 1
        workspace = tmp_path

        async def spawn_restricted(self, prompt, role, **kwargs):
            # Result Gate check
            val = {"checks": [{"id": "candidate_1", "verdict": "PASS", "issues": []}]}; return SwarmResult(role, "SUCCESS", val, json.dumps(val))

        async def spawn(self, prompt, role, **kwargs):
            worker_calls.append((role, prompt))
            if role == "Domain-Analyst":
                finding = {
                    "answer": "System throughput is 5000 rps with 12ms P99 latency.",
                    "sources": [{"id": "raw_spec", "locator": str(doc), "retrieval_type": "local_file",
                                 "retrieved_at": "", "support_excerpt": excerpt}],
                    "claims": [{"text": "Throughput is 5000 rps with 12ms P99 latency.", "source_ids": ["raw_spec"],
                                "support_status": "supported", "rationale": "Direct spec quote"}],
                    "gaps": []
                }
                return SwarmResult(role, "SUCCESS", finding, json.dumps(finding))
            else:
                # Dependent should receive frozen span in prompt
                assert "frozen_dependency_span" in prompt
                assert excerpt in prompt
                dependent_finding = {
                    "answer": "Architecture budgeted for 5000 rps at 12ms P99.",
                    "sources": [],
                    "claims": [],
                    "gaps": []
                }
                return SwarmResult(role, "SUCCESS", dependent_finding, json.dumps(dependent_finding))

    async def run():
        results = await execute_graph(graph, MockWorker())
        assert "research" in results and "dependent" in results

        # Verify engine-owned capture on research node
        research_env = results["research"]
        captured = research_env.get("captured_evidence")
        assert captured is not None
        validate_capture_packet(captured)

        # Source ID was converted from raw_spec to capture_<sha256>
        captured_source = captured["sources"][0]
        assert captured_source["id"].startswith("capture_")
        assert captured_source["id"] != "raw_spec"
        assert captured_source["locator"] == str(doc.resolve())

        # Claim was rebound to the engine capture ID
        assert research_env["result"]["claims"][0]["source_ids"] == [captured_source["id"]]

        # Dependent envelope inherited frozen evidence
        dep_env = results["dependent"]
        assert dep_env.get("frozen_evidence") == [captured]

    asyncio.run(run())


def test_mixed_worker_ungrounded_excerpt_fails_capture_and_blocks_dependent(tmp_path):
    """If an ordinary research worker returns an ungrounded or altered excerpt, engine capture fails closed."""
    doc = tmp_path / "data.txt"
    doc.write_text("Measurement: temperature is 21C.", encoding="utf-8")

    graph = TaskGraph("Temperature check")
    graph.add_node(TaskNode("research", "Domain-Analyst", "Inspect temp", "Inspect temp",
                            input_artifacts={"task_contract": {"objective": "Inspect temp", "operation": "research",
                                                               "inputs": [str(doc)], "expected_output": "Temp",
                                                               "acceptance_check": "Grounded"},
                                             "result_gate": result_gate_policy()},
                            required_evidence=True))
    graph.add_node(TaskNode("child", "Code-Architect", "Act on temp", "Act on temp", dependencies={"research"}))

    class Worker:
        default_model = "fixture"
        default_effort = "low"
        max_concurrency = 1
        workspace = tmp_path

        async def spawn(self, prompt, role, **kwargs):
            # Worker hallucinates excerpt not present in data.txt
            finding = {
                "answer": "Temperature is 99C.",
                "sources": [{"id": "s1", "locator": str(doc), "retrieval_type": "local_file",
                             "retrieved_at": "", "support_excerpt": "Measurement: temperature is 99C."}],
                "claims": [{"text": "Temperature is 99C.", "source_ids": ["s1"],
                            "support_status": "supported", "rationale": "Grounded"}],
                "gaps": []
            }
            return SwarmResult(role, "SUCCESS", finding, json.dumps(finding))

    async def run():
        results = await execute_graph(graph, Worker())
        assert results == {}
        node = graph.nodes["research"]
        assert node.status == TaskStatus.FAILED
        assert node.rejected_output is not None
        assert node.rejected_output["reason"] == "Engine source capture failed"
        assert "absent from engine-captured source" in node.rejected_output["capture_error"]
        assert graph.nodes["child"].status == TaskStatus.CANCELLED

    asyncio.run(run())


def test_downstream_span_completeness_rejects_missing_upstream_spans():
    """If a dependency result claims support from a source missing from frozen evidence, downstream admission fails."""
    child_node = TaskNode("child", "Worker", "Child task", "Child task", dependencies={"parent"})
    dependency_results = {
        "parent": {
            "result": {
                "answer": "Finding",
                "claims": [{"text": "Critical claim", "source_ids": ["capture_unbound_123"],
                            "support_status": "supported", "rationale": "Claimed"}],
                "sources": []
            },
            # frozen_evidence is present in run, but missing spans for capture_unbound_123
            "frozen_evidence": [{"sources": [{"id": "capture_other"}], "spans": [{"source_id": "capture_other"}]}]
        }
    }

    with pytest.raises(ValueError, match="incomplete upstream evidence: source 'capture_unbound_123' cited by dependency 'parent' is missing frozen spans"):
        validate_downstream_span_completeness(child_node, dependency_results)


def test_downstream_contract_input_completeness_rejects_unbound_requirements():
    """If a dependent contract requires explicit inputs that are not bound in evidence, admission halts."""
    child_node = TaskNode("child", "Worker", "Child task", "Child task", dependencies={"parent"},
                          input_artifacts={"task_contract": {"inputs": ["capture_required_spec_99.txt"]}})
    dependency_results = {
        "parent": {
            "result": {"answer": "Parent answer", "claims": [], "sources": []},
            "frozen_evidence": [{"sources": [{"id": "capture_different"}], "spans": [{"source_id": "capture_different"}]}]
        }
    }

    with pytest.raises(ValueError, match="requires input 'capture_required_spec_99.txt' which is not bound in available evidence"):
        validate_downstream_span_completeness(child_node, dependency_results)


def test_identical_file_references_across_workers_share_engine_identity_and_timestamp(tmp_path):
    """Concurrent or peer workers referencing the same content receive deterministic identities and timestamps."""
    shared_file = tmp_path / "shared_config.txt"
    shared_file.write_text("port: 8080\nenv: production", encoding="utf-8")

    rec1 = SourceStore.capture_reference(str(shared_file), workspace=tmp_path)
    rec2 = SourceStore.capture_reference(str(shared_file), workspace=tmp_path)

    assert rec1["id"] == rec2["id"]
    assert rec1["sha256"] == rec2["sha256"]
    assert rec1["retrieved_at"] == rec2["retrieved_at"]


def test_bounded_span_delivery_preserves_offsets_and_line_numbers(tmp_path):
    """Engine computes exact line numbers and character offsets without guessing."""
    doc = tmp_path / "multiline.txt"
    lines = [f"Line {i:02d}: text content" for i in range(1, 11)]
    doc.write_text("\n".join(lines), encoding="utf-8")

    target_span = "Line 04: text content\nLine 05: text content"
    finding = {
        "answer": "Lines 4 and 5",
        "sources": [{"id": "w1", "locator": str(doc), "retrieval_type": "local_file",
                     "retrieved_at": "", "support_excerpt": target_span}],
        "claims": [{"text": "Extracted", "source_ids": ["w1"], "support_status": "supported", "rationale": "Text"}],
        "gaps": []
    }

    output, sources, spans = capture_result_evidence(finding, workspace=tmp_path)
    packet = {"sources": sources, "spans": spans}
    packet["hash"] = identity(packet)

    inlined = inline_spans(packet, "frozen_dependency_span")
    assert len(inlined) == 1
    span_item = inlined[0]

    assert span_item["line_start"] == 4
    assert span_item["line_end"] == 5
    assert span_item["text"] == target_span
    assert span_item["delivery"] == "frozen_dependency_span"
