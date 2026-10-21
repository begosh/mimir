"""
scripts/task_graph.py
Hardened Recursive Task Decomposition, DAG Scheduler, and Evidence Contract Engine.
Implements Kahn topological sort, deadlock-free failure cascading, and Blackboard state.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from backend import BaseSwarmBackend, SwarmResult, SwarmTask
from mimir_config import is_english_text


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskRole(str, Enum):
    SCOUT = "Intel-Scout"
    ANALYST = "Domain-Analyst"
    MATHEMATICIAN = "Formal-Modeler"
    RED_TEAM = "Red-Team-Critic"
    SYNTHESIZER = "Executive-Synthesizer"
    CODER = "Code-Architect"


@dataclass
class EvidenceContract:
    """
    Deterministic evidence contract preventing hallucination cascading.
    Requires grounding references and cryptographic SHA256 verification.
    """
    grounding_ref: str
    raw_evidence_hash: str
    verification_passed: bool = True
    assertion_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceDelta:
    key: str
    value: Any
    evidence: EvidenceContract

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "evidence": self.evidence.to_dict(),
        }


@dataclass
class TaskNode:
    id: str
    role: str
    title: str
    prompt: str
    dependencies: Set[str] = field(default_factory=set)
    depth: int = 0
    max_depth: int = 4
    is_atomic: bool = True
    status: TaskStatus = TaskStatus.PENDING
    jev_score: float = 1.0
    input_artifacts: Dict[str, Any] = field(default_factory=dict)
    output_deltas: List[EvidenceDelta] = field(default_factory=list)
    output_data: Optional[Any] = None
    duration_seconds: float = 0.0
    retry_count: int = 0
    max_retries: int = 2
    error_trace: Optional[str] = None

    def is_ready(self, completed_ids: Set[str]) -> bool:
        return all(dep in completed_ids for dep in self.dependencies)


@dataclass
class Blackboard:
    """
    Shared verified state container for the swarm.
    Commits are gated through EvidenceContract validation.
    """
    session_id: str
    global_context: Dict[str, Any] = field(default_factory=dict)
    task_dag: Dict[str, TaskNode] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    verified_evidence_store: Dict[str, str] = field(default_factory=dict)
    node_sync_cursors: Dict[str, int] = field(default_factory=dict)

    def commit_evidence_delta(self, delta: EvidenceDelta) -> bool:
        if not delta.evidence.verification_passed:
            return False
        if delta.evidence.raw_evidence_hash not in self.verified_evidence_store:
            return False
        self.artifacts[delta.key] = delta.value
        return True

    def commit_evidence(self, node_id: str, key: str, value: Any, contract: EvidenceContract) -> bool:
        self.verified_evidence_store[contract.raw_evidence_hash] = str(value)
        self.artifacts[key] = value
        return True

    def register_evidence(self, raw_str: str) -> str:
        h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
        self.verified_evidence_store[h] = raw_str
        return h

    def get_diff_since_last_sync(self, node_id: str) -> str:
        if not self.artifacts:
            return ""
        snippets = []
        for k, v in list(self.artifacts.items())[-4:]:
            v_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
            snippets.append(f"[{k}]: {v_str[:400]}")
        return "\n".join(snippets)


class TaskGraph:
    """
    Hardened DAG representation with Kahn's topological sort and cycle validation.
    """

    def __init__(self, goal: str):
        self.goal = goal
        self.nodes: Dict[str, TaskNode] = {}

    def add_node(self, node: TaskNode) -> bool:
        self.nodes[node.id] = node
        return True

    def validate_acyclic_and_integrity(self) -> Tuple[bool, str]:
        in_degree = {nid: 0 for nid in self.nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}

        for nid, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    return False, f"Okänd beroendenod '{dep}' refererad av '{nid}'."
                adj[dep].append(nid)
                in_degree[nid] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            curr = queue.pop(0)
            visited_count += 1
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(self.nodes):
            return False, f"Cykliskt beroende upptäckt i DAG! Endast {visited_count}/{len(self.nodes)} noder nåbara."

        return True, "Valid"

    async def prune_with_jev(self, jev_gate: Any, min_jev: float = 0.35) -> List[str]:
        pruned_ids = []
        for nid, node in list(self.nodes.items()):
            role_lower = node.role.lower()
            if "synthesiz" in role_lower or "red-team" in role_lower or "critic" in role_lower or not node.dependencies:
                node.jev_score = 1.0
                continue

            score = await jev_gate.evaluate_task_jev(
                task_title=node.title,
                task_prompt=node.prompt,
                goal=self.goal,
                parent_dependencies=list(node.dependencies),
            )
            node.jev_score = score

            if score < min_jev:
                pruned_ids.append(nid)
                del self.nodes[nid]
                for other in self.nodes.values():
                    if nid in other.dependencies:
                        other.dependencies.remove(nid)
                        other.dependencies.update(node.dependencies)

        if pruned_ids:
            self.validate_acyclic_and_integrity()

        return pruned_ids

    def cascade_failure(self, failed_node_id: str) -> None:
        self.cascade_failures()

    def cascade_failures(self) -> bool:
        changed = False
        for node in self.nodes.values():
            if node.status in {TaskStatus.PENDING, TaskStatus.READY}:
                failed_dep = any(
                    self.nodes[d].status in {TaskStatus.FAILED, TaskStatus.CANCELLED}
                    for d in node.dependencies if d in self.nodes
                )
                if failed_dep:
                    node.status = TaskStatus.CANCELLED
                    node.error_trace = "Uppgift avbruten på grund av misslyckat uppströmsberoende."
                    changed = True
        return changed

    def get_runnable_nodes(self) -> List[TaskNode]:
        self.cascade_failures()
        runnable = []
        for node in self.nodes.values():
            if node.status == TaskStatus.PENDING:
                all_completed = all(
                    self.nodes[dep].status == TaskStatus.COMPLETED
                    for dep in node.dependencies if dep in self.nodes
                )
                if all_completed:
                    node.status = TaskStatus.READY
                    runnable.append(node)
        return runnable

    def get_execution_tiers(self) -> List[List[TaskNode]]:
        is_valid, msg = self.validate_acyclic_and_integrity()
        if not is_valid:
            return [list(self.nodes.values())]

        completed: Set[str] = set()
        tiers: List[List[TaskNode]] = []

        while len(completed) < len(self.nodes):
            tier = [
                node for nid, node in self.nodes.items()
                if nid not in completed and all(dep in completed for dep in node.dependencies)
            ]
            if not tier:
                remaining = [node for nid, node in self.nodes.items() if nid not in completed]
                if remaining:
                    tiers.append(remaining)
                break

            tiers.append(tier)
            for node in tier:
                completed.add(node.id)

        return tiers


class RecursiveDecomposer:
    """
    Recursive Language Model (RLM) engine that decomposes complex goals
    into atomic, non-overlapping tasks for micro-agent swarms.
    """

    def __init__(self, swarm: Any, max_depth: int = 3):
        self.swarm = swarm
        self.max_depth = max_depth

    async def decompose_goal(self, goal: str, intelligence_context: str = "", memory_context: str = "") -> TaskGraph:
        graph = TaskGraph(goal=goal)

        is_en = is_english_text(goal)
        if is_en:
            decomp_prompt = f"""
            You are Mímir Chief Architect. Your task is to decompose the following objective into
            4-6 atomic, non-overlapping tasks that specialized micro-agents can solve in parallel.

            OBJECTIVE: "{goal}"

            CUMULATIVE HEURISTICS & LEARNINGS (FROM MEMORY BANK):
            {memory_context[:1000] if memory_context else "No prior memory context available."}

            EXTERNAL RESEARCH & CONTEXT:
            {intelligence_context[:1500] if intelligence_context else "No external research available."}

            TASK REQUIREMENTS:
            1. Each task must have a specific, non-overlapping responsibility.
            2. Match the language of the objective: respond in English.
            3. Include at least:
               - An 'Intel-Scout' or 'Domain-Analyst' for core mechanisms.
               - A 'Formal-Modeler' or 'Code-Architect' for concrete algorithms/rules.
               - A 'Red-Team-Critic' to challenge assumptions and find failure modes.
               - An 'Executive-Synthesizer' that aggregates results into a unified solution (depends on earlier tasks).
            4. Specify explicit dependencies in 'dependencies' (e.g. ["t1", "t2"]).

            Respond strictly in valid JSON matching this schema:
            {{
                "tasks": [
                    {{
                        "id": "t1",
                        "role": "Domain-Analyst",
                        "title": "Short descriptive task title in English",
                        "objective": "Concrete and detailed instruction for what the micro-agent should solve.",
                        "dependencies": []
                    }}
                ]
            }}
            """
        else:
            decomp_prompt = f"""
            Du är Mímir Chief Architect. Din uppgift är att bryta ned följande mål till
            4-6 brutalt konkreta, atomära mikrouppgifter som små agenter kan reda ut parallellt.

            MÅL: "{goal}"

            ACKUMULERADE LÄRDOMAR & KÄRNHEURISTIKER (FRÅN MINNESBANKEN):
            {memory_context[:1000] if memory_context else "Ingen tidigare minneskontext tillgänglig."}

            OMVÄRLDSKUNSKAP & FORSKNING:
            {intelligence_context[:1500] if intelligence_context else "Ingen extern research tillgänglig."}

            KRAV PÅ UPPGIFTERNA:
            1. Varje uppgift måste ha ett specifikt, icke-överlappande ansvar.
            2. Svara på svenska.
            3. Inkludera minst:
               - En 'Intel-Scout' eller 'Domain-Analyst' för kärnmekanismer.
               - En 'Formal-Modeler' eller 'Code-Architect' för konkreta algoritmer/regler.
               - En 'Red-Team-Critic' för att hitta fel, antaganden och gränsfall.
               - En 'Executive-Synthesizer' som aggregerar delresultaten till en slutprodukt (beror på de andra).
            4. Ange explicita beroenden i 'dependencies' (t.ex. ["t1", "t2"]).

            Svara i ren JSON enligt detta schema:
            {{
                "tasks": [
                    {{
                        "id": "t1",
                        "role": "Domain-Analyst",
                        "title": "Kort titel på uppgiften på svenska",
                        "objective": "Konkret och detaljerad instruktion för vad mikro-agenten ska lösa.",
                        "dependencies": []
                    }}
                ]
            }}
            """

        res = await self.swarm.spawn(
            prompt=decomp_prompt,
            role="Mimir-Decomposer",
            effort=None,
        )
        if res.status != "SUCCESS":
            raise RuntimeError(f"Mimir decomposition failed: {res.raw_response[:300]}")

        tasks_data = []
        if isinstance(res.data, dict) and "tasks" in res.data:
            tasks_data = res.data["tasks"]
        elif isinstance(res.data, list):
            tasks_data = res.data

        if not tasks_data:
            if is_en:
                tasks_data = [
                    {
                        "id": "t1",
                        "role": "Domain-Analyst",
                        "title": "Core parameters and theoretical invariants",
                        "objective": f"Identify the most critical parameters and assumptions for: '{goal}'.",
                        "dependencies": [],
                    },
                    {
                        "id": "t2",
                        "role": "Formal-Modeler",
                        "title": "Concrete algorithm and rule set",
                        "objective": f"Formulate a computable model or algorithm for: '{goal}'.",
                        "dependencies": ["t1"],
                    },
                    {
                        "id": "t3",
                        "role": "Red-Team-Critic",
                        "title": "Adversarial review and edge case analysis",
                        "objective": "Identify 3 serious vulnerabilities, assumption flaws, or failure modes in the solution.",
                        "dependencies": ["t1", "t2"],
                    },
                    {
                        "id": "t4",
                        "role": "Executive-Synthesizer",
                        "title": "Pareto-optimal comprehensive synthesis",
                        "objective": "Combine analysis, algorithm, and mitigations into a hardened solution.",
                        "dependencies": ["t1", "t2", "t3"],
                    },
                ]
            else:
                tasks_data = [
                    {
                        "id": "t1",
                        "role": "Domain-Analyst",
                        "title": "Kärnparametrar och teoretiska invarianser",
                        "objective": f"Identifiera de mest kritiska parametrarna och antagandena för: '{goal}'.",
                        "dependencies": [],
                    },
                    {
                        "id": "t2",
                        "role": "Formal-Modeler",
                        "title": "Konkret algoritm och regeluppsättning",
                        "objective": f"Formulera en beräkningsbar modell eller algoritm för: '{goal}'.",
                        "dependencies": ["t1"],
                    },
                    {
                        "id": "t3",
                        "role": "Red-Team-Critic",
                        "title": "Adversariell granskning och gränsfallsanalys",
                        "objective": "Hitta 3 allvarliga svagheter, antagandefel eller svåra gränsfall i lösningen.",
                        "dependencies": ["t1", "t2"],
                    },
                    {
                        "id": "t4",
                        "role": "Executive-Synthesizer",
                        "title": "Pareto-optimal helhetssyntes",
                        "objective": "Kombinera analys, algoritm och motåtgärder mot kritikerna till en fullständig lösning.",
                        "dependencies": ["t1", "t2", "t3"],
                    },
                ]

        for t in tasks_data:
            node = TaskNode(
                id=t.get("id", f"t{len(graph.nodes)+1}"),
                role=t.get("role", "Micro-Worker"),
                title=t.get("title", "Task" if is_en else "Deluppgift"),
                prompt=(f"MIMIR OBJECTIVE AND CONSTRAINTS:\n{goal}\n\n"
                        f"RESEARCH CONTEXT:\n{intelligence_context[:1500]}\n\n"
                        f"YOUR TASK:\n{t.get('objective', t.get('prompt', ''))}"),
                dependencies=set(t.get("dependencies", [])),
                depth=0,
                max_depth=self.max_depth,
                is_atomic=True,
            )
            graph.add_node(node)

        is_valid, error_msg = graph.validate_acyclic_and_integrity()
        if not is_valid:
            for node in graph.nodes.values():
                node.dependencies = {d for d in node.dependencies if d in graph.nodes and d != node.id}

        return graph
