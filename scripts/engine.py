"""
scripts/mimir.py
M Í M I R // The Omniscient Oracle & Autonomous Recursive Multi-Agent Swarm.
Keeper of the Well of Wisdom (Mimisbrunnr).
Combines public research scouting, atomic DAG decomposition,
JEV System-1 decision gating, EvidenceContracts, and cumulative long-term memory.
Worker prompts and generated reports currently use English.
Supports both single-run pipeline and discrete phased execution (--phase plan|execute|synthesize|all).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
import math
import os
import re
import sys
import time
import tempfile
from contextlib import suppress, contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Ensure scripts dir is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from backend import BaseSwarmBackend, SwarmResult, SwarmTask, create_swarm_backend, has_worker_result, worker_diagnostic
from mimir_config import is_english_text, ConfigurationRequired, configure, config_status, resolve_execution
from gepa_optimizer import GepaOptimizer
from jarvis_memory import JarvisMemory
from jev_gate import JevDecisionGate
from research_scout import IntelligenceBrief, ResearchScout
from task_graph import Blackboard, RecursiveDecomposer, TaskGraph, TaskNode, TaskStatus

# Rich UI imports
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.tree import Tree
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


ASCII_LOGO = r"""  __  __ _____ __  __ _____ _____
 |  \/  |_   _|  \/  |_   _|  __ \
 | \  / | | | | \  / | | | | |__) |
 | |\/| | | | | |\/| | | | |  _  /
 |_|  |_|_|___|_|  |_|_|___|_| \_\
 [ WELL OF WISDOM :: DIALECTICAL REASONING ENGINE ]"""


class MimirConsole:
    def __init__(self, is_en: bool = True, progress_format: str = "terminal", event_sink: Optional[Callable] = None):
        self.console = Console(highlight=False) if HAS_RICH and progress_format == "terminal" else None
        self.is_en = is_en
        self.progress_format = progress_format
        self.event_sink = event_sink
        self.started_at = time.monotonic()
        self.sequence = 0
        self.phase = None
        self.activity = "Worker setup"
        self.submitted_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.completion = None

    async def heartbeat(self, interval_seconds: float = 15):
        """Process liveness while awaiting work; never a claim of new findings."""
        while True:
            await asyncio.sleep(interval_seconds)
            self.notice("run_waiting", f"Mímir keeps watch: waiting in {self.activity}.",
                        phase=self.phase, activity=self.activity,
                        submitted_tasks=self.submitted_tasks,
                        completed_tasks=self.completed_tasks, failed_tasks=self.failed_tasks)

    def _flush(self):
        if self.console and hasattr(self.console.file, "flush"):
            try:
                self.console.file.flush()
            except Exception:
                pass
        try:
            sys.stdout.flush()
        except Exception:
            pass

    def emit(self, event: str, **data: Any):
        """Public execution activity and final-output excerpts, never model reasoning."""
        if self.progress_format in ("jsonl", "events"):
            self.sequence += 1
            record = {"schema_version": 1, "sequence": self.sequence, "event": event,
                      "elapsed_seconds": round(time.monotonic() - self.started_at, 3), **data}
            if self.event_sink is not None:
                self.event_sink(record)
            if self.progress_format == "jsonl":
                sys.stdout.write(json.dumps(record, ensure_ascii=True) + "\n")
                sys.stdout.flush()

    def notice(self, event: str, message: str, **data: Any):
        self.emit(event, message=message, **data)
        if self.progress_format == "terminal":
            if self.console:
                self.console.print(message)
                self._flush()
            else:
                print(message, flush=True)

    def print_banner(self, goal: str, model: str, backend_name: str, memory_stats: Optional[Dict[str, Any]] = None,
                     web_enabled: bool = True, jev_enabled: bool = True, phase_mode: str = "all"):
        entries = memory_stats.get('entries', 0) if memory_stats else 0
        self.emit("run_started", backend=backend_name, model=model, memory_entries=entries,
                  web_enabled=web_enabled, jev_enabled=jev_enabled, phase=phase_mode)
        if self.progress_format in ("jsonl", "events"):
            return
        if self.is_en:
            title = "[bold gold1]M Í M I R // Keeper of Wisdom & Autonomous Swarm[/bold gold1]"
            sub = '[italic dim]"Drink from the Well. Truth distilled from the noise of the cosmos."[/italic dim]'
            mem_text = f"Chronicle: {entries} entries"
            lbl_goal = "OBJECTIVE"
        else:
            title = "[bold gold1]M Í M I R // Vishetens Väktare & Autonom Svärm[/bold gold1]"
            sub = '[italic dim]"Drink from the Well of Wisdom. Truth distilled from cosmic noise."[/italic dim]'
            mem_text = f"Minne: {entries} lärdomar"
            lbl_goal = "UPPDRAG"

        banner_text = f"{title}\n{sub}\n\n[bold white]{lbl_goal}:[/bold white] [green]{goal}[/green]\n"
        banner_text += f"[dim]Motor: {backend_name} ({model}) | {mem_text} | Web: {'on' if web_enabled else 'off'} | JEV: {'on' if jev_enabled else 'off'} | Phase: {phase_mode}[/dim]"

        if self.console:
            self.console.print(f"[bold cyan]{ASCII_LOGO}[/bold cyan]")
            self.console.print(Panel(banner_text, border_style="gold1", title="[bold gold1]MIMISBRUNNR ONLINE[/bold gold1]"))
            self._flush()
        else:
            print(f"=== M Í M I R ===\n{goal}\nBackend: {backend_name} ({model}) | {mem_text} | Phase: {phase_mode}\n", flush=True)

    def print_phase(self, phase_num: int, title: str, title_en: Optional[str] = None):
        final_title = title_en or title
        self.phase = phase_num
        self.activity = final_title
        self.emit("phase_started", phase=phase_num, title=final_title)
        if self.progress_format in ("jsonl", "events"):
            return
        runes = {1: 'ᚠ', 2: 'ᚢ', 3: 'ᚦ', 4: 'ᚨ', 5: 'ᚱ'}
        rune = runes.get(phase_num, 'ᛟ')
        if self.console:
            self.console.print(f"\n[bold gold1]{rune} Phase {phase_num} // {final_title.upper()}[/bold gold1]")
            self._flush()
        else:
            print(f"\n--- PHASE {phase_num}: {final_title} ---", flush=True)

    def display_intel(self, brief: IntelligenceBrief):
        self.emit("research_completed", source_count=len(brief.items), sources=[
            {"title": item.title, "channel": item.channel, "url": item.url, "retrieval_type": item.retrieval_type}
            for item in brief.items[:6]
        ], retrieval_gaps=brief.retrieval_gaps)
        if self.progress_format in ("jsonl", "events"):
            return
        if not self.console:
            print(brief.to_compact_markdown(), flush=True)
            return

        title = "Mímir's Omni-Channel Scryer (Inhämtad Data)" if not self.is_en else "Mímir's Omni-Channel Scryer (Discovered Intelligence)"
        table = Table(title=f"[bold blue]{title}[/bold blue]", border_style="blue")
        table.add_column("Channel / Domain", style="cyan", width=24)
        table.add_column("Finding / Title", style="bold white", width=42)
        table.add_column("Source / Meta", style="green", width=20)

        for it in brief.items[:6]:
            table.add_row(it.channel[:22], it.title[:40] + "...", it.author_or_meta[:18])

        self.console.print(table)
        for gap in brief.retrieval_gaps:
            self.console.print(f"Retrieval gap: {gap}", markup=False)
        self._flush()

    def display_dag(self, graph: TaskGraph):
        self.emit("graph_ready", tasks=[
            {"id": n.id, "role": n.role, "title": n.title,
             "dependencies": sorted(n.dependencies), "jev_score": n.jev_score,
             "jev_status": getattr(n, "jev_status", "not_evaluated")}
            for n in graph.nodes.values()
        ], tiers=[[n.id for n in tier] for tier in graph.get_execution_tiers()])
        if self.progress_format in ("jsonl", "events"):
            return
        if not self.console:
            print(f"Task Graph with {len(graph.nodes)} nodes:", flush=True)
            for n in graph.nodes.values():
                print(f" - [{n.id}] {n.role}: {n.title} (JEV: {getattr(n, 'jev_status', 'not_evaluated')})", flush=True)
            return

        label = "Mímir's Task & Rune DAG"
        tree = Tree(f"[bold cyan]{label}[/bold cyan] ({len(graph.nodes)} tasks)")
        tiers = graph.get_execution_tiers()
        for idx, tier in enumerate(tiers):
            tier_lbl = f"Execution Tier #{idx+1}"
            tier_branch = tree.add(f"[bold yellow]{tier_lbl}[/bold yellow] ({len(tier)} noder)")
            for node in tier:
                deps_str = f" [dim](beror på: {', '.join(node.dependencies)})[/dim]" if node.dependencies else ""
                jev_val = getattr(node, "jev_score", 1.0)
                status = getattr(node, "jev_status", "not_evaluated")
                jev_str = f" [bold yellow]JEV:{jev_val:.2f}[/bold yellow]" if status == "scored" else f" [dim]JEV:{status}[/dim]"
                tier_branch.add(f"[bold white]{node.id}[/bold white] - [green]{node.role}[/green]: {node.title}{deps_str}{jev_str}")

        self.console.print(tree)
        self._flush()

    def display_agent_done(self, node: TaskNode, duration: float, evidence_hash: str = ""):
        if self.progress_format in ("jsonl", "events"):
            return
        hash_tag = f" [dim cyan]sha256:{evidence_hash}[/dim cyan]" if evidence_hash else ""
        if self.console:
            self.console.print(f"  [green][OK][/green] [[cyan]{node.id}[/cyan]] [bold]{node.role}[/bold]: {node.title} [dim]({duration:.1f}s)[/dim]{hash_tag}")
            self._flush()
        else:
            print(f"  [OK] {node.id} {node.role}: {node.title} ({duration:.1f}s){hash_tag}", flush=True)

    def display_agent_submitted(self, node: TaskNode):
        self.submitted_tasks += 1
        self.emit("task_submitted", node_id=node.id, role=node.role, title=node.title)
        if self.progress_format == "terminal":
            if self.console:
                self.console.print(f"  [cyan][QUEUED][/cyan] [{node.id}] {node.role}: {node.title}")
                self._flush()
            else:
                print(f"  [QUEUED] [{node.id}] {node.role}: {node.title}", flush=True)


@contextmanager
def _checkpoint_lock(state_file: str):
    """One phase owns a checkpoint at a time, including its model calls."""
    from run_locks import ownership
    target = Path(state_file).resolve()
    with ownership(target.with_name(target.name + ".lock")):
        yield


def _write_artifact(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        # Windows scanners can temporarily open a just-written destination
        # without delete sharing. Retry only that transient replace failure.
        for attempt in range(5):
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _save_state(state: Dict[str, Any], state_file: str) -> None:
    """Replace a complete checkpoint atomically, keeping the previous one on error."""
    target = Path(state_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: value for key, value in state.items() if key not in {"task_graph_obj", "blackboard"}}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
        # Windows scanners can temporarily open a just-written destination
        # without delete sharing. Retry only that transient replace failure.
        for attempt in range(5):
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _load_state(state_file: str, phase: str) -> Dict[str, Any]:
    target = Path(state_file)
    if not target.is_file():
        raise FileNotFoundError(f"State file not found at {target}. Run --phase plan first.")
    state = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1:
        raise ValueError("Unsupported Mimir state version.")
    if not isinstance(state.get("goal"), str) or not state["goal"].strip():
        raise ValueError("State requires a nonempty objective.")
    expected = {"planned", "executing"} if phase == "execute" else {"executed", "synthesized"}
    if state.get("phase") not in expected:
        raise ValueError(f"Cannot {phase} state in phase {state.get('phase')!r}.")
    graph = TaskGraph.from_dict(state.get("graph", {}))
    valid, message = graph.validate_acyclic_and_integrity()
    if not graph.nodes or not valid:
        raise ValueError(f"Invalid persisted task graph: {message}")
    if phase == "execute":
        retained = state.get("completed_data", {})
        if not isinstance(retained, dict) or not set(retained).issubset(graph.nodes):
            raise ValueError("Invalid retained task results.")
        for node in graph.nodes.values():
            if node.status == TaskStatus.COMPLETED and node.id not in retained:
                raise ValueError("Completed task is missing its retained result.")
            if node.status != TaskStatus.COMPLETED:
                node.status = TaskStatus.PENDING
                node.error_trace = None
        state["graph"] = graph.to_dict()
    if phase == "synthesize":
        results = state.get("completed_data")
        if not isinstance(results, dict) or set(results) != set(graph.nodes):
            raise ValueError("Synthesis requires results for every planned task.")
        if any(not isinstance(result, dict) or "result" not in result for result in results.values()):
            raise ValueError("Invalid persisted task results.")
        if any(not has_worker_result(result["result"]) for result in results.values()):
            raise ValueError("Synthesis requires usable output for every planned task.")
        if any(node.status != TaskStatus.COMPLETED for node in graph.nodes.values()):
            # Historical manually constructed checkpoints omitted status.
            if state.get("mode"):
                raise ConfigurationRequired("Synthesis requires every planned task to be completed.")
        for node_id, result in results.items():
            if state.get("mode") and not all(result.get(key) for key in ("result_hash", "evidence_hash", "input_fingerprint")):
                raise ConfigurationRequired("Retained task is missing its identity records; synthesis cannot consume it.")
            if result.get("result_hash"):
                content = json.dumps(result["result"], sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                if hashlib.sha256(content.encode()).hexdigest() != result["result_hash"]:
                    raise ConfigurationRequired("Retained result identity changed; synthesis cannot consume it.")
                raw = result.get("raw_response")
                if not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != result.get("evidence_hash"):
                    raise ConfigurationRequired("Retained raw evidence identity changed; synthesis cannot consume it.")
    return state


async def _run_plan_stage(goal: str, output_path: str, model: str, backend: str, skip_web: bool,
                          max_depth: int, sources: Optional[List[str]], enable_jev: bool,
                          effort: Optional[str], worker_timeout: float, max_concurrency: int,
                          state_file: str, ui: MimirConsole, swarm: Optional[Any] = None,
                          search_query: Optional[str] = None, worker_transport: str = "native",
                          mode: str = "review", max_tasks: int = 4,
                          memory_mode: str = "read", memory_path: Optional[str] = None,
                          max_context_chars: int = 120000) -> Dict[str, Any]:
    is_en = ui.is_en
    if swarm is None:
        swarm = create_swarm_backend(backend_type=backend, model=model, max_concurrency=max_concurrency,
                                     effort=effort, timeout_seconds=worker_timeout)
        if hasattr(swarm, "help_command"):
            await swarm.check_cli()

    active_model = model or getattr(swarm, "default_model", "gemini-3.8-flash-low")
    backend_display = swarm.__class__.__name__.replace("SwarmBackend", "")
    memory = JarvisMemory(memory_path, mode=memory_mode, workspace=Path.cwd())
    mem_stats = memory.get_summary_stats()

    ui.print_banner(goal, active_model, backend_display, memory_stats=mem_stats,
                    web_enabled=not skip_web, jev_enabled=enable_jev, phase_mode="PLAN")
    ui.notice("worker_research_tools", "  Worker research tools: " +
              getattr(swarm, "research_tool_policy", "No MCP tool adapter; use supplied evidence"))

    start_plan_time = time.time()
    intel_brief = IntelligenceBrief(topic=goal)
    if not skip_web:
        ui.print_phase(1, "Mímir's World Scrying (Omni-Channel Discovery)")
        ui.notice("scout_querying", "  [BUSY] Mímir scries the world's networks... sifting primary evidence from cosmic noise.")
        scout = ResearchScout()
        # Network discovery is synchronous; keep the event loop available for
        # flushed liveness events while the search is waiting on remote sources.
        scout_options = {"custom_domains": sources}
        if search_query is not None:
            scout_options["search_query"] = search_query
        discovery = asyncio.create_task(asyncio.to_thread(scout.conduct_deep_scout, goal, **scout_options))
        try:
            intel_brief = await asyncio.shield(discovery)
        except asyncio.CancelledError:
            # urllib cannot abort an executor thread. Join its bounded requests
            # before releasing run ownership; no false completed cancellation.
            while not discovery.done():
                try:
                    await asyncio.shield(discovery)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if discovery.done() and not discovery.cancelled():
                discovery.exception()
            raise
        ui.display_intel(intel_brief)
    else:
        ui.print_phase(1, "Skipping external discovery (--skip-web)")
        ui.emit("research_skipped")

    intel_context = intel_brief.to_compact_markdown()
    memory_context = memory.load_memory_context(topic=goal)

    ui.print_phase(2, "Planning the evidence review")
    ui.notice("dag_decomposing", f"  Building a {mode} plan with at most {max_tasks} tasks.")
    decomposer = RecursiveDecomposer(swarm=swarm, max_depth=max_depth, mode=mode, max_tasks=max_tasks)
    task_graph = await decomposer.decompose_goal(
        goal=goal,
        intelligence_context=intel_context,
        memory_context=memory_context,
    )
    valid, error = task_graph.validate_acyclic_and_integrity()
    if not task_graph.nodes or not valid:
        raise ValueError(f"Invalid planned task graph: {error}")

    if enable_jev:
        jev_gate = JevDecisionGate(swarm=swarm)
        min_jev = 0.20 if max_concurrency >= 8 else 0.30
        pruned_nodes = await task_graph.prune_with_jev(jev_gate=jev_gate, min_jev=min_jev)
        if pruned_nodes:
            msg = f"Pruned {len(pruned_nodes)} low-JEV branches: {', '.join(pruned_nodes)}"
            ui.notice("tasks_pruned", msg, node_ids=pruned_nodes, threshold=min_jev)

    ui.display_dag(task_graph)

    state = {
        "version": 1,
        "phase": "planned",
        "goal": goal,
        "output_path": str(output_path),
        "backend": backend,
        "worker_transport": worker_transport,
        "model": active_model,
        "effort": effort,
        "worker_timeout": worker_timeout,
        "max_concurrency": max_concurrency,
        "enable_jev": enable_jev,
        "mode": mode, "max_tasks": max_tasks,
        "memory_mode": memory_mode, "memory_path": str(memory.memory_path),
        "max_context_chars": max_context_chars,
        "usage_calls": list(getattr(swarm, "usage_calls", [])),
        "intel_brief": intel_brief.to_dict(),
        "intel_context": intel_context,
        "memory_context": memory_context,
        "graph": task_graph.to_dict(),
        "task_graph_obj": task_graph,
        "tasks": [
            {"id": n.id, "role": n.role, "title": n.title, "dependencies": sorted(list(n.dependencies)), "jev_score": n.jev_score, "jev_status": n.jev_status}
            for n in task_graph.nodes.values()
        ],
        "tiers": [[n.id for n in tier] for tier in task_graph.get_execution_tiers()],
        "plan_duration_seconds": round(time.time() - start_plan_time, 2),
    }

    if state_file:
        _save_state(state, state_file)

    completion = dict(state_file=str(Path(state_file).resolve()) if state_file else "", task_count=len(task_graph.nodes), duration_seconds=state["plan_duration_seconds"])
    ui.emit("plan_checkpoint_ready", **completion)
    ui.completion = ("plan_completed", completion)

    if ui.progress_format == "terminal":
        task_summary = ", ".join([f"{n.id} ({n.role})" for n in task_graph.nodes.values()])
        plan_msg = (
            f"\n[OK] ᚱ Mímir Phase 1 (Plan) Complete: {len(task_graph.nodes)} tasks carved into DAG ({state['plan_duration_seconds']}s).\n"
            f"Tasks: {task_summary}\n"
        )
        if ui.console:
            ui.console.print(f"[bold green]{plan_msg}[/bold green]")
            ui._flush()
        else:
            print(plan_msg, flush=True)

    return state


async def _run_execute_stage(state: Dict[str, Any], state_file: Optional[str], backend: Optional[str],
                             model: Optional[str], effort: Optional[str], worker_timeout: Optional[float],
                             max_concurrency: Optional[int], ui: MimirConsole,
                             swarm: Optional[Any] = None) -> Dict[str, Any]:
    is_en = ui.is_en
    goal = state.get("goal", "")
    active_backend = backend or state.get("backend", "agy")
    active_model = model or state.get("model", "gemini-3.8-flash-low")
    active_effort = effort or state.get("effort") or getattr(swarm, "default_effort", "low")
    timeout = worker_timeout or state.get("worker_timeout", 180)
    concurrency = max_concurrency or state.get("max_concurrency", 4)

    if swarm is None:
        swarm = create_swarm_backend(backend_type=active_backend, model=active_model,
                                     max_concurrency=concurrency, effort=active_effort,
                                     timeout_seconds=timeout)
        if hasattr(swarm, "help_command"):
            await swarm.check_cli()

    task_graph = state.get("task_graph_obj") or TaskGraph.from_dict(state["graph"])
    blackboard = Blackboard(session_id=str(int(time.time())))
    start_exec_time = time.time()
    retained = state.get("completed_data", {})
    state["phase"] = "executing"
    state["completed_data"] = dict(retained)
    if state_file:
        _save_state(state, state_file)

    def persist_result(node, envelope):
        state["completed_data"][node.id] = envelope
        state["graph"] = task_graph.to_dict()
        state["blackboard_artifacts"] = blackboard.artifacts
        state["verified_evidence_hashes"] = list(blackboard.verified_evidence_store)
        state["usage_calls"] = list(getattr(swarm, "usage_calls", []))
        if state_file:
            _save_state(state, state_file)

    ui.print_phase(3, "Swarm of Runes (Parallel Execution & Evidence Contracts)")

    def on_task_finish(node: TaskNode, res: SwarmResult, contract: Optional[Any] = None):
        if res.status != "SUCCESS":
            ui.failed_tasks += 1
            ui.notice("task_failed", f"  [ERROR] {node.id} {node.role}: {res.raw_response[:300]}",
                      node_id=node.id, role=node.role, duration_seconds=res.duration_seconds)
            return
        ui.completed_tasks += 1
        h = contract.raw_evidence_hash[:10] if contract and hasattr(contract, "raw_evidence_hash") else ""
        result = json.dumps(res.data, ensure_ascii=False) if isinstance(res.data, (dict, list)) else str(res.data)
        ui.emit("task_completed", node_id=node.id, role=node.role, title=node.title,
                duration_seconds=res.duration_seconds, evidence_hash=h,
                output_excerpt=result[:400])
        ui.display_agent_done(node, res.duration_seconds, evidence_hash=h)

    try:
        research_dispatch = None
        if state.get("research_config"):
            from research_program import ResearchContext, ResearchDispatcher
            from source_store import SourceStore
            research_dispatch = ResearchDispatcher(ResearchContext(
                swarm, SourceStore(state["research_config"]["sources"]),
                Path(state_file).resolve().parent / (Path(state_file).stem + "-research"), state["research_config"]))
        completed_data = await swarm.execute_graph(
            graph=task_graph, blackboard=blackboard, jev_gate=None,
            on_task_start=ui.display_agent_submitted, on_task_finish=on_task_finish,
            retained_results=retained, on_result_commit=persist_result,
            **({"research_dispatch": research_dispatch} if research_dispatch else {}),
        )
    finally:
        state["graph"] = task_graph.to_dict()
        state["usage_calls"] = list(getattr(swarm, "usage_calls", []))
        state["execute_duration_seconds"] = state.get("execute_duration_seconds", 0) + round(time.time() - start_exec_time, 2)
        if state_file:
            _save_state(state, state_file)

    failed_nodes = [n.id for n in task_graph.nodes.values() if n.status != TaskStatus.COMPLETED]
    if failed_nodes:
        ui.emit("graph_incomplete", tasks=[{"id": n.id, "status": n.status.value}
                                          for n in task_graph.nodes.values() if n.status != TaskStatus.COMPLETED])
        from backend import WorkerFailure
        failure = next((n.error_trace for n in task_graph.nodes.values() if n.status == TaskStatus.FAILED), "")
        raise WorkerFailure("Mimir", failure or "Task graph incomplete; completed artifacts retained.")

    exec_duration = round(time.time() - start_exec_time, 2)
    state["phase"] = "executed"
    state["graph"] = task_graph.to_dict()
    state.update(backend=active_backend, model=active_model, effort=active_effort,
                 worker_timeout=timeout, max_concurrency=concurrency)
    state["completed_data"] = completed_data
    state["blackboard"] = blackboard
    state["blackboard_artifacts"] = blackboard.artifacts
    state["verified_evidence_hashes"] = list(blackboard.verified_evidence_store.keys())
    state["usage_calls"] = list(getattr(swarm, "usage_calls", []))

    if state_file:
        _save_state(state, state_file)

    completion = dict(state_file=str(Path(state_file).resolve()) if state_file else "", task_count=len(completed_data), duration_seconds=exec_duration)
    ui.emit("execution_checkpoint_ready", **completion)
    ui.completion = ("execute_completed", completion)

    if ui.progress_format == "terminal":
        exec_msg = (
            f"\n[OK] ⚔️ Mímir Phase 2 (Swarm) Complete: {len(completed_data)}/{len(task_graph.nodes)} tasks completed with output identity hashes ({exec_duration}s).\n"
        )
        if ui.console:
            ui.console.print(f"[bold green]{exec_msg}[/bold green]")
            ui._flush()
        else:
            print(exec_msg, flush=True)

    return state


async def _run_synthesize_stage(state: Dict[str, Any], state_file: Optional[str], output_path: Optional[str],
                                backend: Optional[str], model: Optional[str], effort: Optional[str],
                                ui: MimirConsole, swarm: Optional[Any] = None) -> Dict[str, Any]:
    is_en = ui.is_en
    goal = state.get("goal", "")
    final_out_path = output_path or state.get("output_path", "artifacts/mimir_solution.md")
    active_backend = backend or state.get("backend", "agy")
    active_model = model or state.get("model", "gemini-3.8-flash-low")
    active_effort = effort or state.get("effort") or getattr(swarm, "default_effort", "low")
    completed_data = state.get("completed_data", {})
    intel_context = state.get("intel_context", "")
    total_elapsed = state.get("plan_duration_seconds", 0) + state.get("execute_duration_seconds", 0)
    synthesis_started_at = time.monotonic()

    publication = state.get("publication")
    if state.get("phase") == "synthesized" and isinstance(publication, dict):
        report = Path(final_out_path).resolve()
        if str(report) != publication.get("report_path"):
            raise ConfigurationRequired("Recovery must use the published report path; start a new run to change it.")
        for path, key in ((report, "report_hash"), (report.with_suffix(".json"), "sidecar_hash")):
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != publication.get(key):
                raise ConfigurationRequired("Published artifact identity changed; recovery cannot silently replace it.")
        data = dict(report_path=str(report), json_path=str(report.with_suffix(".json")), task_count=len(completed_data), duration_seconds=state.get("total_elapsed_seconds", total_elapsed), recovered=True)
        ui.emit("publication_recovered", **data)
        ui.completion = ("run_completed", data)
        return state

    if not completed_data:
        raise ValueError("No completed worker tasks found in state file. Run --phase execute first.")
    if state.get("mode") and swarm is not None:
        from scheduler import validate_retained
        validate_retained(TaskGraph.from_dict(state["graph"]), swarm, completed_data)

    if swarm is None:
        swarm = create_swarm_backend(backend_type=active_backend, model=active_model,
                                     max_concurrency=state.get("max_concurrency", 4), effort=active_effort,
                                     timeout_seconds=state.get("worker_timeout", 180))
        if hasattr(swarm, "help_command"):
            await swarm.check_cli()

    backend_display = swarm.__class__.__name__.replace("SwarmBackend", "")
    memory = JarvisMemory(state.get("memory_path"), mode=state.get("memory_mode", "read"), workspace=Path.cwd())

    is_single = state.get("mode") == "single"
    ui.print_phase(4, "Preparing the single-worker report" if is_single else "Adversarial Trial & Red-Team Reflection")

    red_team_critiques = []

    for node_id, data in completed_data.items():
        role = data.get("role", "")
        res_content = str(data.get("result", ""))
        if "red-team" in role.lower() or "critic" in role.lower():
            red_team_critiques.append(res_content)

    # Supply the full evidence set, including findings a draft may have omitted.
    combined_draft = "\n\n".join(
        f"TASK {node_id} ({data.get('role', 'Worker')}): {data.get('title', '')}\n"
        + (json.dumps(data['result'], ensure_ascii=False) if isinstance(data['result'], (dict, list)) else str(data['result']))
        for node_id, data in completed_data.items()
    )
    combined_draft += "\n\nSOURCE RETRIEVAL RECORDS AND GAPS:\n" + json.dumps(state.get("intel_brief", {}), ensure_ascii=False)
    combined_draft += "\n\nSCOUT CONTEXT:\n" + intel_context

    combined_critique = "\n\n".join(red_team_critiques) if red_team_critiques else "No explicit critique was produced; identify and challenge gaps independently."
    ui.emit("critique_collected", critique_count=len(red_team_critiques),
            output_excerpt=combined_critique[:600] if red_team_critiques else "")
    if not is_single:
        ui.notice("reflection_started", "  Synthesizing findings and the critic's corrections.")

    if state.get("mode") == "single":
        from research_contract import normalize_worker_result
        hardened_solution = normalize_worker_result(next(iter(completed_data.values()))["result"])["answer"]
        reflection = "Single-worker report; no separate critique or reflective model call was performed."
    else:
        gepa = GepaOptimizer(swarm=swarm, critic_model=active_model)
        hardened_solution, reflection = await gepa.reflective_evolve(
            candidate_content=combined_draft, goal=goal, critique_points=combined_critique,
        )
    ui.emit("reflection_skipped" if is_single else "reflection_completed", output_excerpt=str(reflection)[:600])

    if ui.progress_format == "terminal":
        msg = "The single-worker findings are ready for publication." if is_single else "Mímir's reflective revision is ready for publication."
        if ui.console:
            ui.console.print(f"  [green][OK][/green] [bold]{msg}[/bold]")
            ui._flush()
        else:
            print(f"  [OK] {msg}", flush=True)

    ui.print_phase(5, "The Word of Mímir (Executive Synthesis & Chronicle)")
    ui.notice("synthesis_started", "  [BUSY] Recording Mímir's reviewed findings and remaining uncertainties...")

    hardened_str = json.dumps(hardened_solution, indent=2, ensure_ascii=False) if isinstance(hardened_solution, (dict, list)) else str(hardened_solution)
    reflection_str = json.dumps(reflection, indent=2, ensure_ascii=False) if isinstance(reflection, (dict, list)) else str(reflection)
    total_elapsed += time.monotonic() - synthesis_started_at

    mimir_persona_intro = (
        "> *Mímir records the worker findings and adversarial reflection. "
        "Source retrieval, model critique, and output hashes do not independently verify factual claims.*\n\n"
    )
    report_lines = [
        f"# M Í M I R // Review: {' '.join(goal.split())[:180]}",
        f"\n**Produced by:** Mímir Autonomous Swarm ({backend_display} / {active_model}) | **Time:** {total_elapsed:.1f}s | **Tasks Completed:** {len(completed_data)}",
        "\n---\n",
        mimir_persona_intro,
        "## 1. Executive Summary & Reviewed Findings",
        hardened_str,
        "\n---\n",
        "## 2. Mímir's Reflection & Adversarial Analysis (Red-Team)",
        f"**Reflection Notes:**\n{reflection_str}\n" if reflection_str else "",
        f"**Identified Pitfalls:**\n{combined_critique}\n" if combined_critique else "",
        "\n---\n",
        "## 3. Empirical Intelligence (Omni-Channel Evidence)",
        intel_context if intel_context else "No external intelligence gathered.",
        "\n---\n",
        "## 4. Atomic Task Results per Agent (with Evidence Contracts)",
    ]

    for node_id, data in completed_data.items():
        h = data.get("evidence_hash", "")
        h_str = f" [sha256:{h}]" if h else ""
        report_lines.append(f"### Node [{node_id}] - {data.get('role', 'Agent')}: {data.get('title', 'Task' if is_en else 'Uppgift')}{h_str}")
        node_res = data.get('result', '')
        node_res_str = json.dumps(node_res, indent=2, ensure_ascii=False) if isinstance(node_res, (dict, list)) else str(node_res)
        report_lines.append(f"```text\n{node_res_str}\n```\n")

    full_report = "\n".join([str(x) for x in report_lines])
    out_path = Path(final_out_path)

    json_path = out_path.with_suffix(".json")
    blackboard = state.get("blackboard")
    bb_artifacts = blackboard.artifacts if blackboard else state.get("blackboard_artifacts", {})
    bb_hashes = list(blackboard.verified_evidence_store.keys()) if blackboard else state.get("verified_evidence_hashes", [])
    from research_contract import aggregate_research_results, audit_final_references
    research = aggregate_research_results(completed_data)
    research["final_reference_audit"] = audit_final_references(hardened_str, research)
    if research["final_reference_audit"]["missing_supporting_locators"]:
        research["coverage"] = "partial"
    scout_gaps = state.get("intel_brief", {}).get("retrieval_gaps", [])
    research["gaps"].extend({"task_id": "public_scout", "description": gap} for gap in scout_gaps)
    if scout_gaps:
        research["coverage"] = "partial"
    calls = list(getattr(swarm, "usage_calls", []))
    usage = {"model_calls": len(calls), "known_tokens": sum(c.get("tokens_used", 0) or 0 for c in calls),
             "usage_complete": bool(calls) and all((c.get("tokens_used") or 0) > 0 for c in calls),
             "calls": calls, "billed_cost": None}
    usage["worker_calls"] = len(calls)
    usage["model_calls_scope"] = "Adapter invocations, not provider inference requests; native tool continuations may make multiple model requests."
    research_lines = ["\n## Evidence coverage and limitations\n",
                      f"Record coverage: **{research['coverage']}**. Independent factual validation: **not performed**.\n"]
    for source in research["sources"]:
        research_lines.append(f"- [{source['id']}] {source['locator']} ({source['retrieval_type']}; retrieved {source['retrieved_at'] or 'time unavailable'})\n  Supporting excerpt: {source['support_excerpt']}")
    for gap in research["gaps"] + research["issues"]:
        research_lines.append(f"- Gap [{gap['task_id']}]: {gap['description']}")
    for locator in research["final_reference_audit"]["missing_supporting_locators"]:
        research_lines.append(f"- Supporting source omitted from the synthesis text: {locator}")
    full_report += "\n" + "\n".join(research_lines)

    json_payload = {
        "goal": goal,
        "persona": "Mímir",
        "backend": backend_display,
        "model": active_model,
        "worker_effort": active_effort,
        "elapsed_seconds": total_elapsed,
        "intel_brief": state.get("intel_brief", {}),
        "task_results": completed_data,
        "reflection": reflection,
        "hardened_solution": hardened_solution,
        "blackboard_artifacts": bb_artifacts,
        "verified_evidence_hashes": bb_hashes,
        "output_identity_hashes": bb_hashes,
        "evidence_verification": "Output identity only; factual correctness has not been independently verified.",
        "memory_file": str(memory.memory_path),
        "memory_mode": state.get("memory_mode", "read"),
        "learning_candidate_file": str(getattr(memory, "candidate_path", memory.memory_path)),
        "execution_policy": {"mode": state.get("mode", "legacy"), "max_tasks": state.get("max_tasks"), "max_context_chars": state.get("max_context_chars"),
                             "research_program": state.get("research_program", "native"),
                             "research_budget": (state.get("research_config") or {}).get("budget")},
        "research": research, "usage": usage,
        "research_identity": state.get("research_identity"),
        "captured_sources": [{k: v for k, v in r.items() if k != "text"}
                             for r in (state.get("research_config") or {}).get("sources", [])],
    }
    json_content = json.dumps(json_payload, indent=2, ensure_ascii=False, allow_nan=False)
    _write_artifact(json_path, json_content)
    _write_artifact(out_path, full_report)
    state.update(phase="synthesized", report_path=str(out_path.resolve()),
                 backend=active_backend, model=active_model, effort=active_effort,
                 synthesis_duration_seconds=round(time.monotonic() - synthesis_started_at, 2))
    state["usage_calls"] = calls
    state["total_elapsed_seconds"] = total_elapsed
    state["publication"] = {"report_path": str(out_path.resolve()),
                            "report_hash": hashlib.sha256(out_path.read_bytes()).hexdigest(),
                            "sidecar_hash": hashlib.sha256(json_path.read_bytes()).hexdigest()}
    # Commit publication identity before any optional learning write. A crash
    # after this point recovers artifacts without another reflective call.
    if state_file:
        _save_state(state, state_file)
    memory_saved = memory.record_learning(
        goal=goal, hardened_solution_snippet=hardened_str,
        reflection_notes=reflection_str, red_team_traps=red_team_critiques,
        report_path=str(out_path.resolve()),
    )
    mode = state.get("memory_mode", "read")
    ui.emit(("memory_recorded" if memory_saved else "memory_write_failed") if mode == "write" else "memory_write_skipped", memory_file=str(memory.memory_path), candidate_file=str(getattr(memory, "candidate_path", memory.memory_path)), mode=mode)
    state["learning_candidate_saved"] = memory_saved if mode == "write" else False
    if state_file:
        _save_state(state, state_file)

    if ui.console:
        completed_title = "The Counsel of Mímir is complete!"
        rep_saved = "📄 Report saved to:"
        json_saved = "📊 JSON structured data:"
        mem_saved = "🧠 Long-term memory updated:"
        tot_time = "⏱ Total time:"
        ui.console.print(Panel(
            f"[bold gold1]{completed_title}[/bold gold1]\n\n"
            f"{rep_saved} [cyan]{out_path.resolve()}[/cyan]\n"
            f"{json_saved} [cyan]{json_path.resolve()}[/cyan]\n"
            f"{'Learning candidate saved:' if memory_saved and mode == 'write' else 'Learning write failed:' if mode == 'write' else 'Learning writes disabled:'} [cyan]{getattr(memory, 'candidate_path', memory.memory_path).resolve()}[/cyan]\n"
            f"{tot_time} [bold white]{total_elapsed:.1f}s[/bold white]",
            border_style="gold1",
            title="[bold gold1]M Í M I R // WISDOM DELIVERED[/bold gold1]"
        ))
        ui.console.print(f"\n[bold gold1]Summary from Mímir:[/bold gold1]\n")
        ui.console.print(Markdown(hardened_str[:1500] + ("..." if len(hardened_str) > 1500 else "")))
        ui._flush()
    elif ui.progress_format == "terminal":
        rep_msg = f"\n[OK] 📜 Mímir Phase 3 Complete: Report saved to {out_path.resolve()} ({total_elapsed:.1f}s)\n"
        print(rep_msg, flush=True)

    completion = dict(report_path=str(out_path.resolve()), json_path=str(json_path.resolve()), task_count=len(completed_data), duration_seconds=total_elapsed)
    ui.emit("artifacts_ready", **completion)
    ui.completion = ("run_completed", completion)
    return state


async def run_mimir(
    goal: Optional[str] = None,
    output_path: Optional[str] = None,
    model: Optional[str] = None,
    backend: Optional[str] = None,
    skip_web: bool = False,
    max_depth: int = 2,
    sources: Optional[List[str]] = None,
    enable_jev: Optional[bool] = None,
    effort: Optional[str] = None,
    worker_timeout: Optional[float] = None,
    max_concurrency: Optional[int] = None,
    progress_format: str = "terminal",
    phase: str = "all",
    state_file: str = "artifacts/mimir_state.json",
    search_query: Optional[str] = None,
    worker_transport: Optional[str] = None,
    event_sink: Optional[Callable] = None,
    worker_factory: Optional[Callable] = None,
    mode: Optional[str] = None,
    max_tasks: Optional[int] = None,
    memory_mode: Optional[str] = None,
    memory_path: Optional[str] = None,
    max_context_chars: Optional[int] = None,
    research_program: Optional[str] = None,
    research_budget: Optional[dict] = None,
    source_manifest: Optional[str] = None,
    program_manifest: Optional[str] = None,
):
    if progress_format not in ("terminal", "jsonl", "events"):
        raise ValueError("Progress format must be terminal, jsonl or events.")

    is_en = is_english_text(goal or "")
    ui = MimirConsole(is_en=is_en, progress_format=progress_format, event_sink=event_sink)

    swarm = None
    checkpoint_lock = None
    heartbeat = asyncio.create_task(ui.heartbeat())
    try:
        if phase not in {"all", "plan", "execute", "synthesize"}:
            raise ValueError("Unknown Mimir phase.")
        candidate_lock = _checkpoint_lock(state_file)
        candidate_lock.__enter__()
        checkpoint_lock = candidate_lock
        state = _load_state(state_file, phase) if phase in {"execute", "synthesize"} else {}
        if state and ((mode is not None and mode != state.get("mode", mode)) or
                      (max_tasks is not None and max_tasks != state.get("max_tasks", max_tasks))):
            raise ConfigurationRequired("Execution policy and task cap are fixed by the plan; start a new run to change them.")
        mode = mode or state.get("mode", "review")
        max_tasks = max_tasks if max_tasks is not None else state.get("max_tasks", 4)
        memory_mode = memory_mode or state.get("memory_mode", "read")
        memory_path = memory_path or state.get("memory_path")
        max_context_chars = max_context_chars if max_context_chars is not None else state.get("max_context_chars", 120000)
        enable_jev = enable_jev if enable_jev is not None else state.get("enable_jev", False)
        if mode not in {"single", "review", "swarm"} or type(max_tasks) is not int or not 1 <= max_tasks <= 16:
            raise ConfigurationRequired("Choose single/review/swarm and a maximum of 1–16 tasks.")
        if memory_mode not in {"off", "read", "write"}:
            raise ConfigurationRequired("Memory mode must be off, read or write.")
        if type(max_context_chars) is not int or max_context_chars < 1000:
            raise ConfigurationRequired("Context admission requires at least 1000 characters.")
        from research_program import prepare_research
        research_config, captured_sources, research_identity = await asyncio.to_thread(prepare_research,
            research_program, research_budget, source_manifest, program_manifest,
            state, Path(state_file).resolve().parent)
        if state:
            if goal and goal != state["goal"]:
                raise ValueError("Objective does not match persisted state.")
            goal = state["goal"]
        elif not isinstance(goal, str) or not goal.strip():
            raise ValueError("Provide a nonempty goal or --goal-file.")
        # State is the fallback for a resumed phase, after explicit/env choices.
        fallback_backend = backend or os.environ.get("MIMIR_BACKEND") or state.get("backend")
        if fallback_backend == "auto":
            fallback_backend = os.environ.get("MIMIR_BACKEND") or state.get("backend")
        resume_same_backend = fallback_backend == state.get("backend")
        selected_model = model or (os.environ.get(f"MIMIR_{fallback_backend.upper()}_MODEL") if fallback_backend else None) or os.environ.get("MIMIR_MODEL")
        selected_effort = effort or os.environ.get("MIMIR_EFFORT")
        if resume_same_backend:
            selected_model = selected_model or state.get("model")
            selected_effort = selected_effort or state.get("effort")
        resolved_backend, resolved_model, resolved_effort = resolve_execution(fallback_backend, selected_model, selected_effort)
        if resolved_backend == state.get("backend"):
            resolved_model = resolved_model or state.get("model")
            resolved_effort = resolved_effort or state.get("effort")
        worker_timeout = worker_timeout if worker_timeout is not None else state.get("worker_timeout", 180)
        max_concurrency = max_concurrency if max_concurrency is not None else state.get("max_concurrency", 4)
        output_path = output_path or state.get("output_path") or "artifacts/mimir_solution.md"
        state_path = Path(state_file).resolve()
        paths = [Path(output_path).resolve(), Path(output_path).with_suffix(".json").resolve(), state_path,
                 state_path.with_name(state_path.name + ".lock")]
        if len(set(paths)) != len(paths):
            raise ValueError("Report, JSON sidecar and state paths must be distinct; use a .md report path.")
        # Older checkpoints were created by CLI adapters. Preserve that contract
        # when no explicit invocation/environment transport replaces it.
        selected_transport = worker_transport or os.environ.get("MIMIR_WORKER_TRANSPORT") or (state.get("worker_transport", "cli") if state and resume_same_backend else None) or "native"
        factory = worker_factory or create_swarm_backend
        swarm = factory(backend_type=resolved_backend, model=resolved_model,
                                     max_concurrency=max_concurrency, effort=resolved_effort,
                                     timeout_seconds=worker_timeout, worker_transport=selected_transport)
        if getattr(swarm, "_native_config", False):
            from diagnostics import native_environment
            native, _ = native_environment(resolved_backend)
            config_hashes = []
            for config_file in native.get("config_paths", []):
                path = Path(config_file)
                config_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
            swarm.execution_identity = {"provider": native.get("provider"), "config_hashes": config_hashes, "transport": selected_transport}
        from invocation_broker import InvocationBroker
        swarm = InvocationBroker(swarm, max_context_chars=max_context_chars,
                                 calls=state.get("usage_calls", []),
                                 budget=research_config["budget"],
                                 journal=Path(state_file).with_suffix(".operations.jsonl") if research_config["budget"] else None,
                                 policy=research_identity if research_config["program"] != "native" or captured_sources.records else None,
                                 recover=bool(state))
        if mode == "review" and research_config["budget"]:
            swarm.reserve_for_review = 2
        elif mode == "swarm" and research_config["budget"]:
            swarm.reserve_for_review = 1
        if hasattr(swarm, "help_command") or getattr(swarm, "transport", None) in ("sdk", "server"):
            await swarm.check_cli()

        if state:
            state["research_program"] = research_config["program"]
            state["research_config"] = research_config
            state["worker_transport"] = selected_transport
            state["memory_mode"] = memory_mode
            state["memory_path"] = memory_path
            state["max_context_chars"] = max_context_chars
            if memory_path is None:
                state.pop("memory_path", None)
        if phase == "plan":
            if not goal:
                raise ValueError("Provide a goal or --goal-file for --phase plan.")
            state = await _run_plan_stage(
                goal=goal, output_path=output_path, model=resolved_model, backend=resolved_backend,
                skip_web=skip_web, max_depth=max_depth, sources=sources, enable_jev=enable_jev,
                effort=resolved_effort, worker_timeout=worker_timeout, max_concurrency=max_concurrency,
                state_file=state_file, ui=ui, swarm=swarm, search_query=search_query, worker_transport=selected_transport,
                mode=mode, max_tasks=max_tasks, memory_mode=memory_mode, memory_path=memory_path, max_context_chars=max_context_chars
            )
            state.update(research_program=research_config["program"], research_config=research_config,
                         research_identity=research_identity)
            _save_state(state, state_file)
        elif phase == "execute":
            state_p = Path(state_file)
            if not state_p.exists():
                raise FileNotFoundError(f"State file not found at {state_p}. Run --phase plan first.")
            state = await _run_execute_stage(
                state=state, state_file=state_file, backend=resolved_backend, model=resolved_model,
                effort=resolved_effort, worker_timeout=worker_timeout, max_concurrency=max_concurrency,
                ui=ui, swarm=swarm
            )
        elif phase == "synthesize":
            state_p = Path(state_file)
            if not state_p.exists():
                raise FileNotFoundError(f"State file not found at {state_p}. Run --phase plan and execute first.")
            state = await _run_synthesize_stage(
                state=state, state_file=state_file, output_path=output_path, backend=resolved_backend,
                model=resolved_model, effort=resolved_effort, ui=ui, swarm=swarm
            )
        else:  # "all"
            if not goal:
                raise ValueError("Provide a goal or --goal-file.")
            plan_state = await _run_plan_stage(
                goal=goal, output_path=output_path, model=resolved_model, backend=resolved_backend,
                skip_web=skip_web, max_depth=max_depth, sources=sources, enable_jev=enable_jev,
                effort=resolved_effort, worker_timeout=worker_timeout, max_concurrency=max_concurrency,
                state_file=state_file, ui=ui, swarm=swarm, search_query=search_query, worker_transport=selected_transport,
                mode=mode, max_tasks=max_tasks, memory_mode=memory_mode, memory_path=memory_path, max_context_chars=max_context_chars
            )
            plan_state.update(research_program=research_config["program"], research_config=research_config,
                              research_identity=research_identity)
            _save_state(plan_state, state_file)
            exec_state = await _run_execute_stage(
                state=plan_state, state_file=state_file, backend=resolved_backend, model=resolved_model,
                effort=resolved_effort, worker_timeout=worker_timeout, max_concurrency=max_concurrency,
                ui=ui, swarm=swarm
            )
            state = await _run_synthesize_stage(
                state=exec_state, state_file=state_file, output_path=output_path, backend=resolved_backend,
                model=resolved_model, effort=resolved_effort, ui=ui, swarm=swarm
            )
        return state
    except asyncio.CancelledError:
        ui.emit("run_cancelled")
        raise
    except ConfigurationRequired as exc:
        ui.emit("configuration_required", message=str(exc))
        raise
    except Exception as exc:
        ui.emit("run_failed", error_type=type(exc).__name__, message=worker_diagnostic("Mimir", str(exc), error=exc))
        raise
    finally:
        heartbeat.cancel()
        try:
            with suppress(asyncio.CancelledError):
                await heartbeat
        finally:
            try:
                if swarm:
                    if hasattr(swarm, "aclose"):
                        cleanup = asyncio.create_task(swarm.aclose())
                        cleanup_cancelled = False
                        while not cleanup.done():
                            try:
                                await asyncio.shield(cleanup)
                            except asyncio.CancelledError:
                                cleanup_cancelled = True
                                continue
                        try:
                            cleanup.result()
                        except Exception as exc:
                            ui.emit("run_failed", error_type=type(exc).__name__, message="Worker cleanup failed; verify the local runtime before retrying.")
                            raise
                        if cleanup_cancelled:
                            raise asyncio.CancelledError
                    else:
                        swarm.cleanup()
                if sys.exc_info()[0] is None and ui.completion is not None:
                    event, details = ui.completion
                    ui.emit(event, **details)
            finally:
                if checkpoint_lock is not None:
                    checkpoint_lock.__exit__(None, None, None)
