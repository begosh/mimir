"""P1.6: Separate structural provenance defects from model support labels;
avoid treating abbreviated-locator string mismatches as citation entailment failures.

Verification covers:
1. Exact source-ID abbreviations, basenames and unscoped IDs resolve without requiring literal full-path comparison.
2. Unbound final references in synthesis text are audited and flagged under unbound_references.
3. Structural provenance checks consistently assign check_type="structural_provenance".
4. Engine presentation cleanly separates structural reference presence from model support judgments and updates coverage.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine
from backend import SwarmResult
from extraction_checks import check_extraction
from post_worker import material_finding_contract, result_gate_policy
from research_contract import aggregate_research_results, audit_final_references
from source_support import check_bound_citations
from test_engine_policy import FixtureBackend


def test_abbreviated_locator_and_source_id_resolve_without_full_path():
    """Exact source-ID abbreviations, basenames and unscoped IDs satisfy final reference audit."""
    registry = {
        "sources": [
            {"id": "task_1:spec_doc", "locator": "https://example.test/specs/protocol_v1.html"},
            {"id": "task_2:local_code", "locator": "C:/repo/src/algorithms/solver.py"},
        ],
        "claims": [
            {"text": "Protocol version claim", "source_ids": ["task_1:spec_doc"], "support_status": "supported"},
            {"text": "Algorithm solver claim", "source_ids": ["task_2:local_code"], "support_status": "supported"},
        ],
    }

    # Case 1: Synthesis cites exact full locators
    ans_full = "The protocol is documented in https://example.test/specs/protocol_v1.html and solver.py."
    audit_full = audit_final_references(ans_full, registry)
    assert audit_full["reference_presence_passed"] is True
    assert audit_full["missing_supporting_locators"] == []
    assert audit_full["unbound_references"] == []

    # Case 2: Synthesis cites abbreviated source IDs [spec_doc] and [solver.py]
    ans_abbrev = "The protocol [spec_doc] and the solver implementation [solver.py] support this."
    audit_abbrev = audit_final_references(ans_abbrev, registry)
    assert audit_abbrev["reference_presence_passed"] is True
    assert audit_abbrev["missing_supporting_locators"] == []
    assert len(audit_abbrev["resolved_references"]) >= 2

    # Case 3: Synthesis cites scoped source IDs [task_1:spec_doc]
    ans_scoped = "Reference [task_1:spec_doc] and [local_code] define the limits."
    audit_scoped = audit_final_references(ans_scoped, registry)
    assert audit_scoped["reference_presence_passed"] is True
    assert audit_scoped["missing_supporting_locators"] == []


def test_unbound_final_references_are_detected_and_flagged():
    """Unbound references cited in the answer are caught and flagged in unbound_references."""
    registry = {
        "sources": [
            {"id": "doc_1", "locator": "https://example.test/real_doc.html"},
        ],
        "claims": [
            {"text": "Claim", "source_ids": ["doc_1"], "support_status": "supported"},
        ],
    }

    # Answer cites legitimate doc_1 but invents [unknown_source_99] and [fake_file.py]
    ans_with_unbound = "Based on [real_doc.html], and additionally according to [unknown_source_99] and [fake_file.py]."
    audit = audit_final_references(ans_with_unbound, registry)

    assert audit["reference_presence_passed"] is False
    assert "unknown_source_99" in audit["unbound_references"]
    assert "fake_file.py" in audit["unbound_references"]
    assert audit["missing_supporting_locators"] == []


def test_omitted_supported_source_fails_reference_audit():
    """When a worker-supported source is completely absent from synthesis text, audit flags it."""
    registry = {
        "sources": [
            {"id": "doc_1", "locator": "https://example.test/important_standard.html"},
        ],
        "claims": [
            {"text": "Critical claim", "source_ids": ["doc_1"], "support_status": "supported"},
        ],
    }

    ans_no_cite = "We determined the parameters without citing anything."
    audit = audit_final_references(ans_no_cite, registry)

    assert audit["reference_presence_passed"] is False
    assert "https://example.test/important_standard.html" in audit["missing_supporting_locators"]


def test_structural_provenance_check_type_distinct_from_semantic_support():
    """Structural checks consistently return check_type='structural_provenance'."""
    text = "Source content"
    digest = hashlib.sha256(text.encode()).hexdigest()
    # 1. Bound citation check with unknown source ID
    bound_cit_check = check_bound_citations({"sources": [{"id": "unknown_source_id"}]}, [{
        "id": "s1", "delivery": "supplied_inline", "text": text, "sha256": digest
    }])
    assert bound_cit_check["check_type"] == "structural_provenance"
    assert bound_cit_check["verdict"] == "FAIL"

    # 2. Extraction check with mismatching numbers
    ext_check = check_extraction({"sources": [{"id": "s1"}], "answer": "100 g"}, [{"id": "s1", "text": "50 g"}])
    assert ext_check["check_type"] == "structural_provenance"
    assert ext_check["verdict"] == "FAIL"

    # 3. Final reference audit
    ref_audit = audit_final_references("Text", {"sources": []})
    assert ref_audit["check_type"] == "structural_provenance"
    assert ref_audit["independently_verified"] is False


@pytest.mark.parametrize("mode", ["single", "review"])
def test_end_to_end_presentation_separates_resolution_and_flags_unbound(tmp_path, mode):
    """run_mimir report and JSON payload correctly report reference audit and preserve coverage."""
    state_file = tmp_path / "state.json"
    output_path = tmp_path / "report.md"

    class MockWorker(FixtureBackend):
        async def spawn(self, prompt, role="Worker", **options):
            if role == "Domain-Analyst":
                data = {
                    "answer": "According to [spec], the limit is 100. Also see [unbound_source].",
                    "sources": [{
                        "id": "spec",
                        "locator": "https://example.test/spec.html",
                        "retrieval_type": "web_page",
                        "retrieved_at": "2026-10-26T10:00:00Z",
                        "support_excerpt": "Limit is 100",
                    }],
                    "claims": [{
                        "text": "Limit is 100",
                        "source_ids": ["spec"],
                        "support_status": "supported",
                        "rationale": "Direct statement",
                    }],
                    "gaps": [],
                }
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            elif role == "Code-Architect":
                data = {
                    "answer": "Tradeoff assessment referencing [spec].",
                    "sources": [{
                        "id": "spec",
                        "locator": "https://example.test/spec.html",
                        "retrieval_type": "web_page",
                        "retrieved_at": "2026-10-26T10:00:00Z",
                        "support_excerpt": "Limit is 100",
                    }],
                    "claims": [{
                        "text": "Limit is 100",
                        "source_ids": ["spec"],
                        "support_status": "supported",
                        "rationale": "Direct statement",
                    }],
                    "gaps": [],
                }
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            elif role == "Red-Team-Critic":
                data = {
                    "answer": "Review critique verified against [spec].",
                    "sources": [{
                        "id": "spec",
                        "locator": "https://example.test/spec.html",
                        "retrieval_type": "web_page",
                        "retrieved_at": "2026-10-26T10:00:00Z",
                        "support_excerpt": "Limit is 100",
                    }],
                    "claims": [{
                        "text": "Limit is 100",
                        "source_ids": ["spec"],
                        "support_status": "supported",
                        "rationale": "Direct statement",
                    }],
                    "gaps": [],
                }
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            return await super().spawn(prompt, role=role, **options)

        async def spawn_restricted(self, prompt, role="Worker", **options):
            if role == "Red-Team-Critic":
                data = {
                    "answer": "Review critique verified against [spec].",
                    "sources": [{
                        "id": "spec",
                        "locator": "https://example.test/spec.html",
                        "retrieval_type": "web_page",
                        "retrieved_at": "2026-10-26T10:00:00Z",
                        "support_excerpt": "Limit is 100",
                    }],
                    "claims": [{
                        "text": "Limit is 100",
                        "source_ids": ["spec"],
                        "support_status": "supported",
                        "rationale": "Direct statement",
                    }],
                    "gaps": [],
                }
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            elif role == "Mimir-Result-Checker":
                context = json.loads(prompt.split("INPUTS:\n")[1]) if "INPUTS:\n" in prompt else {}
                checks = [{"id": c["id"], "verdict": "PASS", "issues": []} for c in context.get("candidates", [{"id": "candidate_1"}])]
                data = {"checks": checks}
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            elif role == "Mimir-Synthesizer":
                data = {
                    "answer": "According to [spec], the limit is 100. Also see [unbound_source].",
                    "limitations": [],
                }
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            elif role == "Mimir-Final-Checker":
                data = {"verdict": "PASS", "issues": []}
                return SwarmResult(role, "SUCCESS", data, json.dumps(data))
            return await super().spawn_restricted(prompt, role=role, **options)

    async def run():
        await engine.run_mimir(
            goal="Analyze specification limits",
            mode=mode,
            backend="codex",
            model="fixture",
            effort="low",
            worker_transport="native",
            worker_factory=lambda **kw: MockWorker(),
            state_file=str(state_file),
            output_path=str(output_path),
            skip_web=True,
            memory_mode="off",
            progress_format="events",
        )

        # Inspect generated JSON payload
        payload_file = output_path.with_suffix(".json")
        assert payload_file.exists()
        payload = json.loads(payload_file.read_text(encoding="utf-8"))

        ref_audit = payload["research"]["final_reference_audit"]
        # Abbreviated [spec] was resolved without full-path comparison
        assert ref_audit["missing_supporting_locators"] == []
        # Unbound citation [unbound_source] was caught
        assert "unbound_source" in ref_audit["unbound_references"]
        assert ref_audit["reference_presence_passed"] is False
        assert payload["research"]["coverage"] == "partial"

        # Inspect generated Markdown report
        md_text = output_path.read_text(encoding="utf-8")
        assert "Unbound reference in synthesis text: unbound_source" in md_text
        assert "Final reference audit: **partial**" in md_text
        assert "Independent factual validation: **not performed**" in md_text

    asyncio.run(run())
