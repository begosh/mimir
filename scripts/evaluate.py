"""Run repeatable policy comparisons and record conservative answer metrics.

Reference requirements are benchmark expectations, not independent entailment
judgments. Reports remain available for blinded human assessment.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import statistics
import time
from engine import run_mimir, _write_artifact


def score_report(case: dict, report: dict) -> dict:
    answer = report["hardened_solution"]
    research = report["research"]
    cited = {s["locator"] for s in research["sources"]}
    expected = case.get("required_locators", [])
    markers = case.get("required_answer_markers", [])
    return {"required_locator_hits": sum(locator in cited for locator in expected),
            "required_locator_count": len(expected),
            "answer_marker_hits": sum(marker in answer for marker in markers),
            "answer_marker_count": len(markers),
            "reported_unsupported_claims": sum(c["support_status"] == "unsupported" for c in research["claims"]),
            "reported_gap_count": len(research["gaps"]),
            "record_coverage": research["coverage"],
            "citation_entailment": "requires independent review",
            "unknown_unrecorded_claims": "not measured"}


async def evaluate(cases: list[dict], out: Path, *, backend: str, model: str,
                   effort: str, modes: list[str], repeats: int, worker_timeout: float) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for repeat in range(repeats):
        # Alternate policy order to reduce a fixed warmup/order advantage.
        order = modes if repeat % 2 == 0 else list(reversed(modes))
        for case in cases:
            if not isinstance(case.get("goal"), str) or not case["goal"].strip():
                raise ValueError("Each evaluation case requires a nonempty goal.")
            identity = hashlib.sha256(case["goal"].encode()).hexdigest()[:12]
            for mode in order:
                directory = out / f"{identity}-{repeat}-{mode}"
                directory.mkdir()
                started = time.monotonic()
                row = {"case_id": case.get("id", identity), "goal_sha256": identity,
                       "mode": mode, "repeat": repeat, "report_path": str((directory / "report.md").resolve())}
                try:
                    await run_mimir(goal=case["goal"], backend=backend, model=model, effort=effort,
                                    worker_transport="native", phase="all", skip_web=True,
                                    mode=mode, max_tasks=4, memory_mode="off", enable_jev=False,
                                    worker_timeout=worker_timeout, max_concurrency=2,
                                    state_file=str(directory / "checkpoint.json"),
                                    output_path=str(directory / "report.md"), progress_format="events")
                    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
                    row.update(status="completed", usage=report["usage"], metrics=score_report(case, report))
                except Exception as exc:
                    from backend import worker_diagnostic
                    row.update(status="failed", error=worker_diagnostic("Evaluation", str(exc), error=exc))
                row["wall_seconds"] = round(time.monotonic() - started, 3)
                results.append(row)
                _write_artifact(out / "results.json", json.dumps(results, indent=2))
    summary = {"backend": backend, "model": model, "effort": effort, "runs": results,
               "budget_qualification": "Same model, context admission and worker deadlines; total token/dollar ceilings are not enforced.",
               "quality_qualification": "Locator and marker presence only; no automatic entailment, exhaustive coverage or superiority claim.",
               "policies": {mode: {"completed": sum(r["status"] == "completed" for r in results if r["mode"] == mode),
                                   "median_wall_seconds": statistics.median(r["wall_seconds"] for r in results if r["mode"] == mode)} for mode in modes}}
    _write_artifact(out / "summary.json", json.dumps(summary, indent=2))
    return summary


def main():
    p = argparse.ArgumentParser(description="Evaluate explicit local primary-source cases through the same engine")
    p.add_argument("--cases", type=Path, required=True, help="JSON list of goal/required_locators/required_answer_markers cases")
    p.add_argument("--output", type=Path, required=True, help="New directory for separate run artifacts")
    p.add_argument("--backend", required=True); p.add_argument("--model", required=True)
    p.add_argument("--effort", default="low"); p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--modes", nargs="+", choices=["single", "review", "swarm"], default=["single", "review"])
    p.add_argument("--worker-timeout", type=float, default=300)
    args = p.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases or not 1 <= args.repeats <= 10:
        p.error("Provide nonempty case list and 1–10 repetitions")
    asyncio.run(evaluate(cases,args.output,backend=args.backend,model=args.model,effort=args.effort,
                         modes=list(dict.fromkeys(args.modes)),repeats=args.repeats,worker_timeout=args.worker_timeout))


if __name__ == "__main__":
    main()
