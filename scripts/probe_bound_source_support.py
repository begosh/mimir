"""Small blinded semantic qualification using a frozen current-repository span."""
import asyncio
import json
from pathlib import Path

from post_worker import check_results
from source_store import SourceStore, identity
from retrieved_evidence import capture_result_evidence, inline_spans
from source_support import check_bound_citations
from text_api_backend import TextResponsesBackend


async def main():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "task_graph.py"
    text = path.read_text(encoding="utf-8")
    start = text.index('            word_limit = (t["contract"]')
    end = text.index('            if t.get("contract"):', start)
    excerpt = text[start:end]
    seed = {"answer": "Review word limits", "sources": [{"id": "worker", "locator": str(path),
        "retrieval_type": "local_file", "retrieved_at": "", "support_excerpt": excerpt}],
        "claims": [], "gaps": []}
    result, sources, spans = capture_result_evidence(seed, workspace=root)
    packet = {"sources": sources, "spans": spans}
    packet["hash"] = identity(packet)
    bound = inline_spans(packet, "frozen_dependency_span")
    cases = [
        ("correct", "When t.get('contract') is truthy, its max_output_words sets the limit. Otherwise, in review mode task ID critique has 180 words and other task IDs 250; in other modes the limit is None."),
        ("association", "A supplied task contract sets max_output_words. Without it, review critique has 250 words, other review tasks 180; other modes have no word limit here."),
        ("condition", "A supplied task contract sets max_output_words. Without it, critique always has 180 words and other tasks always have 250, in all modes."),
        ("omission", "Review critique has 180 words; other review tasks have 250 words."),
    ]
    backend = TextResponsesBackend("gpt-6.1-sol", effort="low", max_concurrency=1)
    observations = []
    try:
        # One isolated candidate per call; no expected verdict sent to the checker.
        for case, answer in cases:
            candidate = {**result, "answer": answer, "claims": [{"text": answer,
                "source_ids": [result["sources"][0]["id"]], "support_status": "supported", "rationale": "Conditional expression"}]}
            structural = check_bound_citations(candidate, bound)
            assert structural["verdict"] == "REVIEW"
            context = {"candidates": [{"id": "candidate_1", "contract": {"objective":
                "Describe all branches of this word-limit expression, including supplied contract precedence, review role limits and other-mode behavior.",
                "operation": "research", "inputs": ["frozen source span"], "expected_output": "All branches and conditions",
                "acceptance_check": "Correct values, associations, precedence and mode conditions; preserve all requested branches."},
                "result": candidate, "supplied_sources": bound}]}
            verdict = await asyncio.wait_for(check_results(backend, context), 60)
            observations.append({"case": case, "structural_verdict": structural["verdict"],
                "candidate": candidate, "checks": verdict["checks"]})
        output = {"model": backend.default_model, "effort": backend.default_effort,
                  "source_packet": packet, "observations": observations}
        import time
        target = root / ".mimir" / f"bound-source-support-probe-{time.time_ns()}.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps([{ "case": r["case"], "checks": r["checks"]} for r in observations], indent=2))
        assert [r["checks"][0]["verdict"] for r in observations] == ["PASS", "FAIL", "FAIL", "FAIL"]
    finally:
        await backend.aclose()


if __name__ == "__main__":
    asyncio.run(main())
