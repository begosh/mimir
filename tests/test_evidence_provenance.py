"""Direct behavioral tests at the EvidenceProvenance interface seam.

Tests exercise:
1. Local-substitutable workspace files via tmp_path and injectable https_fetcher adapter at the internal seam.
2. Lifecycle entry points: from_manifest, from_state, bind_graph_sources, capture_worker_evidence,
   verify_task_result, restore_task_evidence, attach_envelope_lineage.
3. Synthesis & publication entry points: build_synthesis_registry, verify_conflict_preservation, audit_publication.
4. DSPy/RLM bounded query dispatch (dispatch_query).
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evidence_provenance import EvidenceProvenance, ProvenanceVerdict, identity
from mimir_config import ConfigurationRequired
from task_graph import TaskGraph, TaskNode


def test_from_manifest_and_https_fetcher_seam(tmp_path: Path):
    """Manifest capture uses local-substitutable files and the injectable https_fetcher adapter without sockets."""
    local_file = tmp_path / "spec.txt"
    local_file.write_text("L01 Critic limit: 180 words.\nL02 Specialist limit: 250 words.", encoding="utf-8")

    fetched_urls: list[str] = []

    def fake_https_fetcher(url: str, **kwargs) -> str:
        fetched_urls.append(url)
        return "Remote policy: port is 8080 in review mode."

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "allowed_domains": ["docs.example"],
                "sources": [
                    {"id": "local_spec", "path": "spec.txt", "status": "user_supplied"},
                    {"id": "remote_doc", "url": "https://docs.example/policy", "status": "retrieved"},
                ],
            }
        ),
        encoding="utf-8",
    )

    prov = EvidenceProvenance.from_manifest(manifest, workspace=tmp_path, https_fetcher=fake_https_fetcher)
    assert fetched_urls == ["https://docs.example/policy"]
    assert set(prov.records) == {"local_spec", "remote_doc"}
    assert prov.source_statuses == {"local_spec": "user_supplied", "remote_doc": "retrieved"}
    assert prov.allowed_domains == ["docs.example"]

    # Domain allowlist is enforced ahead of the https_fetcher seam
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text(
        json.dumps(
            {
                "allowed_domains": ["docs.example"],
                "sources": [{"id": "bad", "url": "https://evil.example/payload"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="allowlist"):
        EvidenceProvenance.from_manifest(bad_manifest, workspace=tmp_path, https_fetcher=fake_https_fetcher)
    assert len(fetched_urls) == 1  # Adapter was never called for unapproved domain


def test_dynamic_worker_capture_via_https_adapter_and_upstream_binding(tmp_path: Path):
    """Dynamic worker capture uses the instance https_fetcher adapter, freezes spans, and binds to dependents."""
    remote_body = "Header\ncritic = 180 if mode == 'review' else 250\nFooter"
    prov = EvidenceProvenance(
        workspace=tmp_path,
        allowed_domains=["api.example"],
        https_fetcher=lambda url, **kw: remote_body,
    )

    parent = TaskNode(
        "retrieve_node",
        "Retriever",
        "Fetch remote rules",
        "Fetch rules",
        input_artifacts={"task_contract": {"operation": "retrieve", "inputs": ["https://api.example/rules"]}},
    )
    child = TaskNode(
        "extract_node",
        "Extractor",
        "Extract limits",
        "Extract limits",
        dependencies={"retrieve_node"},
        input_artifacts={"task_contract": {"operation": "extract", "inputs": []}},
    )

    worker_output = {
        "answer": "Critic 180; specialists 250.",
        "sources": [
            {
                "id": "w_remote",
                "locator": "https://api.example/rules#section-2",
                "retrieval_type": "web_page",
                "retrieved_at": "invented",
                "support_excerpt": "critic = 180 if mode == 'review' else 250",
            }
        ],
        "claims": [
            {
                "text": "Critic is 180 and specialists is 250.",
                "source_ids": ["w_remote"],
                "support_status": "supported",
                "rationale": "Exact conditional expression",
            }
        ],
        "gaps": [],
    }

    rewritten, did_capture = asyncio.run(prov.capture_worker_evidence(parent, worker_output, {}))
    assert did_capture is True
    cap_id = rewritten["sources"][0]["id"]
    assert cap_id.startswith("capture_")
    assert rewritten["sources"][0]["locator"] == "https://api.example/rules"
    assert rewritten["claims"][0]["source_ids"] == [cap_id]

    # Verify deterministic checks pass on the captured span
    verdict = prov.verify_task_result(rewritten, node=parent)
    assert verdict.verdict == "REVIEW"
    assert not verdict.failed

    # Stamp lineage onto parent envelope and bind to child
    parent_envelope: dict = {"result": rewritten}
    prov.attach_envelope_lineage(parent, parent_envelope, {})
    assert "captured_evidence" in parent_envelope
    assert "frozen_evidence" in parent_envelope

    completed = {"retrieve_node": parent_envelope}
    assert prov.bind_upstream_evidence(child, completed) is True
    bound_child = child.input_artifacts["supplied_sources"]
    assert len(bound_child) == 1
    assert bound_child[0]["delivery"] == "frozen_dependency_span"
    assert bound_child[0]["line_start"] == 2
    assert bound_child[0]["line_end"] == 2

    # Checkpoint restore validates lineage and bound citations
    prov.restore_task_evidence(parent, parent_envelope, {})


def test_standalone_verify_task_result_catches_swapped_associations_and_bad_units(tmp_path: Path):
    """verify_task_result works standalone without a TaskNode for offline candidate scoring."""
    source_file = tmp_path / "recipe.txt"
    source_file.write_text("L01 Dough: 600ml water, 250g flour. Critic has 180 words, specialist has 250 words.", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{"id": "recipe", "path": "recipe.txt"}]}), encoding="utf-8")

    prov = EvidenceProvenance.from_manifest(manifest, workspace=tmp_path)
    bound = [
        {
            **prov.records["recipe"],
            "status": "user_supplied",
            "delivery": "supplied_inline",
        }
    ]

    # 1. Valid extraction candidate -> REVIEW (never PASS)
    good_candidate = {
        "answer": "Use 600ml water and 250g flour. Critic has 180 words and specialist has 250 words.",
        "sources": [
            {
                "id": "recipe",
                "locator": "recipe:L01",
                "retrieval_type": "local_file",
                "retrieved_at": prov.records["recipe"]["retrieved_at"],
                "support_excerpt": "600ml water, 250g flour",
            }
        ],
        "claims": [
            {
                "text": "600ml water and 250g flour",
                "source_ids": ["recipe"],
                "support_status": "supported",
                "rationale": "Stated in L01",
            }
        ],
        "gaps": [],
    }
    good_verdict = prov.verify_task_result(good_candidate, bound_sources=bound, operation="extract")
    assert isinstance(good_verdict, ProvenanceVerdict)
    assert good_verdict.verdict == "REVIEW"
    assert not good_verdict.failed

    # 2. Swapped entity-value association -> FAIL (deterministic_association)
    swapped_candidate = deepcopy(good_candidate)
    swapped_candidate["answer"] = "Critic has 250 words and specialist has 180 words."
    swapped_verdict = prov.verify_task_result(swapped_candidate, bound_sources=bound, operation="extract")
    assert swapped_verdict.failed
    assert swapped_verdict.check_type == "deterministic_association"
    assert any("Corrupted field association" in issue for issue in swapped_verdict.issues)

    # 3. Altered unit (600g water instead of 600ml) -> FAIL (structural_provenance)
    bad_unit_candidate = deepcopy(good_candidate)
    bad_unit_candidate["answer"] = "Use 600g water and 250g flour."
    unit_verdict = prov.verify_task_result(bad_unit_candidate, bound_sources=bound, operation="extract")
    assert unit_verdict.failed
    assert any("Number/unit pair absent" in issue for issue in unit_verdict.issues)


def test_synthesis_registry_conflict_preservation_and_publication_audit(tmp_path: Path):
    """Stage 4 methods consolidate synthesis sources, enforce conflict preservation, and audit references."""
    doc = tmp_path / "config.py"
    doc.write_text("PORT = 8080\nLEGACY_PORT = 9090\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{"id": "cfg", "path": "config.py"}]}), encoding="utf-8")
    prov = EvidenceProvenance.from_manifest(manifest, workspace=tmp_path)

    state = {
        "research_config": {
            "sources": prov.to_list(),
            "source_statuses": prov.source_statuses,
        },
        "graph": {"nodes": {"t1": {"id": "t1", "input_artifacts": {}}, "t2": {"id": "t2", "input_artifacts": {}}}},
        "completed_data": {
            "t1": {
                "role": "Domain-Analyst",
                "result": {
                    "answer": "Service port is 8080.",
                    "sources": [
                        {
                            "id": "cfg",
                            "locator": str(doc),
                            "retrieval_type": "local_file",
                            "retrieved_at": prov.records["cfg"]["retrieved_at"],
                            "support_excerpt": "PORT = 8080",
                        }
                    ],
                    "claims": [
                        {
                            "text": "Service port is 8080.",
                            "source_ids": ["cfg"],
                            "support_status": "supported",
                            "rationale": "Line 1",
                        }
                    ],
                    "gaps": [],
                },
            },
            "t2": {
                "role": "Domain-Analyst",
                "result": {
                    "answer": "Service port is 9090.",
                    "sources": [
                        {
                            "id": "cfg",
                            "locator": str(doc),
                            "retrieval_type": "local_file",
                            "retrieved_at": prov.records["cfg"]["retrieved_at"],
                            "support_excerpt": "LEGACY_PORT = 9090",
                        }
                    ],
                    "claims": [
                        {
                            "text": "Service port is 9090.",
                            "source_ids": ["cfg"],
                            "support_status": "supported",
                            "rationale": "Line 2",
                        }
                    ],
                    "gaps": [],
                },
            },
        },
    }

    sources, supplied, findings, critiques = prov.build_synthesis_registry(state)
    assert len(sources) == 1
    assert sources[0]["id"] == "cfg"
    assert set(sources[0]["support_excerpts"]) == {"PORT = 8080", "LEGACY_PORT = 9090"}

    # Suppressing port 9090 in synthesis fails conflict preservation
    suppressed = {"answer": "The service runs on port 8080 [config.py].", "limitations": []}
    bad_conflict = prov.verify_conflict_preservation(suppressed, {"findings": findings})
    assert bad_conflict.failed
    assert bad_conflict.check_type == "conflict_integrity"

    # Preserving both 8080 and 9090 passes conflict preservation
    preserved = {
        "answer": "Sources disagree between port 8080 and port 9090 in [config.py].",
        "limitations": [],
    }
    ok_conflict = prov.verify_conflict_preservation(preserved, {"findings": findings})
    assert not ok_conflict.failed

    # Audit publication checks resolved references and unbound citations
    pub_ledger = prov.audit_publication(
        preserved["answer"] + " Also cites [hallucinated.py:L99].",
        state["completed_data"],
        scout_gaps=["External benchmark unavailable"],
    )
    assert pub_ledger["coverage"] == "partial"
    assert pub_ledger["final_reference_audit"]["unbound_references"] == ["hallucinated.py:L99"]
    assert any(g["task_id"] == "public_scout" for g in pub_ledger["gaps"])


def test_dispatch_query_allowlist_and_hash(tmp_path: Path):
    """dispatch_query executes allowlisted read-only source queries and returns their canonical hash."""
    doc = tmp_path / "notes.txt"
    doc.write_text("Alpha Beta Gamma Delta", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{"id": "notes", "path": "notes.txt"}]}), encoding="utf-8")

    prov = EvidenceProvenance.from_manifest(manifest, workspace=tmp_path)
    span, span_hash = prov.dispatch_query("read_span", {"source_id": "notes", "start": 6, "end": 10})
    assert span["text"] == "Beta"
    assert span_hash == identity(span)

    with pytest.raises(ValueError, match="allowlist"):
        prov.dispatch_query("delete_sources", {})
