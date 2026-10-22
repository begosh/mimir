"""Explicit GEPA training job using existing native credentials/model routing."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from codex_sdk_backend import CodexSdkSwarmBackend
from invocation_broker import InvocationBroker, validate_budget
from research_program import ResearchRequest, ResearchContext
from source_store import SourceStore, identity


def load_dataset(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if set(data) != {"train", "dev", "held_out"}:
        raise ValueError("Dataset requires train, dev, held_out splits")
    groups = set()
    for split, rows in data.items():
        if not isinstance(rows, list) or not rows:
            raise ValueError("Every dataset split must be nonempty")
        current = set()
        for row in rows:
            if set(row) != {"group", "objective", "evidence", "expected"} or any(not isinstance(v, str) or not v for v in row.values()):
                raise ValueError("Invalid dataset example")
            current.add(row["group"])
        if groups & current:
            raise ValueError("Source/topic group leakage across dataset splits")
        groups.update(current)
    return data


async def train(args):
    from dspy_runtime.host import run_program
    data = load_dataset(args.dataset)
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError("Candidate output exists; choose a new output path")
    budget = validate_budget({"max_attempts": args.max_attempts, "max_seconds": args.max_seconds,
                              "max_depth": 0})
    native = CodexSdkSwarmBackend(args.model, args.effort, max_concurrency=1)
    broker = InvocationBroker(native, budget=budget, journal=output.with_suffix(".operations.jsonl"))
    context = ResearchContext(broker, SourceStore(), output.parent / (output.stem + "-research"),
                              {"program": args.program, "budget": budget, "sources": []})
    try:
        # Held-out content is deliberately absent from the optimization process.
        result, _ = await run_program(ResearchRequest("optimization", "Optimize research instructions", "GEPA-training",
                                                     args.model, args.effort, None), context,
                                      optimize={"program": args.program, "train": data["train"], "dev": data["dev"],
                                                "max_metric_calls": args.max_metric_calls})
        candidate = result.data
        candidate["evaluation"]["held_out_digest"] = identity(data["held_out"])
        candidate["sha256"] = identity({k: v for k, v in candidate.items() if k != "sha256"})
        output.write_text(json.dumps(candidate, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"candidate": str(output), "reviewed": False, "native_attempts": len(broker.usage_calls)}))
    finally:
        await broker.aclose()


def main():
    parser = argparse.ArgumentParser(description="Explicit upstream DSPy GEPA instruction training")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--program", choices=["dspy", "rlm"], default="rlm")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="low")
    parser.add_argument("--max-attempts", type=int, default=64)
    parser.add_argument("--max-seconds", type=float, default=1800)
    parser.add_argument("--max-metric-calls", type=int, default=24)
    args = parser.parse_args()
    asyncio.run(train(args))


if __name__ == "__main__":
    main()
