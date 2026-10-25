"""Terminal adapter for the shared Mimir engine."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from engine import run_mimir, create_swarm_backend
from mimir_config import configure, config_status, resolve_execution

def main():
    parser = argparse.ArgumentParser(description="M Í M I R // Omniscient Oracle & Autonomous Swarm")
    parser.add_argument("goal", nargs="?", type=str, help="Det komplexa målet, forskningsfrågan eller strategin.")
    parser.add_argument("--goal-file", type=str, help="UTF-8 file containing the objective and required context")
    parser.add_argument("--task-brief", type=json.loads, help="Compact JSON interpretation: outcome, constraints, components, evidence_needs, missing_information")
    parser.add_argument("--recursive-plan", action="store_true", default=None, help="Interpret then recursively split into bounded atomic tasks; requires swarm mode")
    parser.add_argument("--planning-budget", type=json.loads, help="JSON planning limits: max_calls, max_seconds, max_nodes")
    parser.add_argument("--phase", "--stage", choices=["all", "plan", "execute", "synthesize"], default="all",
                        help="Execute a discrete phase of Mimir or the entire pipeline (plan | execute | synthesize | all)")
    parser.add_argument("--state-file", type=str, default="artifacts/mimir_state.json",
                        help="State file path for phased execution (default: artifacts/mimir_state.json)")
    parser.add_argument("--check", action="store_true", help="Check CLI and worker settings without a model call")
    parser.add_argument("--diagnostics", action="store_true", help="Read operating paths, dependency and credential presence without inference")
    parser.add_argument("--doctor", action="store_true", help="Diagnose setup and probe public search with the native scout and curl; no model calls")
    parser.add_argument("--mode", choices=["single", "review", "swarm"], default=None, help="single: one worker; review: two specialists and critic; swarm: bounded model plan")
    parser.add_argument("--max-tasks", type=int, default=None, help="Enforced task limit independent of concurrency (default 4)")
    parser.add_argument("--memory", choices=["off", "read", "write"], default=None, help="Default read; write records candidates without promoting them")
    parser.add_argument("--memory-path", default=None, help="Explicit curated learning path; default project .mimir/LEARNINGS.md")
    parser.add_argument("--max-context-chars", type=int, default=None, help="Context admission limit; no silent evidence truncation (default 120000)")
    parser.add_argument("--research-program", choices=["native", "dspy", "rlm"], default=None)
    parser.add_argument("--source-manifest", help="Explicit JSON manifest of local UTF-8 files or allowlisted HTTPS sources")
    parser.add_argument("--program-manifest", help="Reviewed data-only optimized instruction manifest")
    parser.add_argument("--research-budget", type=json.loads, help="Fixed whole-run limits (default: 64 attempts, 1800 elapsed seconds); reported-token threshold may overshoot in-flight work")
    setup = parser.add_mutually_exclusive_group()
    setup.add_argument("--config-status", action="store_true", help="Show saved project profile and available CLIs without a model call")
    setup.add_argument("--configure", action="store_true", help="Save an explicitly agreed backend/model/effort in .mimir/config.json")
    parser.add_argument("--host", choices=["agy", "codex", "claude", "opencode"],
                        help="Hosting CLI suggestion for --config-status; never automatically saves a choice")
    parser.add_argument("--host-model", help="Known host model for a first-use worker suggestion; does not select or save it")
    parser.add_argument("--output", "-o", type=str, default=None, help="Report path; resumes the planned path when omitted")
    parser.add_argument("--backend", "-b", type=str, default=None, choices=["auto", "agy", "codex", "claude", "opencode", "responses", "openai", "anthropic", "ollama"], help="Tool runtime or direct Responses backend; otherwise use saved setup")
    parser.add_argument("--worker-transport", choices=["native", "cli", "hybrid"], default=None,
                        help="Default hybrid for tool runtimes: direct text API plus tools; native/cli are explicit legacy overrides")
    parser.add_argument("--effort", default=None, help="Worker reasoning effort (default low); OpenCode provider variant or none")
    parser.add_argument("--worker-timeout", type=float, default=None, help="Worker timeout; default 180 or persisted phase setting")
    parser.add_argument("--concurrency", type=int, default=None, help="Worker concurrency; default 4 or persisted phase setting")
    parser.add_argument("--progress", choices=["terminal", "jsonl"], default="terminal",
                        help="Rich terminal display or flushed JSONL progress events for a hosting harness")
    parser.add_argument("--model", "-m", type=str, default=None, help="Modell för mikromodeller (standard: anpassas efter backend)")
    parser.add_argument("--skip-web", action="store_true", help="Legacy compatibility: omit the optional search-query hint; planning never searches")
    parser.add_argument("--search-query", help="Optional public-query hint for workers to assess after interpretation; no automatic search")
    parser.add_argument("--depth", type=int, default=2, help="Maximum recursive split depth with --recursive-plan (1-4)")
    parser.add_argument("--sources", "-s", type=str, default=None, help="Kommaseparerad lista med specifika källor/domäner")
    jev = parser.add_mutually_exclusive_group()
    jev.add_argument("--jev", action="store_true", default=None, help="Opt into heuristic pruning")
    jev.add_argument("--no-jev", action="store_true", help="Disable heuristic pruning")

    args = parser.parse_args()
    if args.diagnostics or args.doctor:
        from diagnostics import collect_diagnostics
        print(json.dumps(collect_diagnostics(args.backend or "codex", args.model, args.effort,
                                             memory_path=args.memory_path, memory_mode=args.memory or "read",
                                             worker_transport=args.worker_transport,
                                             check_search=args.doctor), indent=2))
        return
    if args.config_status or args.configure:
        if args.goal or args.goal_file or args.check:
            parser.error("Setup commands cannot be combined with an objective or --check")
        try:
            if args.configure:
                if not args.backend or args.backend == "auto":
                    parser.error("--configure requires an explicit --backend")
                configure(args.backend, args.model, args.effort)
            print(json.dumps(config_status(args.host, host_model=args.host_model), ensure_ascii=False, indent=2))
            return
        except (OSError, ValueError) as exc:
            parser.exit(1, f"Mimir configuration failed: {exc}\n")
    if args.concurrency is not None and args.concurrency < 1:
        parser.error("--concurrency must be positive")
    if args.check:
        try:
            backend, model, effort = resolve_execution(args.backend, args.model, args.effort)
            swarm = create_swarm_backend(backend, model, args.concurrency or 4, effort, args.worker_timeout or 180, worker_transport=args.worker_transport)
            if not hasattr(swarm, "check_cli"):
                parser.error("--check validates CLI backends only")
            async def preflight():
                try:
                    return await swarm.check_cli()
                finally:
                    await swarm.aclose()
            print(json.dumps(asyncio.run(preflight()), ensure_ascii=False, indent=2))
            return
        except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as exc:
            parser.exit(1, f"Preflight failed: {exc}\n")
    if args.goal and args.goal_file:
        parser.error("Use a positional goal or --goal-file, not both")

    goal = None
    if args.goal_file:
        try:
            goal = Path(args.goal_file).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            parser.error(f"Cannot read objective file: {exc}")
    elif args.goal:
        goal = args.goal

    if not goal and args.phase in ("all", "plan"):
        parser.error("Provide a goal or --goal-file")

    source_list = [s.strip() for s in args.sources.split(",")] if args.sources else None

    try:
        asyncio.run(run_mimir(
            goal=goal,
            output_path=args.output,
            backend=args.backend,
            model=args.model,
            skip_web=args.skip_web,
            max_depth=args.depth,
            sources=source_list,
            enable_jev=False if args.no_jev else args.jev,
            effort=args.effort,
            worker_timeout=args.worker_timeout,
            max_concurrency=args.concurrency,
            progress_format=args.progress,
            phase=args.phase,
            state_file=args.state_file,
            search_query=args.search_query,
            worker_transport=args.worker_transport,
            mode=args.mode, max_tasks=args.max_tasks, memory_mode=args.memory,
            memory_path=args.memory_path, max_context_chars=args.max_context_chars,
            research_program=args.research_program, research_budget=args.research_budget,
            source_manifest=args.source_manifest, program_manifest=args.program_manifest,
            task_brief=args.task_brief,
            recursive_plan=args.recursive_plan, planning_budget=args.planning_budget,
        ))
    except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as exc:
        parser.exit(1, f"Mimir failed: {exc}\n")
