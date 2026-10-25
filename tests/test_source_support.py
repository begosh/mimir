"""Bound record identities fail before semantic checking or dependent release."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import SwarmResult
from post_worker import material_finding_contract, result_gate_policy
from retrieved_evidence import capture_result_evidence, inline_spans
from scheduler import execute_graph
from source_store import identity
from source_support import check_bound_citations
from task_graph import TaskGraph, TaskNode


def bound_case(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("Heading\nCritic: 180 words. Specialists: 250 words.\nOnly in review mode.\nOther section.", encoding="utf-8")
    value = {"answer": "Review limits: critic 180; specialists 250.", "sources": [{"id": "original", "locator": str(path),
        "retrieval_type": "local_file", "retrieved_at": "", "support_excerpt": "Critic: 180 words. Specialists: 250 words.\nOnly in review mode."}],
        "claims": [{"text": "Review limits: critic 180; specialists 250.", "source_ids": ["original"],
                    "support_status": "supported", "rationale": "Review-only conditional"}], "gaps": []}
    value, sources, spans = capture_result_evidence(value, workspace=tmp_path)
    packet = {"sources": sources, "spans": spans}
    packet["hash"] = identity(packet)
    return value, inline_spans(packet, "frozen_dependency_span")


@pytest.mark.parametrize("defect", ["unknown_id", "stale_id", "timestamp", "type", "excerpt", "offsets", "line", "claim_link"])
def test_provenance_defect_never_calls_semantic_checker_or_releases_child(tmp_path, defect):
    result, sources = bound_case(tmp_path)
    sid = sources[0]["id"]
    source = result["sources"][0]
    if defect == "unknown_id": source["id"] = "unknown"
    elif defect == "stale_id": source["id"] = "capture_" + "0" * 64
    elif defect == "timestamp": source["retrieved_at"] = "2026-10-01T00:00:00Z"
    elif defect == "type": source["retrieval_type"] = "web_page"
    elif defect == "excerpt": source["support_excerpt"] = "Other section."
    elif defect == "offsets": source["locator"] = sid + "#chars=0-10"
    elif defect == "line": source["locator"] = sid + ":L99"
    else: result["claims"][0]["source_ids"] = ["unknown"]
    graph = TaskGraph("Review limits")
    graph.add_node(TaskNode("parent", "Worker", "Read limits", "Read limits", input_artifacts={
        "task_contract": material_finding_contract("Read review limits"), "supplied_sources": sources,
        "result_gate": result_gate_policy()}))
    graph.add_node(TaskNode("child", "Child", "Use", "Use", dependencies={"parent"}))
    class Worker:
        default_model = "fixture"
        default_effort = "low"
        max_concurrency = 1
        async def spawn(self, prompt, role, **kwargs):
            assert role == "Worker", "Rejected parent released its child"
            return SwarmResult(role, "SUCCESS", result, json.dumps(result))
        async def spawn_restricted(self, **kwargs):
            raise AssertionError("Structural defect reached semantic checker")
    async def run():
        assert await execute_graph(graph, Worker()) == {}
        check = graph.nodes["parent"].rejected_output["result_check"]
        assert check["verdict"] == "FAIL"
        if defect != "claim_link": assert check["check_type"] == "structural_provenance"
    asyncio.run(run())


@pytest.mark.parametrize("locator", ["full", "id", "span", "lines"])
def test_documented_locator_forms_pass_structure_without_claiming_semantic_support(tmp_path, locator):
    result, sources = bound_case(tmp_path)
    source = sources[0]
    if locator == "id": result["sources"][0]["locator"] = source["id"]
    elif locator == "span": result["sources"][0]["locator"] = f'{source["id"]}#chars={source["span_start"]}-{source["span_end"]}'
    elif locator == "lines": result["sources"][0]["locator"] = source["id"] + ":L2-L3"
    assert check_bound_citations(result, sources)["verdict"] == "REVIEW"


def test_two_spans_do_not_authorize_excerpt_between_them(tmp_path):
    result, sources = bound_case(tmp_path)
    first = {**sources[0], "text": "Critic: 180 words."}
    second = {**sources[0], "text": "Only in review mode."}
    result["sources"][0]["support_excerpt"] = "Specialists: 250 words."
    assert check_bound_citations(result, [first, second])["verdict"] == "FAIL"


def test_same_id_conflicting_versions_fail_structure(tmp_path):
    result, sources = bound_case(tmp_path)
    changed = {**sources[0], "sha256": "0" * 64}
    assert check_bound_citations(result, sources + [changed])["verdict"] == "FAIL"


def test_existing_line_does_not_authorize_quote_from_another_line(tmp_path):
    result, sources = bound_case(tmp_path)
    result["sources"][0]["locator"] = sources[0]["id"] + ":L2"
    result["sources"][0]["support_excerpt"] = "Only in review mode."
    assert check_bound_citations(result, sources)["verdict"] == "FAIL"


def test_full_manifest_content_hash_is_checked_separately(tmp_path):
    result, sources = bound_case(tmp_path)
    source = {**sources[0], "delivery": "supplied_inline", "sha256": "0" * 64}
    assert check_bound_citations(result, [source])["verdict"] == "FAIL"
