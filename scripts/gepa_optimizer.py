"""
scripts/gepa_optimizer.py
Implements GEPA (Genetic-Pareto Reflective Evolution) using Mímir Swarm.
Uses reflection over execution traces/misses to evolve prompts, rules, or strategies.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from backend import BaseSwarmBackend, SwarmTask


@dataclass
class CandidateProgram:
    id: str
    content: str
    description: str
    scores: Dict[str, float] = field(default_factory=dict)
    reflections: List[str] = field(default_factory=list)
    generation: int = 0


@dataclass
class EvaluationSample:
    input_data: Any
    expected_output: Any
    context_notes: str = ""


class GepaOptimizer:
    """
    Reflective Genetic-Pareto optimizer powered by Mímir micro-agents.
    """

    def __init__(
        self,
        swarm: Any,
        critic_model: Optional[str] = None,
        max_generations: int = 2,
        pareto_keys: Optional[List[str]] = None,
    ):
        self.swarm = swarm
        self.critic_model = critic_model or getattr(swarm, "default_model", "gemini-3.8-flash-low")
        self.max_generations = max_generations
        self.pareto_keys = pareto_keys or ["primary_accuracy"]

    async def optimize(
        self,
        initial_candidates: List[CandidateProgram],
        eval_dataset: List[EvaluationSample],
        eval_fn: Callable[[CandidateProgram, EvaluationSample], Tuple[float, Dict[str, float], str]],
    ) -> List[CandidateProgram]:
        population = list(initial_candidates)

        for gen in range(self.max_generations):
            all_failures: Dict[str, List[Dict[str, Any]]] = {}

            for cand in population:
                total_primary = 0.0
                metric_sums: Dict[str, float] = {}
                failures = []

                for sample in eval_dataset:
                    score, sub_metrics, trace_feedback = eval_fn(cand, sample)
                    total_primary += score

                    for k, v in sub_metrics.items():
                        metric_sums[k] = metric_sums.get(k, 0.0) + v

                    if score < 0.99:
                        failures.append({
                            "input": sample.input_data,
                            "expected": sample.expected_output,
                            "notes": sample.context_notes,
                            "feedback": trace_feedback,
                        })

                n = max(len(eval_dataset), 1)
                cand.scores["primary_accuracy"] = round(total_primary / n, 3)
                for k, v in metric_sums.items():
                    cand.scores[k] = round(v / n, 3)

                all_failures[cand.id] = failures

            pareto_front = self._compute_pareto_front(population)

            if gen == self.max_generations - 1:
                return pareto_front

            mutation_tasks: List[SwarmTask] = []
            for cand in pareto_front:
                misses = all_failures.get(cand.id, [])
                if not misses:
                    continue

                sampled_misses = misses[:2]
                prompt = (
                    f"Du är en GEPA Reflektionskritiker. "
                    f"Här är en strategi/regel som testades:\n\n{cand.content}\n\n"
                    f"Följande fall misslyckades vid validering:\n"
                )
                for idx, m in enumerate(sampled_misses, 1):
                    prompt += f"Fall {idx}: Input={m['input']}, Förväntat={m['expected']}. Orsak: {m['feedback']}\n"

                prompt += (
                    f"\nUPPGIFT:\n"
                    f"1. Reflektera kort över varför strategin misslyckades på dessa fall.\n"
                    f"2. Föreslå en konkret MUTATION eller förfinad regel som fixar detta utan att förstöra helheten.\n"
                    f"Svara i ren JSON med nycklarna: 'reflection' (str) och 'mutated_content' (str)."
                )

                mutation_tasks.append(
                    SwarmTask(
                        role=f"GEPA-Critic-{cand.id}",
                        prompt=prompt,
                        model=self.critic_model,
                        effort="low",
                    )
                )

            if not mutation_tasks:
                return pareto_front

            results = await self.swarm.parallel(mutation_tasks)

            new_candidates = []
            for orig, res in zip(pareto_front, results):
                if res.status == "SUCCESS" and isinstance(res.data, dict):
                    mutated_text = res.data.get("mutated_content", "")
                    reflection_text = res.data.get("reflection", "")
                    if mutated_text:
                        new_cand = CandidateProgram(
                            id=f"{orig.id}_gen{gen+1}",
                            content=mutated_text,
                            description=f"Mutation av {orig.id}",
                            reflections=orig.reflections + [reflection_text],
                            generation=gen + 1,
                        )
                        new_candidates.append(new_cand)

            population = pareto_front + new_candidates

        return self._compute_pareto_front(population)

    async def reflective_evolve(
        self,
        candidate_content: str,
        goal: str,
        critique_points: str,
    ) -> Tuple[str, str]:
        prompt = f"""
        Du är Mímir GEPA-Reflektionskritiker.
        MÅL: "{goal}"

        FÖRESLAGEN LÖSNING / ALGORITM:
        {candidate_content}

        IDENTIFIERADE SVAGHETER & MOTSTÅNDARKRITIK (RED-TEAM):
        {critique_points}

        UPPGIFT:
        1. Analysera varför lösningen är sårbar för kritiken.
        2. Genomför en evolutionär MUTATION som täpper till luckorna och härdar lösningen
           utan att öka komplexiteten onödigt mycket (Pareto-effektivitet).

        Svara i ren JSON med nycklarna:
        - "reflection": Kort analys av svagheterna och vad som åtgärdats.
        - "hardened_solution": Den fullständiga, förbättrade lösningen.
        """

        res = await self.swarm.spawn(
            prompt=prompt,
            role="GEPA-Evolver",
            model=self.critic_model,
            effort="low",
        )

        if isinstance(res.data, dict) and "hardened_solution" in res.data:
            return res.data["hardened_solution"], res.data.get("reflection", "")

        return candidate_content, "Ingen strukturerad mutation kunde utföras."

    def _compute_pareto_front(self, candidates: List[CandidateProgram]) -> List[CandidateProgram]:
        front = []
        for i, c1 in enumerate(candidates):
            dominated = False
            for j, c2 in enumerate(candidates):
                if i != j:
                    c2_better_or_equal = all(
                        c2.scores.get(k, 0) >= c1.scores.get(k, 0) for k in self.pareto_keys
                    )
                    c2_strictly_better = any(
                        c2.scores.get(k, 0) > c1.scores.get(k, 0) for k in self.pareto_keys
                    )
                    if c2_better_or_equal and c2_strictly_better:
                        dominated = True
                        break
            if not dominated and c1 not in front:
                front.append(c1)
        return front
