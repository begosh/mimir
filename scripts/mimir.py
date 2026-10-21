"""
scripts/mimir.py
M Í M I R // The Omniscient Oracle & Autonomous Recursive Multi-Agent Swarm.
Keeper of the Well of Wisdom (Mimisbrunnr).
Combines dynamic omni-channel research, recursive DAG decomposition,
JEV System-1 decision gating, EvidenceContracts, and cumulative long-term memory.
Bilingual: Seamlessly operates in Swedish and English.
Supports both single-run pipeline and discrete phased execution (--phase plan|execute|synthesize|all).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Force UTF-8 and line buffering on Windows stdout/stderr to prevent cp1252 errors and pipe buffering stalls
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

# Ensure scripts dir is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from backend import BaseSwarmBackend, SwarmResult, SwarmTask, create_swarm_backend
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
    def __init__(self, is_en: bool = False, progress_format: str = "terminal"):
        self.console = Console(highlight=False) if HAS_RICH and progress_format == "terminal" else None
        self.is_en = is_en
        self.progress_format = progress_format
        self.started_at = time.monotonic()
        self.sequence = 0

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
        if self.progress_format == "jsonl":
            self.sequence += 1
            print(json.dumps({
                "schema_version": 1, "sequence": self.sequence, "event": event,
                "elapsed_seconds": round(time.monotonic() - self.started_at, 3),
                **data,
            }, ensure_ascii=False), flush=True)

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
        if self.progress_format == "jsonl":
            return
        if self.is_en:
            title = "[bold gold1]M Í M I R // Keeper of Wisdom & Autonomous Swarm[/bold gold1]"
            sub = '[italic dim]"Drink from the Well. Truth distilled from the noise of the cosmos."[/italic dim]'
            mem_text = f"Chronicle: {entries} entries"
            lbl_goal = "OBJECTIVE"
        else:
            title = "[bold gold1]M Í M I R // Vishetens Väktare & Autonom Svärm[/bold gold1]"
            sub = '[italic dim]"Drick ur Mimers brunn. Sanningen är silad ur kosmos brus."[/italic dim]'
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

    def print_phase(self, phase_num: int, title_sv: str, title_en: str):
        title = title_en if self.is_en else title_sv
        self.emit("phase_started", phase=phase_num, title=title)
        if self.progress_format == "jsonl":
            return
        if self.console:
            self.console.print(f"\n[bold gold1]>> FAS {phase_num}: {title.upper()}[/bold gold1]")
            self._flush()
        else:
            print(f"\n--- FAS {phase_num}: {title} ---", flush=True)

    def display_intel(self, brief: IntelligenceBrief):
        self.emit("research_completed", source_count=len(brief.items), sources=[
            {"title": item.title, "channel": item.channel, "url": item.url}
            for item in brief.items[:6]
        ])
        if self.progress_format == "jsonl":
            return
        if not self.console:
            print(brief.to_compact_markdown(), flush=True)
            return

        title = "Mímir's Omni-Channel Scryer (Inhämtad Data)" if not self.is_en else "Mímir's Omni-Channel Scryer (Discovered Intelligence)"
        table = Table(title=f"[bold blue]{title}[/bold blue]", border_style="blue")
        table.add_column("Kanal / Domän" if not self.is_en else "Channel / Domain", style="cyan", width=24)
        table.add_column("Fynd / Titel" if not self.is_en else "Finding / Title", style="bold white", width=42)
        table.add_column("Källa / Meta" if not self.is_en else "Source / Meta", style="green", width=20)

        for it in brief.items[:6]:
            table.add_row(it.channel[:22], it.title[:40] + "...", it.author_or_meta[:18])

        self.console.print(table)
        self._flush()

    def display_dag(self, graph: TaskGraph):
        self.emit("graph_ready", tasks=[
            {"id": n.id, "role": n.role, "title": n.title,
             "dependencies": sorted(n.dependencies), "jev_score": n.jev_score}
            for n in graph.nodes.values()
        ], tiers=[[n.id for n in tier] for tier in graph.get_execution_tiers()])
        if self.progress_format == "jsonl":
            return
        if not self.console:
            print(f"Task Graph with {len(graph.nodes)} nodes:", flush=True)
            for n in graph.nodes.values():
                print(f" - [{n.id}] {n.role}: {n.title} (JEV: {getattr(n, 'jev_score', 1.0):.2f})", flush=True)
            return

        label = "Mímirs Run- och Uppgifts-DAG" if not self.is_en else "Mímir's Task & Rune DAG"
        tree = Tree(f"[bold cyan]{label}[/bold cyan] ({len(graph.nodes)} {'deluppgifter' if not self.is_en else 'atomic tasks'})")
        tiers = graph.get_execution_tiers()
        for idx, tier in enumerate(tiers):
            tier_lbl = f"Exekveringstier #{idx+1}" if not self.is_en else f"Execution Tier #{idx+1}"
            tier_branch = tree.add(f"[bold yellow]{tier_lbl}[/bold yellow] ({len(tier)} noder)")
            for node in tier:
                deps_str = f" [dim](beror på: {', '.join(node.dependencies)})[/dim]" if node.dependencies else ""
                jev_val = getattr(node, "jev_score", 1.0)
                jev_str = f" [bold yellow]JEV:{jev_val:.2f}[/bold yellow]"
                tier_branch.add(f"[bold white]{node.id}[/bold white] - [green]{node.role}[/green]: {node.title}{deps_str}{jev_str}")

        self.console.print(tree)
        self._flush()

    def display_agent_done(self, node: TaskNode, duration: float, evidence_hash: str = ""):
        if self.progress_format == "jsonl":
            return
        hash_tag = f" [dim cyan]sha256:{evidence_hash}[/dim cyan]" if evidence_hash else ""
        if self.console:
            self.console.print(f"  [green][OK][/green] [[cyan]{node.id}[/cyan]] [bold]{node.role}[/bold]: {node.title} [dim]({duration:.1f}s)[/dim]{hash_tag}")
            self._flush()
        else:
            print(f"  [OK] {node.id} {node.role}: {node.title} ({duration:.1f}s){hash_tag}", flush=True)

    def display_agent_submitted(self, node: TaskNode):
        self.emit("task_submitted", node_id=node.id, role=node.role, title=node.title)
        if self.progress_format == "terminal":
            if self.console:
                self.console.print(f"  [cyan][RUNNING][/cyan] [{node.id}] {node.role}: {node.title}")
                self._flush()
            else:
                print(f"  [RUNNING] [{node.id}] {node.role}: {node.title}", flush=True)


async def _run_plan_stage(goal: str, output_path: str, model: str, backend: str, skip_web: bool,
                          max_depth: int, sources: Optional[List[str]], enable_jev: bool,
                          effort: Optional[str], worker_timeout: float, max_concurrency: int,
                          state_file: str, ui: MimirConsole, swarm: Optional[Any] = None) -> Dict[str, Any]:
    is_en = ui.is_en
    if swarm is None:
        swarm = create_swarm_backend(backend_type=backend, model=model, max_concurrency=max_concurrency,
                                     effort=effort, timeout_seconds=worker_timeout)
        if hasattr(swarm, "help_command"):
            await swarm.check_cli()

    active_model = model or getattr(swarm, "default_model", "gemini-3.8-flash-low")
    backend_display = swarm.__class__.__name__.replace("SwarmBackend", "")
    memory = JarvisMemory()
    mem_stats = memory.get_summary_stats()

    ui.print_banner(goal, active_model, backend_display, memory_stats=mem_stats,
                    web_enabled=not skip_web, jev_enabled=enable_jev, phase_mode="PLAN")

    start_plan_time = time.time()
    intel_brief = IntelligenceBrief(topic=goal)
    if not skip_web:
        ui.print_phase(1, "Mímirs Världsspaning (Dynamiska Källor & Primärdata)", "Mímir's World Scrying (Omni-Channel Discovery)")
        ui.notice("scout_querying", "  [BUSY] Mímir scries the world's networks... sifting primary evidence from cosmic noise." if is_en else "  [BUSY] Mimer skådar genom världarnas nätverk... silar primärdata ur kosmos brus.")
        scout = ResearchScout()
        intel_brief = scout.conduct_deep_scout(goal, custom_domains=sources)
        ui.display_intel(intel_brief)
    else:
        ui.print_phase(1, "Hoppar över extern spaning (--skip-web)", "Skipping external discovery (--skip-web)")
        ui.emit("research_skipped")

    intel_context = intel_brief.to_compact_markdown()
    memory_context = memory.load_memory_context(topic=goal)

    ui.print_phase(2, "Mimisbrunns Dissektion (Rekursiv DAG & JEV-Beskärning)", "Dissection of Mimisbrunnr (Recursive DAG & JEV Pruning)")
    ui.notice("dag_decomposing", "  [BUSY] Carving the Runes of the DAG & weighing branches on the scales of JEV..." if is_en else "  [BUSY] Ristar uppgifts-DAGens runor och väger grenarna på JEV-vågen...")
    target_tasks = max_concurrency if max_concurrency >= 6 else None
    decomposer = RecursiveDecomposer(swarm=swarm, max_depth=max_depth, target_tasks=target_tasks)
    task_graph = await decomposer.decompose_goal(
        goal=goal,
        intelligence_context=intel_context,
        memory_context=memory_context,
    )

    if enable_jev:
        jev_gate = JevDecisionGate(swarm=swarm)
        min_jev = 0.20 if max_concurrency >= 8 else 0.30
        pruned_nodes = await task_graph.prune_with_jev(jev_gate=jev_gate, min_jev=min_jev)
        if pruned_nodes:
            msg = f"Beskar bort {len(pruned_nodes)} noder med låg JEV: {', '.join(pruned_nodes)}" if not is_en else f"Pruned {len(pruned_nodes)} low-JEV branches: {', '.join(pruned_nodes)}"
            ui.notice("tasks_pruned", msg, node_ids=pruned_nodes, threshold=min_jev)

    ui.display_dag(task_graph)

    state = {
        "version": 1,
        "phase": "planned",
        "goal": goal,
        "output_path": str(output_path),
        "backend": backend,
        "model": active_model,
        "effort": effort,
        "worker_timeout": worker_timeout,
        "max_concurrency": max_concurrency,
        "enable_jev": enable_jev,
        "intel_brief": intel_brief.to_dict(),
        "intel_context": intel_context,
        "memory_context": memory_context,
        "graph": task_graph.to_dict(),
        "task_graph_obj": task_graph,
        "tasks": [
            {"id": n.id, "role": n.role, "title": n.title, "dependencies": sorted(list(n.dependencies)), "jev_score": n.jev_score}
            for n in task_graph.nodes.values()
        ],
        "tiers": [[n.id for n in tier] for tier in task_graph.get_execution_tiers()],
        "plan_duration_seconds": round(time.time() - start_plan_time, 2),
    }

    if state_file:
        state_p = Path(state_file)
        state_p.parent.mkdir(parents=True, exist_ok=True)
        # Store without task_graph_obj for JSON serializability
        save_state = dict(state)
        save_state.pop("task_graph_obj", None)
        state_p.write_text(json.dumps(save_state, indent=2, ensure_ascii=False), encoding="utf-8")

    ui.emit("plan_completed", state_file=str(Path(state_file).resolve()) if state_file else "", task_count=len(task_graph.nodes),
            duration_seconds=state["plan_duration_seconds"])

    if ui.progress_format != "jsonl":
        task_summary = ", ".join([f"{n.id} ({n.role})" for n in task_graph.nodes.values()])
        if is_en:
            plan_msg = (
                f"\n[OK] ᚱ Mímir Phase 1 (Plan) Complete: {len(task_graph.nodes)} tasks carved into DAG ({state['plan_duration_seconds']}s).\n"
                f"Tasks: {task_summary}\n"
            )
        else:
            plan_msg = (
                f"\n[OK] ᚱ Mimers Fas 1 (Plan) klar: {len(task_graph.nodes)} runuppgifter ristade i DAGen ({state['plan_duration_seconds']}s).\n"
                f"Uppgifter: {task_summary}\n"
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

    ui.print_phase(3, "Runornas Svärm (Parallell Exekvering & Evidensavtal)", "Swarm of Runes (Parallel Execution & Evidence Contracts)")

    def on_task_finish(node: TaskNode, res: SwarmResult, contract: Optional[Any] = None):
        if res.status != "SUCCESS":
            ui.notice("task_failed", f"  [ERROR] {node.id} {node.role}: {res.raw_response[:300]}",
                      node_id=node.id, role=node.role, duration_seconds=res.duration_seconds)
            return
        h = contract.raw_evidence_hash[:10] if contract and hasattr(contract, "raw_evidence_hash") else ""
        result = json.dumps(res.data, ensure_ascii=False) if isinstance(res.data, (dict, list)) else str(res.data)
        ui.emit("task_completed", node_id=node.id, role=node.role, title=node.title,
                duration_seconds=res.duration_seconds, evidence_hash=h,
                output_excerpt=result[:400])
        ui.display_agent_done(node, res.duration_seconds, evidence_hash=h)

    completed_data = await swarm.execute_graph(
        graph=task_graph,
        blackboard=blackboard,
        jev_gate=None,
        on_task_start=ui.display_agent_submitted,
        on_task_finish=on_task_finish,
    )

    failed_nodes = [n.id for n in task_graph.nodes.values() if n.status != TaskStatus.COMPLETED]
    if failed_nodes:
        ui.emit("graph_incomplete", tasks=[{"id": n.id, "status": n.status.value}
                                          for n in task_graph.nodes.values() if n.status != TaskStatus.COMPLETED])
        raise RuntimeError(f"Swarm incomplete ({', '.join(failed_nodes)}); no completed report recorded.")

    exec_duration = round(time.time() - start_exec_time, 2)
    state["phase"] = "executed"
    state["completed_data"] = completed_data
    state["blackboard"] = blackboard
    state["blackboard_artifacts"] = blackboard.artifacts
    state["verified_evidence_hashes"] = list(blackboard.verified_evidence_store.keys())
    state["execute_duration_seconds"] = exec_duration

    if state_file:
        state_p = Path(state_file)
        save_state = dict(state)
        save_state.pop("task_graph_obj", None)
        save_state.pop("blackboard", None)
        state_p.write_text(json.dumps(save_state, indent=2, ensure_ascii=False), encoding="utf-8")

    ui.emit("execute_completed", state_file=str(Path(state_file).resolve()) if state_file else "",
            task_count=len(completed_data), duration_seconds=exec_duration)

    if ui.progress_format != "jsonl":
        if is_en:
            exec_msg = (
                f"\n[OK] ⚔️ Mímir Phase 2 (Swarm) Complete: {len(completed_data)}/{len(completed_data)} tasks executed with verified evidence contracts ({exec_duration}s).\n"
            )
        else:
            exec_msg = (
                f"\n[OK] ⚔️ Mimers Fas 2 (Svärm) klar: {len(completed_data)}/{len(completed_data)} deluppgifter exekverade med verifierade evidensavtal ({exec_duration}s).\n"
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

    if not completed_data:
        raise ValueError("No completed worker tasks found in state file. Run --phase execute first.")

    if swarm is None:
        swarm = create_swarm_backend(backend_type=active_backend, model=active_model,
                                     max_concurrency=4, effort=active_effort, timeout_seconds=180)
        if hasattr(swarm, "help_command"):
            await swarm.check_cli()

    backend_display = swarm.__class__.__name__.replace("SwarmBackend", "")
    memory = JarvisMemory()

    ui.print_phase(4, "Mimers Råd & Red-Team Prövning (GEPA Pareto-Härdning)", "Mímir's Counsel & Red-Team Trial (GEPA Pareto-Hardening)")

    red_team_critiques = []
    draft_solutions = []

    for node_id, data in completed_data.items():
        role = data.get("role", "")
        res_content = str(data.get("result", ""))
        if "Red-Team" in role or "Critic" in role:
            red_team_critiques.append(res_content)
        elif "Synthesizer" in role or "Modeler" in role or "Architect" in role:
            draft_solutions.append(res_content)

    synth_drafts = [str(data.get("result", "")) for data in completed_data.values() if "Synthesizer" in data.get("role", "")]
    if synth_drafts:
        combined_draft = synth_drafts[0]
    elif draft_solutions:
        combined_draft = "\n\n".join(draft_solutions)
    else:
        combined_draft = "Lösning genererad av Mímir." if not is_en else "Solution generated by Mímir."

    combined_critique = "\n\n".join(red_team_critiques) if red_team_critiques else "Ingen explicit kritik."
    ui.emit("critique_collected", critique_count=len(red_team_critiques),
            output_excerpt=combined_critique[:600] if red_team_critiques else "")
    ui.notice("reflection_started", "  [BUSY] Tempering candidate wisdom in the adversarial furnace of the Red-Team trial..." if is_en else "  [BUSY] Härdar lösningsvisdomen i Red-Team-prövningens eld och motståndarkritik...")

    gepa = GepaOptimizer(swarm=swarm, critic_model=active_model)
    hardened_solution, reflection = await gepa.reflective_evolve(
        candidate_content=combined_draft,
        goal=goal,
        critique_points=combined_critique[:2500],
    )
    ui.emit("reflection_completed", output_excerpt=str(reflection)[:600])

    if ui.progress_format == "terminal":
        msg = "Mímir has hardened the wisdom against adversarial critique." if is_en else "Mímir har härdat visdomen mot motståndarkritik."
        if ui.console:
            ui.console.print(f"  [green][OK][/green] [bold]{msg}[/bold]")
            ui._flush()
        else:
            print(f"  [OK] {msg}", flush=True)

    ui.print_phase(5, "Mimers Ord (Executive Syntes & Minneskonsolidering)", "The Word of Mímir (Executive Synthesis & Memory Consolidation)")
    ui.notice("synthesis_started", "  [BUSY] Forging the final Pareto-hardened Word of Mímir into the chronicle..." if is_en else "  [BUSY] Smider Mimers slutgiltiga Pareto-härdade ord till den eviga krönikan...")

    hardened_str = json.dumps(hardened_solution, indent=2, ensure_ascii=False) if isinstance(hardened_solution, (dict, list)) else str(hardened_solution)
    reflection_str = json.dumps(reflection, indent=2, ensure_ascii=False) if isinstance(reflection, (dict, list)) else str(reflection)

    if is_en:
        mimir_persona_intro = (
            "> *\"I am Mímir, keeper of the Well of Wisdom. You asked for truth, unadorned and uncompromised. "
            "My swarm has walked the global networks, weighed the probabilities, and forged this answer in the fires of rigor.\"\n\n"
        )
        report_lines = [
            f"# M Í M I R // Solution Matrix: {goal}",
            f"\n**Produced by:** Mímir Autonomous Swarm ({backend_display} / {active_model}) | **Time:** {total_elapsed:.1f}s | **Tasks Completed:** {len(completed_data)}",
            "\n---\n",
            mimir_persona_intro,
            "## 1. Executive Summary & Pareto-Hardened Truth",
            hardened_str,
            "\n---\n",
            "## 2. Mímir's Reflection & Adversarial Analysis (Red-Team)",
            f"**Reflection Notes:**\n{reflection_str}\n" if reflection_str else "",
            f"**Averted Pitfalls:**\n{combined_critique[:1500]}\n" if combined_critique else "",
            "\n---\n",
            "## 3. Empirical Intelligence (Omni-Channel Evidence)",
            intel_context if intel_context else "No external intelligence gathered.",
            "\n---\n",
            "## 4. Atomic Task Results per Agent (with Evidence Contracts)",
        ]
    else:
        mimir_persona_intro = (
            "> *\"Jag är Mimer, vishetens väktare vid mimisbrunn. Du sökte sanningen utan dimridåer eller kompromisser. "
            "Min svärm har vandrat genom världarnas nätverk, vägt sannolikheterna och härdat denna lösning i prövningens eld.\"\n\n"
        )
        report_lines = [
            f"# M Í M I R // Solution Matrix: {goal}",
            f"\n**Framtagen av:** Mímir Autonomous Swarm ({backend_display} / {active_model}) | **Tid:** {total_elapsed:.1f}s | **Deluppgifter:** {len(completed_data)}",
            "\n---\n",
            mimir_persona_intro,
            "## 1. Executive Summary & Pareto-Härdad Sanning",
            hardened_str,
            "\n---\n",
            "## 2. Mimers Reflektion & Motståndaranalys (Red-Team)",
            f"**Reflektionsnoter:**\n{reflection_str}\n" if reflection_str else "",
            f"**Avvärjda fallgropar:**\n{combined_critique[:1500]}\n" if combined_critique else "",
            "\n---\n",
            "## 3. Empirisk Omvärldsspaning (Omni-Channel Evidence)",
            intel_context if intel_context else "Ingen omvärldsspaning genomförd.",
            "\n---\n",
            "## 4. Detaljerade Delresultat per Agent (med Evidence Contracts)",
        ]

    for node_id, data in completed_data.items():
        h = data.get("evidence_hash", "")
        h_str = f" [sha256:{h}]" if h else ""
        report_lines.append(f"### Node [{node_id}] - {data.get('role', 'Agent')}: {data.get('title', 'Task' if is_en else 'Uppgift')}{h_str}")
        node_res = data.get('result', '')
        node_res_str = json.dumps(node_res, indent=2, ensure_ascii=False) if isinstance(node_res, (dict, list)) else str(node_res)
        report_lines.append(f"```text\n{node_res_str[:1500]}\n```\n")

    full_report = "\n".join([str(x) for x in report_lines])
    out_path = Path(final_out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full_report, encoding="utf-8")

    memory.record_learning(
        goal=goal,
        hardened_solution_snippet=hardened_str,
        reflection_notes=reflection_str,
        red_team_traps=red_team_critiques,
    )

    json_path = out_path.with_suffix(".json")
    blackboard = state.get("blackboard")
    bb_artifacts = blackboard.artifacts if blackboard else state.get("blackboard_artifacts", {})
    bb_hashes = list(blackboard.verified_evidence_store.keys()) if blackboard else state.get("verified_evidence_hashes", [])

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
        "memory_file": str(memory.memory_path),
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if ui.console:
        completed_title = "The Counsel of Mímir is complete!" if is_en else "Mimers råd är fullbordat!"
        rep_saved = "📄 Report saved to:" if is_en else "📄 Rapport sparad till:"
        json_saved = "📊 JSON structured data:" if is_en else "📊 JSON-strukturerad data:"
        mem_saved = "🧠 Long-term memory updated:" if is_en else "🧠 Långtidsminne uppdaterat:"
        tot_time = "⏱ Total time:" if is_en else "⏱ Total tid:"
        ui.console.print(Panel(
            f"[bold gold1]{completed_title}[/bold gold1]\n\n"
            f"{rep_saved} [cyan]{out_path.resolve()}[/cyan]\n"
            f"{json_saved} [cyan]{json_path.resolve()}[/cyan]\n"
            f"{mem_saved} [cyan]{memory.memory_path.resolve()}[/cyan]\n"
            f"{tot_time} [bold white]{total_elapsed:.1f}s[/bold white]",
            border_style="gold1",
            title="[bold gold1]M Í M I R // WISDOM DELIVERED[/bold gold1]"
        ))
        ui.console.print(f"\n[bold gold1]{'Mimers sammanfattning:' if not is_en else 'Summary from Mímir:'}[/bold gold1]\n")
        ui.console.print(Markdown(hardened_str[:1500] + ("..." if len(hardened_str) > 1500 else "")))
        ui._flush()
    elif ui.progress_format == "terminal":
        rep_msg = f"\n[OK] 📜 Mímir Phase 3 Complete: Report saved to {out_path.resolve()} ({total_elapsed:.1f}s)\n"
        print(rep_msg, flush=True)

    ui.emit("run_completed", report_path=str(out_path.resolve()), json_path=str(json_path.resolve()),
            task_count=len(completed_data), duration_seconds=total_elapsed)
    return state


async def run_mimir(
    goal: Optional[str] = None,
    output_path: str = "artifacts/mimir_solution.md",
    model: Optional[str] = None,
    backend: Optional[str] = None,
    skip_web: bool = False,
    max_depth: int = 2,
    sources: Optional[List[str]] = None,
    enable_jev: bool = True,
    effort: Optional[str] = None,
    worker_timeout: float = 180,
    max_concurrency: int = 4,
    progress_format: str = "terminal",
    phase: str = "all",
    state_file: str = "artifacts/mimir_state.json",
):
    if progress_format not in ("terminal", "jsonl"):
        raise ValueError("Progress format must be terminal or jsonl.")
    
    if phase in ("execute", "synthesize") and not goal:
        state_p = Path(state_file)
        if state_p.exists():
            try:
                st = json.loads(state_p.read_text(encoding="utf-8"))
                goal = st.get("goal", "")
            except Exception:
                pass

    is_en = is_english_text(goal or "")
    ui = MimirConsole(is_en=is_en, progress_format=progress_format)

    swarm = None
    try:
        resolved_backend, resolved_model, resolved_effort = resolve_execution(backend, model, effort)
        swarm = create_swarm_backend(backend_type=resolved_backend, model=resolved_model,
                                     max_concurrency=max_concurrency, effort=resolved_effort,
                                     timeout_seconds=worker_timeout)
        if hasattr(swarm, "help_command"):
            await swarm.check_cli()

        if phase == "plan":
            if not goal:
                raise ValueError("Provide a goal or --goal-file for --phase plan.")
            await _run_plan_stage(
                goal=goal, output_path=output_path, model=resolved_model, backend=resolved_backend,
                skip_web=skip_web, max_depth=max_depth, sources=sources, enable_jev=enable_jev,
                effort=resolved_effort, worker_timeout=worker_timeout, max_concurrency=max_concurrency,
                state_file=state_file, ui=ui, swarm=swarm
            )
        elif phase == "execute":
            state_p = Path(state_file)
            if not state_p.exists():
                raise FileNotFoundError(f"State file not found at {state_p}. Run --phase plan first.")
            state = json.loads(state_p.read_text(encoding="utf-8"))
            await _run_execute_stage(
                state=state, state_file=state_file, backend=resolved_backend, model=resolved_model,
                effort=resolved_effort, worker_timeout=worker_timeout, max_concurrency=max_concurrency,
                ui=ui, swarm=swarm
            )
        elif phase == "synthesize":
            state_p = Path(state_file)
            if not state_p.exists():
                raise FileNotFoundError(f"State file not found at {state_p}. Run --phase plan and execute first.")
            state = json.loads(state_p.read_text(encoding="utf-8"))
            await _run_synthesize_stage(
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
                state_file=state_file, ui=ui, swarm=swarm
            )
            exec_state = await _run_execute_stage(
                state=plan_state, state_file=state_file, backend=resolved_backend, model=resolved_model,
                effort=resolved_effort, worker_timeout=worker_timeout, max_concurrency=max_concurrency,
                ui=ui, swarm=swarm
            )
            await _run_synthesize_stage(
                state=exec_state, state_file=state_file, output_path=output_path, backend=resolved_backend,
                model=resolved_model, effort=resolved_effort, ui=ui, swarm=swarm
            )
    except asyncio.CancelledError:
        ui.emit("run_cancelled")
        raise
    except ConfigurationRequired as exc:
        ui.emit("configuration_required", message=str(exc))
        raise
    except Exception as exc:
        ui.emit("run_failed", error_type=type(exc).__name__, message=str(exc)[:500])
        raise
    finally:
        if swarm:
            swarm.cleanup()


def main():
    parser = argparse.ArgumentParser(description="M Í M I R // Omniscient Oracle & Autonomous Swarm")
    parser.add_argument("goal", nargs="?", type=str, help="Det komplexa målet, forskningsfrågan eller strategin.")
    parser.add_argument("--goal-file", type=str, help="UTF-8 file containing the objective and required context")
    parser.add_argument("--phase", "--stage", choices=["all", "plan", "execute", "synthesize"], default="all",
                        help="Execute a discrete phase of Mimir or the entire pipeline (plan | execute | synthesize | all)")
    parser.add_argument("--state-file", type=str, default="artifacts/mimir_state.json",
                        help="State file path for phased execution (default: artifacts/mimir_state.json)")
    parser.add_argument("--check", action="store_true", help="Check CLI and worker settings without a model call")
    setup = parser.add_mutually_exclusive_group()
    setup.add_argument("--config-status", action="store_true", help="Show saved project profile and available CLIs without a model call")
    setup.add_argument("--configure", action="store_true", help="Save an explicitly agreed backend/model/effort in .mimir/config.json")
    parser.add_argument("--host", choices=["agy", "codex", "claude", "opencode"],
                        help="Hosting CLI suggestion for --config-status; never automatically saves a choice")
    parser.add_argument("--host-model", help="Known host model for a first-use worker suggestion; does not select or save it")
    parser.add_argument("--output", "-o", type=str, default="artifacts/mimir_solution.md", help="Sökväg för rapport")
    parser.add_argument("--backend", "-b", type=str, default=None, choices=["auto", "agy", "codex", "claude", "opencode", "openai", "anthropic", "ollama"], help="CLI or HTTP backend; otherwise use saved setup")
    parser.add_argument("--effort", default=None, help="Worker reasoning effort (default low); OpenCode provider variant or none")
    parser.add_argument("--worker-timeout", type=float, default=180, help="Timeout per CLI call in seconds")
    parser.add_argument("--concurrency", type=int, default=4, help="Maximum concurrent workers")
    parser.add_argument("--progress", choices=["terminal", "jsonl"], default="terminal",
                        help="Rich terminal display or flushed JSONL progress events for a hosting harness")
    parser.add_argument("--model", "-m", type=str, default=None, help="Modell för mikromodeller (standard: anpassas efter backend)")
    parser.add_argument("--skip-web", action="store_true", help="Hoppa över extern omvärldsspaning")
    parser.add_argument("--depth", type=int, default=2, help="Maximalt rekursionsdjup för dekomposition")
    parser.add_argument("--sources", "-s", type=str, default=None, help="Kommaseparerad lista med specifika källor/domäner")
    parser.add_argument("--no-jev", action="store_true", help="Inaktivera JEV-optimering")

    args = parser.parse_args()
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
    if args.concurrency < 1:
        parser.error("--concurrency must be positive")
    if args.check:
        try:
            backend, model, effort = resolve_execution(args.backend, args.model, args.effort)
            swarm = create_swarm_backend(backend, model, args.concurrency, effort, args.worker_timeout)
            if not hasattr(swarm, "help_command"):
                parser.error("--check validates CLI backends only")
            print(json.dumps(asyncio.run(swarm.check_cli()), ensure_ascii=False, indent=2))
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
            enable_jev=not args.no_jev,
            effort=args.effort,
            worker_timeout=args.worker_timeout,
            max_concurrency=args.concurrency,
            progress_format=args.progress,
            phase=args.phase,
            state_file=args.state_file,
        ))
    except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as exc:
        parser.exit(1, f"Mimir failed: {exc}\n")


if __name__ == "__main__":
    main()
