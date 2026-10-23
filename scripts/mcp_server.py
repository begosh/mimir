"""Local stdio tool adapter; stdout is exclusively the MCP protocol."""
from __future__ import annotations
import argparse
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from run_manager import RunManager


def create_server(root: Path, manager: RunManager | None = None):
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.types import ToolAnnotations
    except ImportError:
        raise RuntimeError("Install requirements-workers.txt with this Python interpreter to run Mimir MCP.") from None
    runs = manager or RunManager(root)

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield {"runs": runs}
        finally:
            await runs.aclose()

    server = MCPServer("mimir", version="1.0.0", lifespan=lifespan,
                       instructions="Run plan, execute and synthesize in order. Each start returns promptly. Keep host chat quiet: one opening sentence, then coalesce get_status narration and nearby milestones into one short Mimir well/forge/chronicle update about every 45-60 seconds during long work. Do not relay every worker event, replay old updates, narrate routine checks or announce completion before reading artifacts and giving one concise final answer. Tool-call cards are host-rendered. Status waits up to 20 seconds for meaningful changes by default. Advance its cursor and drain pages silently. Keep hashes, JSON, paths and routine usage in artifacts. Successful completion includes cleanup. Preserve material evidence gaps. Workers use their native credentials/tools, not the host's tools.")
    read_only = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
    public_read = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
    local_write = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)

    @server.tool(annotations=local_write)
    async def start_run(goal: str | None = None, backend: str | None = None,
                        model: str | None = None, effort: str | None = None,
                        phase: Literal["plan", "execute", "synthesize"] = "plan",
                        run_id: str | None = None,
                        worker_transport: Literal["native", "cli", "hybrid"] | None = None,
                        worker_timeout: float | None = None, max_concurrency: int | None = None,
                        skip_web: bool = False, search_query: str | None = None,
                        enable_jev: bool | None = None,
                        mode: Literal["single", "review", "swarm"] | None = None,
                        max_tasks: int | None = None,
                        memory_mode: Literal["off", "read", "write"] | None = None,
                        memory_path: str | None = None,
                        max_context_chars: int | None = None,
                        research_program: Literal["native", "dspy", "rlm"] | None = None,
                        research_budget: dict | None = None, source_manifest: str | None = None,
                        program_manifest: str | None = None, task_brief: dict | None = None,
                        recursive_plan: bool | None = None, planning_budget: dict | None = None,
                        max_depth: int = 2) -> dict:
        """Interpret and plan before worker retrieval; no preliminary search. Supply a compact task_brief with outcome, constraints, components, evidence_needs and missing_information. Resume the same ID; no model fallback."""
        return await runs.start(goal=goal, backend=backend, model=model, effort=effort,
                                phase=phase, run_id=run_id, worker_transport=worker_transport,
                                worker_timeout=worker_timeout, max_concurrency=max_concurrency,
                                skip_web=skip_web, search_query=search_query, enable_jev=enable_jev,
                                mode=mode, max_tasks=max_tasks, memory_mode=memory_mode,
                                memory_path=memory_path, max_context_chars=max_context_chars,
                                research_program=research_program, research_budget=research_budget,
                                source_manifest=source_manifest, program_manifest=program_manifest,
                                task_brief=task_brief, recursive_plan=recursive_plan,
                                planning_budget=planning_budget, max_depth=max_depth)

    @server.tool(annotations=public_read)
    async def get_diagnostics(backend: str = "codex", model: str | None = None,
                              effort: str | None = None, check_search: bool = False) -> dict:
        """Read setup without inference or secrets. Opt into bounded public search probes with check_search=true; report usability and suggest an MCP if the scout fails."""
        from diagnostics import collect_diagnostics
        return await asyncio.to_thread(collect_diagnostics, backend, model, effort,
                                       run_root=runs.root, check_search=check_search)

    @server.tool(annotations=read_only)
    async def get_status(run_id: str, after_sequence: int = 0, limit: int = 50,
                         wait_seconds: float = 20, include_events: bool = False) -> dict:
        """Hear Mimir's observed progress. Coalesce nearby updates into brief milestone narration; do not relay every poll/event. Compact by default; include_events exposes diagnostics. Continue next_sequence while has_more. Waiting is not a finding."""
        return await runs.progress(run_id, after_sequence, limit,
                                   wait_seconds=wait_seconds, include_events=include_events)

    @server.tool(annotations=local_write)
    async def cancel_run(run_id: str) -> dict:
        """Cancel this host's owned phase and await worker cleanup; retain successful checkpoints. Other active hosts retain ownership."""
        return await runs.cancel(run_id)

    @server.tool(annotations=read_only)
    async def get_result(run_id: str, artifact: Literal["report", "sidecar"] = "report",
                         offset: int = 0, limit: int = 32000) -> dict:
        """Read a bounded chunk of a successfully synthesized report or JSON sidecar. Follow next_offset while has_more."""
        return runs.result(run_id, artifact, offset, limit)

    return server


def main():
    parser = argparse.ArgumentParser(description="Mimir local stdio MCP")
    parser.add_argument("--run-root", type=Path, default=None,
                        help="Absolute durable run directory; use the same root across hosts for recovery")
    parser.add_argument("--workspace", type=Path, default=None, help="Native project working directory, independent of host MCP cwd support")
    args = parser.parse_args()
    if args.workspace is not None:
        import os
        os.chdir(args.workspace.resolve(strict=True))
    # Protocol uses UTF-8; importing the engine never reconfigures global streams.
    try:
        root = args.run_root or Path.cwd() / ".mimir/runs"
        create_server(root.resolve()).run(transport="stdio")
    except (ImportError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
