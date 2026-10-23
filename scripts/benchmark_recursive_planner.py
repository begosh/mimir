"""Compare recursive decomposition efforts using the same saved interpretation.

Planning only: no source retrieval, research workers, synthesis, or saved profile changes.
Each effort uses the production native adapter, admission ledger, and planner.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time
from types import SimpleNamespace

from backend import create_swarm_backend
from engine import _write_artifact
from invocation_broker import InvocationBroker
from recursive_planner import RecursivePlanner
from source_store import identity


class RootReplayBroker(InvocationBroker):
    """Reuse one recorded root completion only after its full input identity matches."""
    def __init__(self, native, recorded, **kwargs):
        self.recorded_root = recorded["planning"]["calls"][0]
        self.root_usage = recorded["usage_calls"][0]
        self.replay_pending = True
        super().__init__(native, calls=[self.root_usage], **kwargs)

    async def spawn_restricted(self, prompt, role="Micro-Worker", **options):
        if self.replay_pending:
            if identity({"prompt": prompt, "options": options}) != self.root_usage["input_hash"]:
                raise ValueError("Recorded root input differs; refusing replay")
            self.replay_pending = False
            raw = self.recorded_root["raw_response"]
            return SimpleNamespace(status="SUCCESS", data=json.loads(raw), raw_response=raw,
                                   tokens_used=self.root_usage["tokens_used"], timing=self.recorded_root["timing"])
        return await super().spawn_restricted(prompt, role=role, **options)


async def compare(args):
    saved = json.loads(Path(args.interpretation_file).read_text(encoding="utf-8-sig"))
    source = saved.get("planning", saved)
    goal, brief = source["original_goal"], source["interpretation"]
    domain_rules = Path(args.domain_rules_file).read_text(encoding="utf-8-sig")
    target = Path(args.output_dir).resolve()
    target.mkdir(parents=True, exist_ok=False)
    summaries = []
    metadata = {"goal": goal, "interpretation": brief, "domain_rules": domain_rules,
                "model": args.model, "efforts": args.efforts,
                "limits": {"max_calls": 8, "max_seconds": 120, "max_nodes": 32,
                           "max_leaves": 12, "max_depth": 3},
                "interpretation_reused": True, "research_executed": False,
                "planner_source_sha256": identity(Path(__file__).with_name("recursive_planner.py").read_text(encoding="utf-8"))}
    _write_artifact(target / "comparison.json", json.dumps({**metadata, "results": summaries}, indent=2))
    for effort in args.efforts:
        run_dir = target / effort
        run_dir.mkdir()
        native = create_swarm_backend("codex", args.model, max_concurrency=1,
                                      effort=effort, timeout_seconds=180, worker_transport="native")
        root_seconds = 0
        if args.reuse_root_from:
            recorded = json.loads((Path(args.reuse_root_from) / effort / "planning.json").read_text(encoding="utf-8"))
            broker = RootReplayBroker(native, recorded, journal=run_dir / "operations.jsonl")
            root_seconds = recorded["planning"]["calls"][0]["duration_seconds"]
        else:
            broker = InvocationBroker(native, journal=run_dir / "operations.jsonl")
        seen = set()
        deadline_adjusted = False

        def snapshot(trace):
            nonlocal deadline_adjusted
            if root_seconds and trace["calls"] and not deadline_adjusted:
                planner.deadline -= root_seconds
                deadline_adjusted = True
            if root_seconds and trace["calls"]:
                trace["calls"][0]["replayed"] = True
                trace["calls"][0]["original_duration_seconds"] = root_seconds
            _write_artifact(run_dir / "planning.json", json.dumps(
                {"planning": trace, "usage_calls": broker.usage_calls}, indent=2, ensure_ascii=False))
            for index, call in enumerate(trace["calls"], 1):
                _write_artifact(run_dir / f"prompt-{index}.txt", call["prompt"])
                key = (index, call["status"])
                if key not in seen:
                    seen.add(key)
                    print(json.dumps({"effort": effort, "call": index, "parent": call["parent"],
                                      "status": call["status"], "seconds": call.get("duration_seconds")}), flush=True)

        planner = RecursivePlanner(broker, max_leaves=12, max_depth=3, domain_rules=domain_rules,
                                   on_checkpoint=snapshot)
        started = time.monotonic()
        error = None
        print(json.dumps({"effort": effort, "status": "starting"}), flush=True)
        try:
            await planner.plan(goal, brief)
        except (ValueError, RuntimeError, TimeoutError) as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            await broker.aclose()
            snapshot(planner.state)
        usage = broker.usage_calls
        summary = {"effort": effort, "status": planner.state["status"], "error": error,
                   "duration_seconds": round(time.monotonic() - started + root_seconds, 3),
                   "reused_root": bool(root_seconds),
                   "calls": len(usage), "leaves": len(planner.leaves),
                   "reported_tokens": sum(c.get("tokens_used") or 0 for c in usage),
                   "usage_known_calls": sum(c.get("tokens_used") is not None for c in usage),
                   "input_tokens": sum((c.get("usage_details") or {}).get("input_tokens") or 0 for c in usage),
                   "cached_input_tokens": sum((c.get("usage_details") or {}).get("cached_input_tokens") or 0 for c in usage),
                   "output_tokens": sum((c.get("usage_details") or {}).get("output_tokens") or 0 for c in usage),
                   "reasoning_output_tokens": sum((c.get("usage_details") or {}).get("reasoning_output_tokens") or 0 for c in usage),
                   "root_prompt_sha256": identity(planner.state["calls"][0]["prompt"]) if planner.state["calls"] else None,
                   "leaf_objectives": [leaf["objective"] for leaf in planner.leaves],
                   "blockers": sorted({value for leaf in planner.leaves for value in leaf["blocked_by"]})}
        summaries.append(summary)
        _write_artifact(target / "comparison.json", json.dumps({**metadata, "results": summaries}, indent=2, ensure_ascii=False))
        print(json.dumps(summary, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interpretation-file", required=True)
    parser.add_argument("--domain-rules-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--reuse-root-from", help="Recorded comparison directory; reuse identical successful root calls")
    parser.add_argument("--efforts", nargs="+", choices=["low", "medium", "high"], default=["low", "medium", "high"])
    asyncio.run(compare(parser.parse_args()))
