"""
scripts/mimir.py
M Í M I R // The Omniscient Oracle & Autonomous Recursive Multi-Agent Swarm.
Keeper of the Well of Wisdom (Mimisbrunnr).
Combines dynamic omni-channel research, recursive DAG decomposition,
JEV System-1 decision gating, EvidenceContracts, and cumulative long-term memory.
Bilingual: Seamlessly operates in Swedish and English.
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

# Force UTF-8 on Windows stdout/stderr to prevent cp1252 charmap errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure scripts dir is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from backend import BaseSwarmBackend, SwarmResult, SwarmTask, create_swarm_backend
from gepa_optimizer import GepaOptimizer
from jarvis_memory import JarvisMemory
from jev_gate import JevDecisionGate
from research_scout import IntelligenceBrief, ResearchScout
from task_graph import Blackboard, RecursiveDecomposer, TaskGraph, TaskNode

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


def is_english_text(text: str) -> bool:
    """Detects whether user prompt is primarily in English."""
    common_en = {"how", "what", "why", "best", "the", "and", "for", "with", "system", "architecture", "build", "design"}
    common_sv = {"hur", "vad", "varför", "bästa", "och", "för", "med", "att", "bygga", "skapa", "lösa"}
    words = set(re.findall(r"\b\w+\b", text.lower()))
    en_score = len(words & common_en)
    sv_score = len(words & common_sv)
    return en_score > sv_score


class MimirConsole:
    def __init__(self, is_en: bool = False):
        self.console = Console(highlight=False) if HAS_RICH else None
        self.is_en = is_en

    def print_banner(self, goal: str, model: str, backend_name: str, memory_stats: Optional[Dict[str, Any]] = None):
        entries = memory_stats.get('entries', 0) if memory_stats else 0
        if self.is_en:
            title = "[bold gold1]M Í M I R // Keeper of Wisdom & Autonomous Swarm[/bold gold1]"
            sub = "[italic dim]\"Drink from the Well. Truth distilled from the noise of the cosmos.\"[/italic dim]"
            mem_text = f"Chronicle: {entries} entries"
            lbl_goal = "OBJECTIVE"
        else:
            title = "[bold gold1]M Í M I R // Vishetens Väktare & Autonom Svärm[/bold gold1]"
            sub = "[italic dim]\"Drick ur Mimers brunn. Sanningen är silad ur kosmos brus.\"[/italic dim]"
            mem_text = f"Minne: {entries} lärdomar"
            lbl_goal = "UPPDRAG"

        banner_text = f"{title}\n{sub}\n\n[bold white]{lbl_goal}:[/bold white] [green]{goal}[/green]\n"
        banner_text += f"[dim]Motor: {backend_name} ({model}) | {mem_text} | Nätverk: Omni-Channel | JEV-Gate: Aktiv[/dim]"

        if self.console:
            self.console.print(Panel(banner_text, border_style="gold1", title="[bold gold1]MIMISBRUNNR ONLINE[/bold gold1]"))
        else:
            print(f"=== M I M I R ===\n{goal}\nBackend: {backend_name} ({model}) | {mem_text}\n")

    def print_phase(self, phase_num: int, title_sv: str, title_en: str):
        title = title_en if self.is_en else title_sv
        if self.console:
            self.console.print(f"\n[bold gold1]>> FAS {phase_num}: {title.upper()}[/bold gold1]")
        else:
            print(f"\n--- FAS {phase_num}: {title} ---")

    def display_intel(self, brief: IntelligenceBrief):
        if not self.console:
            print(brief.to_compact_markdown())
            return

        title = "Mímir's Omni-Channel Scryer (Inhämtad Data)" if not self.is_en else "Mímir's Omni-Channel Scryer (Discovered Intelligence)"
        table = Table(title=f"[bold blue]{title}[/bold blue]", border_style="blue")
        table.add_column("Kanal / Domän" if not self.is_en else "Channel / Domain", style="cyan", width=24)
        table.add_column("Fynd / Titel" if not self.is_en else "Finding / Title", style="bold white", width=42)
        table.add_column("Källa / Meta" if not self.is_en else "Source / Meta", style="green", width=20)

        for it in brief.items[:6]:
            table.add_row(it.channel[:22], it.title[:40] + "...", it.author_or_meta[:18])

        self.console.print(table)

    def display_dag(self, graph: TaskGraph):
        if not self.console:
            print(f"Task Graph with {len(graph.nodes)} nodes:")
            for n in graph.nodes.values():
                print(f" - [{n.id}] {n.role}: {n.title} (JEV: {getattr(n, 'jev_score', 1.0):.2f})")
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

    def display_agent_done(self, node: TaskNode, duration: float, evidence_hash: str = ""):
        hash_tag = f" [dim cyan]sha256:{evidence_hash}[/dim cyan]" if evidence_hash else ""
        if self.console:
            self.console.print(f"  [green][OK][/green] [[cyan]{node.id}[/cyan]] [bold]{node.role}[/bold]: {node.title} [dim]({duration:.1f}s)[/dim]{hash_tag}")
        else:
            print(f"  [OK] {node.id} {node.role}: {node.title} ({duration:.1f}s){hash_tag}")


async def run_mimir(
    goal: str,
    output_path: str = "artifacts/mimir_solution.md",
    model: Optional[str] = None,
    backend: str = "auto",
    skip_web: bool = False,
    max_depth: int = 2,
    sources: Optional[List[str]] = None,
    enable_jev: bool = True,
):
    is_en = is_english_text(goal)
    memory = JarvisMemory()
    mem_stats = memory.get_summary_stats()

    swarm = create_swarm_backend(backend_type=backend, model=model, max_concurrency=4)
    active_model = model or getattr(swarm, "default_model", "gemini-3.8-flash-low")
    backend_display = swarm.__class__.__name__.replace("SwarmBackend", "")

    ui = MimirConsole(is_en=is_en)
    ui.print_banner(goal, active_model, backend_display, memory_stats=mem_stats)

    blackboard = Blackboard(session_id=str(int(time.time())))
    jev_gate = JevDecisionGate(swarm=swarm) if enable_jev else None
    start_total_time = time.time()

    # -------------------------------------------------------------------------
    # Fas 1: Mímir's Scryer (Omni-Channel Sensor Array)
    # -------------------------------------------------------------------------
    intel_brief = IntelligenceBrief(topic=goal)
    if not skip_web:
        ui.print_phase(1, "Mímirs Världsspaning (Dynamiska Källor & Primärdata)", "Mímir's World Scrying (Omni-Channel Discovery)")
        scout = ResearchScout()
        intel_brief = scout.conduct_deep_scout(goal, custom_domains=sources)
        ui.display_intel(intel_brief)
    else:
        ui.print_phase(1, "Hoppar över extern spaning (--skip-web)", "Skipping external discovery (--skip-web)")

    intel_context = intel_brief.to_compact_markdown()
    memory_context = memory.load_memory_context(topic=goal)

    # -------------------------------------------------------------------------
    # Fas 2: Mimers Brunn (Rekursiv RLM-Dekomposition & JEV-Beskärning)
    # -------------------------------------------------------------------------
    ui.print_phase(2, "Mimisbrunns Dissektion (Rekursiv DAG & JEV-Beskärning)", "Dissection of Mimisbrunnr (Recursive DAG & JEV Pruning)")
    decomposer = RecursiveDecomposer(swarm=swarm, max_depth=max_depth)
    task_graph = await decomposer.decompose_goal(
        goal=goal,
        intelligence_context=intel_context,
        memory_context=memory_context,
    )

    if jev_gate:
        pruned_nodes = await task_graph.prune_with_jev(jev_gate=jev_gate, min_jev=0.30)
        if pruned_nodes and ui.console:
            msg = f"Beskar bort {len(pruned_nodes)} noder med låg JEV: {', '.join(pruned_nodes)}" if not is_en else f"Pruned {len(pruned_nodes)} low-JEV branches: {', '.join(pruned_nodes)}"
            ui.console.print(f"  [yellow][JEV-PRUNED][/yellow] {msg}")

    ui.display_dag(task_graph)

    # -------------------------------------------------------------------------
    # Fas 3: Runornas Svärm (Parallell Exekvering & Evidensavtal)
    # -------------------------------------------------------------------------
    ui.print_phase(3, "Runornas Svärm (Parallell Exekvering & Evidensavtal)", "Swarm of Runes (Parallel Execution & Evidence Contracts)")

    def on_task_finish(node: TaskNode, res: SwarmResult, contract: Optional[Any] = None):
        h = contract.raw_evidence_hash[:10] if contract and hasattr(contract, "raw_evidence_hash") else ""
        ui.display_agent_done(node, res.duration_seconds, evidence_hash=h)

    completed_data = await swarm.execute_graph(
        graph=task_graph,
        blackboard=blackboard,
        jev_gate=jev_gate,
        on_task_finish=on_task_finish,
    )

    # -------------------------------------------------------------------------
    # Fas 4: Mimers Råd & Red-Team Prövning (GEPA Pareto-Härdning)
    # -------------------------------------------------------------------------
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

    combined_draft = "\n\n".join(draft_solutions) if draft_solutions else "Lösning genererad av Mímir."
    combined_critique = "\n\n".join(red_team_critiques) if red_team_critiques else "Ingen explicit kritik."

    gepa = GepaOptimizer(swarm=swarm, critic_model=active_model)
    hardened_solution, reflection = await gepa.reflective_evolve(
        candidate_content=combined_draft[:4000],
        goal=goal,
        critique_points=combined_critique[:2500],
    )

    if ui.console:
        ui.console.print(f"  [green][OK][/green] [bold]{'Mímir har härdat visdomen mot motståndarkritik.' if not is_en else 'Mímir has hardened the wisdom against adversarial critique.'}[/bold]")

    # -------------------------------------------------------------------------
    # Fas 5: Mimers Ord & Minneskonsolidering (Executive Syntes)
    # -------------------------------------------------------------------------
    ui.print_phase(5, "Mimers Ord (Executive Syntes & Minneskonsolidering)", "The Word of Mímir (Executive Synthesis & Memory Consolidation)")
    total_elapsed = time.time() - start_total_time

    hardened_str = json.dumps(hardened_solution, indent=2, ensure_ascii=False) if isinstance(hardened_solution, (dict, list)) else str(hardened_solution)
    reflection_str = json.dumps(reflection, indent=2, ensure_ascii=False) if isinstance(reflection, (dict, list)) else str(reflection)

    if is_en:
        mimir_persona_intro = (
            "> *\"I am Mímir, keeper of the Well of Wisdom. You asked for truth, unadorned and uncompromised. "
            "My swarm has walked the global networks, weighed the probabilities, and forged this answer in the fires of rigor.\"*\n\n"
        )
    else:
        mimir_persona_intro = (
            "> *\"Jag är Mimer, vishetens väktare vid mimisbrunn. Du sökte sanningen utan dimridåer eller kompromisser. "
            "Min svärm har vandrat genom världarnas nätverk, vägt sannolikheterna och härdat denna lösning i prövningens eld.\"*\n\n"
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
        report_lines.append(f"### Node [{node_id}] - {data.get('role', 'Agent')}: {data.get('title', 'Uppgift')}{h_str}")
        node_res = data.get('result', '')
        node_res_str = json.dumps(node_res, indent=2, ensure_ascii=False) if isinstance(node_res, (dict, list)) else str(node_res)
        report_lines.append(f"```text\n{node_res_str[:1500]}\n```\n")

    full_report = "\n".join([str(x) for x in report_lines])

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full_report, encoding="utf-8")

    memory.record_learning(
        goal=goal,
        hardened_solution_snippet=hardened_str,
        reflection_notes=reflection_str,
        red_team_traps=red_team_critiques,
    )

    json_path = out_path.with_suffix(".json")
    json_payload = {
        "goal": goal,
        "persona": "Mímir",
        "backend": backend_display,
        "model": active_model,
        "elapsed_seconds": total_elapsed,
        "intel_brief": intel_brief.to_dict(),
        "task_results": completed_data,
        "reflection": reflection,
        "hardened_solution": hardened_solution,
        "blackboard_artifacts": blackboard.artifacts,
        "verified_evidence_hashes": list(blackboard.verified_evidence_store.keys()),
        "memory_file": str(memory.memory_path),
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if ui.console:
        ui.console.print(Panel(
            f"[bold gold1]{'Mimers råd är fullbordat!' if not is_en else 'The Counsel of Mímir is complete!'}[/bold gold1]\n\n"
            f"📄 Rapport sparad till: [cyan]{out_path.resolve()}[/cyan]\n"
            f"📊 JSON-strukturerad data: [cyan]{json_path.resolve()}[/cyan]\n"
            f"🧠 Långtidsminne uppdaterat: [cyan]{memory.memory_path.resolve()}[/cyan]\n"
            f"⏱ Total tid: [bold white]{total_elapsed:.1f}s[/bold white]",
            border_style="gold1",
            title="[bold gold1]M Í M I R // WISDOM DELIVERED[/bold gold1]"
        ))
        ui.console.print(f"\n[bold gold1]{'Mimers sammanfattning:' if not is_en else 'Summary from Mímir:'}[/bold gold1]\n")
        ui.console.print(Markdown(hardened_str[:1500] + ("..." if len(hardened_str) > 1500 else "")))
    else:
        print(f"\n[OK] Rapport sparad till {out_path.resolve()} ({total_elapsed:.1f}s)")

    swarm.cleanup()


def main():
    parser = argparse.ArgumentParser(description="M Í M I R // Omniscient Oracle & Autonomous Swarm")
    parser.add_argument("goal", type=str, help="Det komplexa målet, forskningsfrågan eller strategin.")
    parser.add_argument("--output", "-o", type=str, default="artifacts/mimir_solution.md", help="Sökväg för rapport")
    parser.add_argument("--backend", "-b", type=str, default="auto", choices=["auto", "agy", "openai", "anthropic", "ollama"], help="LLM-backend motor")
    parser.add_argument("--model", "-m", type=str, default=None, help="Modell för mikromodeller (standard: anpassas efter backend)")
    parser.add_argument("--skip-web", action="store_true", help="Hoppa över extern omvärldsspaning")
    parser.add_argument("--depth", type=int, default=2, help="Maximalt rekursionsdjup för dekomposition")
    parser.add_argument("--sources", "-s", type=str, default=None, help="Kommaseparerad lista med specifika källor/domäner")
    parser.add_argument("--no-jev", action="store_true", help="Inaktivera JEV-optimering")

    args = parser.parse_args()
    source_list = [s.strip() for s in args.sources.split(",")] if args.sources else None

    asyncio.run(run_mimir(
        goal=args.goal,
        output_path=args.output,
        backend=args.backend,
        model=args.model,
        skip_web=args.skip_web,
        max_depth=args.depth,
        sources=source_list,
        enable_jev=not args.no_jev,
    ))


if __name__ == "__main__":
    main()
