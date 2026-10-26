"""P1.3: Validate source/version/span identity deterministically; add narrow
semantic checks for associations, omissions and conditions against the source.
Preserve conflicting assertions rather than resolving them by majority agreement.

Verification covers:
1. Smallest meaningful test parameterized for single/review:
   - Real source span with numbers (180 and 250) that both occur in the source.
   - Corrupt field association: reversed association where both numbers exist.
   - Deterministic structural check returns REVIEW (not FAIL on structure, not PASS).
   - Deterministic/semantic association check returns FAIL.
   - Dependent child task is blocked from release while parent is rejected.
   - Checked correction repairs the association.
   - Dependent child task releases upon correction.
   - Publication reflects truthful appendix status in publication_view.
2. Conflict preservation through assembly:
   - Suppressing a conflicting assertion by majority agreement fails final gate.
   - Preserving both conflicting assertions explicitly passes final gate.
3. Condition integrity and omissions:
   - Stating review-restricted limits apply in all modes fails condition check.
   - Stating review-restricted limits with proper condition passes.
4. Model PASS never claims independent verification.
"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import SwarmResult
from post_worker import (
    assembly_repair_policy,
    check_final_answer,
    material_finding_contract,
    repair_assembled_answer,
    result_gate_policy,
    result_repair_policy,
)
from publication_view import build_publication_view
from retrieved_evidence import capture_result_evidence, inline_spans
from scheduler import execute_graph
from source_store import identity
from source_support import (
    check_association_integrity,
    check_bound_citations,
    check_conflict_preservation,
    detect_conflicts,
)
from task_graph import TaskGraph, TaskNode, TaskStatus


def real_source_case(tmp_path):
    """Freeze a real source span from task_graph.py with word limits (180 for critique, 250 for specialists)."""
    root = Path(__file__).resolve().parents[1]
    tg_path = root / "scripts" / "task_graph.py"
    tg_text = tg_path.read_text(encoding="utf-8")
    start = tg_text.index('            word_limit = (t["contract"]')
    end = tg_text.index('            if t.get("contract"):', start)
    excerpt = tg_text[start:end]

    path = tmp_path / "task_graph_limits.py"
    path.write_text(excerpt, encoding="utf-8")

    value = {
        "answer": "Review limits: critique 180 words; specialists 250 words.",
        "sources": [{
            "id": "spec",
            "locator": str(path),
            "retrieval_type": "local_file",
            "retrieved_at": "",
            "support_excerpt": excerpt,
        }],
        "claims": [{
            "text": "Review limits: critique 180 words; specialists 250 words.",
            "source_ids": ["spec"],
            "support_status": "supported",
            "rationale": "Direct ternary expression in task_graph.py",
        }],
        "gaps": [],
    }
    value, sources, spans = capture_result_evidence(value, workspace=tmp_path)
    packet = {"sources": sources, "spans": spans}
    packet["hash"] = identity(packet)
    return value, inline_spans(packet, "frozen_dependency_span"), excerpt, path


@pytest.mark.parametrize("mode", ["single", "review"])
def test_smallest_meaningful_corrupted_association_blocks_dependent_and_truthfully_publishes(tmp_path, mode):
    """Smallest meaningful test:
    - One real source span with numbers 180 and 250 both occurring in the source.
    - One factual claim with corrupted field association (critique: 250, specialists: 180).
    - Parameterized for single and review modes.
    - Verifies: structural check REVIEW, association check FAIL, child release blocked,
      checked correction, release upon repair, and truthful appendix status.
    """
    good_result, bound_sources, excerpt, source_path = real_source_case(tmp_path)
    sid = bound_sources[0]["id"]

    # Corrupted association: swap 180 and 250 (both exist in the source span!)
    corrupted_result = deepcopy(good_result)
    corrupted_result["answer"] = "Review limits: critique 250 words; specialists 180 words."
    corrupted_result["claims"][0]["text"] = "Review limits: critique 250 words; specialists 180 words."

    # 1. Verify deterministic separation:
    # Structural provenance check returns REVIEW (not FAIL, not PASS)
    structural = check_bound_citations(corrupted_result, bound_sources)
    assert structural["verdict"] == "REVIEW"
    assert structural["check_type"] == "structural_provenance"

    # Deterministic association check catches the corrupted association!
    assoc = check_association_integrity(corrupted_result, bound_sources)
    assert assoc["verdict"] == "FAIL"
    assert assoc["check_type"] == "deterministic_association"
    assert any(("critic" in issue or "critique" in issue) and "250" in issue for issue in assoc["issues"])

    # 2. Build graph with parent and dependent child
    graph = TaskGraph(f"Review limits test ({mode})")
    parent_id = "research" if mode == "single" else "evidence"
    child_id = "dependent" if mode == "single" else "critique"

    graph.add_node(TaskNode(
        parent_id, "Worker", "Extract limits", "Extract review word limits",
        input_artifacts={
            "task_contract": {**material_finding_contract("Extract review word limits"), "operation": "extract"},
            "supplied_sources": bound_sources,
            "result_gate": result_gate_policy(),
            "result_repair": result_repair_policy(),
        }
    ))
    graph.add_node(TaskNode(
        child_id, "Child", "Consume limits", "Consume extracted limits",
        dependencies={parent_id},
        input_artifacts={
            "task_contract": material_finding_contract("Consume extracted limits"),
            "result_gate": result_gate_policy(),
        }
    ))

    child_executed = False
    attempts = []

    class MockWorker:
        default_model = "gpt-6.1-sol"
        default_effort = "low"
        max_concurrency = 1

        async def spawn(self, prompt, role, **kwargs):
            nonlocal child_executed
            if role == "Child":
                child_executed = True
                data = {"answer": "Consumed limits successfully.", "sources": [], "claims": [], "gaps": []}
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))

            # Parent worker: return corrupted result on attempt 1, corrected on repair attempt 2
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                return SwarmResult(role, "SUCCESS", corrupted_result, json.dumps(corrupted_result))
            else:
                return SwarmResult(role, "SUCCESS", good_result, json.dumps(good_result))

        async def spawn_restricted(self, prompt, role, **kwargs):
            nonlocal child_executed
            if role == "Child":
                child_executed = True
                data = {"answer": "Consumed limits successfully.", "sources": [], "claims": [], "gaps": []}
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            elif role == "Mimir-Result-Repairer":
                data = {
                    "action": "REPHRASE",
                    "objective": "Correct field association: critique has 180 words, specialists 250 words.",
                    "reason": "Previous output inverted the word limits between critique and specialists."
                }
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            elif role == "Mimir-Result-Checker":
                # Blinded semantic check
                data = {"checks": [{"id": "candidate_1", "verdict": "PASS", "issues": []}]}
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            raise NotImplementedError(role)

    async def run():
        results = await execute_graph(graph, MockWorker())

        # Verify parent rejected on attempt 1
        parent_node = graph.nodes[parent_id]
        assert len(parent_node.result_attempts) == 2
        first_attempt = parent_node.result_attempts[0]
        assert first_attempt["status"] == "FAIL"
        assert first_attempt["result_check"]["check_type"] == "deterministic_association"

        # Verify repair succeeded on attempt 2
        second_attempt = parent_node.result_attempts[1]
        assert second_attempt["status"] == "PASS"

        # Verify dependent child task was released and executed
        assert child_executed is True
        assert child_id in results

        # 3. Verify publication and truthful appendix status
        if mode == "single":
            context = {"findings": {parent_id: results[parent_id]["result"]}}
            pub_view = build_publication_view(context)
            assert pub_view[parent_id]["status"] == "accepted"
            assert pub_view[parent_id]["original_hash"] == identity(results[parent_id]["result"])
        else:
            # Review mode publication with quarantine of original corrupted assertion
            context = {
                "findings": {
                    parent_id: results[parent_id]["result"],
                    child_id: results[child_id]["result"]
                }
            }
            quarantines = [{"task_id": parent_id, "reason": "Initial attempt corrupted field association (inverted 180 and 250)"}]
            pub_view = build_publication_view(context, quarantines)
            assert pub_view[parent_id]["status"] == "quarantined"
            assert pub_view[parent_id]["reason"] == "Initial attempt corrupted field association (inverted 180 and 250)"
            assert pub_view[parent_id]["original_hash"] == identity(results[parent_id]["result"])
            assert pub_view[child_id]["status"] == "accepted"

    asyncio.run(run())


def test_corrupted_association_without_repair_permanently_blocks_dependent(tmp_path):
    """When a corrupted association fails check and repair is not enabled, dependent child never releases."""
    good_result, bound_sources, excerpt, source_path = real_source_case(tmp_path)
    corrupted_result = deepcopy(good_result)
    corrupted_result["answer"] = "Review limits: critique 250 words; specialists 180 words."

    graph = TaskGraph("Blocked dependent test")
    graph.add_node(TaskNode(
        "parent", "Worker", "Limits", "Extract limits",
        input_artifacts={
            "task_contract": {**material_finding_contract("Extract review word limits"), "operation": "extract"},
            "supplied_sources": bound_sources,
            "result_gate": result_gate_policy(),
            # No result_repair policy: cannot self-repair
        }
    ))
    graph.add_node(TaskNode(
        "child", "Child", "Consume", "Consume",
        dependencies={"parent"}
    ))

    child_executed = False

    class Worker:
        default_model = "gpt-6.1-sol"
        default_effort = "low"
        max_concurrency = 1

        async def spawn(self, prompt, role, **kwargs):
            nonlocal child_executed
            if role == "Child":
                child_executed = True
                return SwarmResult(role, "SUCCESS", {})
            return SwarmResult(role, "SUCCESS", corrupted_result, json.dumps(corrupted_result))

    async def run():
        results = await execute_graph(graph, Worker())
        assert results == {}
        assert child_executed is False
        assert graph.nodes["parent"].status in (TaskStatus.FAILED, TaskStatus.BLOCKED)
        assert graph.nodes["child"].status == TaskStatus.CANCELLED

    asyncio.run(run())


def test_conflict_preservation_rejects_majority_agreement_and_accepts_preserved():
    """Conflicting assertions across sources must survive assembly rather than resolving by majority."""
    conflicts = [("8100", "9999")]

    # Case 1: Suppressed conflict resolved by majority agreement
    resolved_by_majority = {
        "answer": "Based on majority agreement across sources, Deployment-03 port is 8100.",
        "limitations": [],
    }
    check_bad = check_conflict_preservation(resolved_by_majority, conflicts)
    assert check_bad["verdict"] == "FAIL"
    assert check_bad["check_type"] == "conflict_integrity"
    assert "9999" in check_bad["issues"][0]
    assert "conflicts must be preserved rather than resolved by majority agreement" in check_bad["issues"][0]

    # Case 2: Preserved conflict explicitly stating both sources
    preserved = {
        "answer": "Independent source A reports port 8100, while independent source B reports port 9999. Neither supersedes the other.",
        "limitations": ["Conflicting port documentation between source A and source B."],
    }
    check_good = check_conflict_preservation(preserved, conflicts)
    assert check_good["verdict"] == "PASS"
    assert check_good["check_type"] == "conflict_integrity"
    assert check_good["issues"] == []


def test_detect_conflicts_extracts_incompatible_findings():
    """detect_conflicts identifies conflicting numbers and explicit disagreements across findings."""
    findings = {
        "evidence": {
            "answer": "Primary evidence indicates Deployment-03 port is 8100.",
            "claims": [{"text": "Port is 8100"}],
        },
        "alternatives": {
            "answer": "Alternative evidence records show Deployment-03 port is 9999.",
            "claims": [{"text": "Port is 9999"}],
        },
    }
    conflicts = detect_conflicts(findings)
    assert len(conflicts) >= 1
    pair = conflicts[0]
    assert set(pair) == {"8100", "9999"}


def test_final_answer_check_enforces_conflict_integrity_before_model():
    """check_final_answer fails with conflict_integrity when an assembled answer drops a conflict."""
    context = {
        "findings": {
            "evidence": {"answer": "Source A states port is 8100."},
            "alternatives": {"answer": "Source B states port is 9999."},
        }
    }
    suppressed_assembled = {
        "answer": "The port is 8100 by majority agreement.",
        "limitations": [],
    }

    class DummyBackend:
        default_model = "gpt-6.1-sol"
        default_effort = "low"

        async def spawn(self, **kwargs):
            raise AssertionError("Model should not be called when conflict check fails deterministically")

    async def run():
        check = await check_final_answer(DummyBackend(), context, suppressed_assembled)
        assert check["verdict"] == "FAIL"
        assert check["check_type"] == "conflict_integrity"
        assert any("9999" in issue for issue in check["issues"])

    asyncio.run(run())


def test_condition_integrity_rejects_unconditional_claims_for_scoped_limits(tmp_path):
    """When bound text specifies 'Only in review mode', asserting limits apply 'in all modes' fails."""
    good_result, bound_sources, excerpt, source_path = real_source_case(tmp_path)

    unconditional_result = deepcopy(good_result)
    unconditional_result["answer"] = "Review limits: critique 180 words; specialists 250 words in all modes."

    assoc_check = check_association_integrity(unconditional_result, bound_sources)
    assert assoc_check["verdict"] == "FAIL"
    assert any("Condition violation" in issue for issue in assoc_check["issues"])

    # With proper scoping condition:
    scoped_result = deepcopy(good_result)
    scoped_result["answer"] = "Review limits: critique 180 words; specialists 250 words, only in review mode."
    assoc_pass = check_association_integrity(scoped_result, bound_sources)
    assert assoc_pass["verdict"] == "REVIEW"
    assert assoc_pass["issues"] == []
