"""Sealed engineering comparison; never passes expected answers to students."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import time

from codex_sdk_backend import CodexSdkSwarmBackend
from invocation_broker import InvocationBroker, validate_budget
from optimize_program import load_dataset
from research_program import ResearchContext, ResearchRequest
from source_store import SourceStore, identity


def read_candidate(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("program") != "rlm" or identity({k: v for k, v in value.items() if k != "sha256"}) != value.get("sha256"):
        raise ValueError("Candidate instruction identity is invalid")
    if set(value.get("instructions", {})) != {"action", "extract"}:
        raise ValueError("RLM candidate requires action/extract instructions only")
    return value


async def evaluate(args):
    from dspy_runtime.host import run_program
    dataset = load_dataset(args.dataset)
    candidate = read_candidate(args.candidate) if args.candidate else None
    if candidate and candidate["evaluation"].get("held_out_digest") != identity(dataset["held_out"]):
        raise ValueError("Candidate and sealed dataset identity differ")
    root = Path(args.output).resolve()
    if root.exists():
        raise ValueError("Evaluation output already exists")
    root.parent.mkdir(parents=True, exist_ok=True)
    results = []
    policies = args.policies.split(",") if args.policies else ["native", "dspy", "rlm"] + (["optimized-rlm"] if candidate else [])
    if set(policies) - {"native", "dspy", "rlm", "optimized-rlm"} or ("optimized-rlm" in policies and not candidate):
        raise ValueError("Evaluation policies require supported programs and an optimization candidate")
    for policy in policies:
        native = CodexSdkSwarmBackend(args.model, args.effort, max_concurrency=1)
        broker = InvocationBroker(native, budget=validate_budget({"max_attempts": args.max_attempts,
                                   "max_seconds": args.max_seconds, "max_depth": 0}),
                                   journal=root.with_name(root.stem + f"-{policy}.operations.jsonl"))
        started = time.monotonic()
        group_results = []
        try:
            rows = dataset["held_out"]
            if policy == "native":
                for row in rows:
                    reply = await broker.spawn(row["objective"] + "\nSource evidence:\n" + row["evidence"],
                                               role="fixture-native")
                    try:
                        answer = json.loads(reply.raw_response).get("answer") if reply.status == "SUCCESS" else None
                    except ValueError:
                        answer = None
                    group_results.append({"group": row["group"], "answer": answer})
            else:
                kind = "rlm" if policy == "optimized-rlm" else policy
                context = ResearchContext(broker, SourceStore(), root.parent / (root.stem + f"-{policy}"),
                    {"program": kind, "budget": broker.budget, "sources": [],
                     "instructions": candidate if policy == "optimized-rlm" else None})
                # All answer keys remain exclusively in this parent evaluator.
                public_cases = [{k: v for k, v in row.items() if k != "expected"} for row in rows]
                response, _ = await run_program(ResearchRequest("heldout", "Evaluate sealed cases", "evaluation",
                    args.model, args.effort, None), context, optimize={"kind": "evaluate", "cases": public_cases})
                group_results = response.data["cases"]
            expected = {r["group"]: r["expected"] for r in rows}
            if len(group_results) != len(rows) or {r["group"] for r in group_results} != set(expected):
                raise ValueError("Incomplete held-out case results")
            for result in group_results:
                result["correct"] = result["answer"] == expected[result["group"]]
            result = {"policy": policy, "status": "completed", "cases": group_results,
                      "correct": sum(r["correct"] for r in group_results), "total": len(rows)}
        except Exception as exc:
            result = {"policy": policy, "status": "failed", "error_type": type(exc).__name__}
        finally:
            await broker.aclose()
        result.update(seconds=round(time.monotonic() - started, 2), attempts=len(broker.usage_calls),
                      reported_native_tokens=sum(c.get("tokens_used") or 0 for c in broker.usage_calls))
        results.append(result)
        report = {"version": 1, "metric": "exact-answer-fixture-v1", "dataset_digest": identity(dataset),
                  "candidate_sha256": candidate["sha256"] if candidate else None,
                  "model": args.model, "effort": args.effort, "results": results,
                  "scope": "Synthetic engineering correctness only. Human citation entailment review and operational corpora remain required."}
        root.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "cases"}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--policies", help="Optional comma-separated programs for focused qualification")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="low")
    parser.add_argument("--max-attempts", type=int, default=64)
    parser.add_argument("--max-seconds", type=float, default=1800)
    asyncio.run(evaluate(parser.parse_args()))
