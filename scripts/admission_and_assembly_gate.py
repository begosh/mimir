"""Deep module owning task result admission, coalesced checker batching, bounded task repair,
synthesis context assembly, one-correction final answer gating, and QuarantinedFinding overlays.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence, TypedDict

from backend import WorkerFailure
from evidence_provenance import (
    EvidenceProvenance,
    SOURCE_STATUSES,
    check_material_records,
    identity,
)
from mimir_config import ConfigurationRequired

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
INTERNAL = {
    "result_hash",
    "prompt_hash",
    "input_fingerprint",
    "policy",
    "input_hash",
    "result_check_hash",
    "result_attempts",
    "evidence_hash",
}


class QuarantinedFinding(TypedDict, total=False):
    status: str  # "quarantined" | "accepted"
    original_hash: str
    reason: str
    gaps: list[str]
    sources: list[dict[str, Any]]
    result: Any


# ---------------------------------------------------------------------------
# Model-Facing Prompt Views & Checker Context Compaction
# ---------------------------------------------------------------------------


def model_view(value: Any, sources: Sequence[Mapping[str, Any]] = ()) -> Any:
    """Strip internal hashes and redact workspace filesystem paths to source IDs."""
    aliases = {
        s["locator"]: s["id"]
        for s in sources
        if s.get("id")
        and isinstance(s.get("locator"), str)
        and re.match(r"^(?:[A-Za-z]:[\\/]|/)", s["locator"])
    }

    def clean(item: Any) -> Any:
        if isinstance(item, str):
            for path, alias in sorted(aliases.items(), key=lambda p: -len(p[0])):
                item = item.replace(path, alias)
            return item
        if isinstance(item, list):
            return [clean(v) for v in item]
        if isinstance(item, dict):
            return {k: clean(v) for k, v in item.items() if k not in INTERNAL}
        return item

    return clean(value)


def compact_checker_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Store each evidence text once; bind source references to each candidate."""
    ctx = deepcopy(dict(context))
    registry: list[dict[str, Any]] = []
    alias_sources: list[Mapping[str, Any]] = []

    def register(source: Mapping[str, Any]) -> dict[str, Any]:
        alias_sources.append(source)
        cleaned = model_view(source, [source])
        if cleaned not in registry:
            registry.append(cleaned)
        return {
            "ref": f"source_{registry.index(cleaned) + 1}",
            "id": cleaned.get("id"),
            "sha256": cleaned.get("sha256"),
        }

    shared = ctx.pop("supplied_sources", [])
    shared_refs = [register(s) for s in shared]
    for candidate in ctx.get("candidates", []):
        sources = candidate.pop("supplied_sources", [])
        candidate["source_refs"] = [register(s) for s in sources] or shared_refs
        candidate["result"] = model_view(candidate.get("result", {}), [*shared, *sources])
        if candidate["source_refs"]:
            for source in candidate["result"].get("sources", []):
                source.pop("support_excerpt", None)
        candidate["dependency_results"] = model_view(
            candidate.get("dependency_results", {}), [*shared, *sources]
        )
    if registry:
        ctx["source_registry"] = [{"ref": f"source_{i}", **s} for i, s in enumerate(registry, 1)]
    return model_view(ctx, alias_sources)


# ---------------------------------------------------------------------------
# Policies, Contracts & Schemas
# ---------------------------------------------------------------------------


def material_finding_contract(prompt: str) -> dict[str, Any]:
    """Keep the original assignment as the admission and repair contract."""
    return {
        "objective": prompt,
        "operation": "research",
        "inputs": ["assigned evidence and direct dependency results"],
        "expected_output": "Assigned answer with source-linked material claims, qualifications, conflicts and gaps",
        "acceptance_check": (
            "Address the original assignment; no unsupported factual additions or omitted material requirements. "
            "Preserve source qualifications, conflicts and gaps; model agreement is not independent verification."
        ),
    }


def result_gate_policy() -> dict[str, Any]:
    from prompt_governance_gate import PromptGovernanceGate
    return {
        "version": "bound_material_findings_v3",
        "prompt_hash": PromptGovernanceGate.default().get_template_digest("RESULT_CHECKER"),
    }


def result_repair_policy() -> dict[str, Any]:
    from prompt_governance_gate import PromptGovernanceGate
    return {
        "version": "rephrase_only_v1",
        "max_retries": 2,
        "prompt_hash": PromptGovernanceGate.default().get_template_digest("RESULT_REPAIR"),
    }


def assembly_repair_policy() -> dict[str, Any]:
    from prompt_governance_gate import PromptGovernanceGate
    return {
        "version": "publication_assembly_v2",
        "max_corrections": 1,
        "repair_prompt_hash": PromptGovernanceGate.default().get_template_digest("ASSEMBLY_REPAIR"),
        "checker_prompt_hash": PromptGovernanceGate.default().get_template_digest("FINAL_ANSWER_CHECK"),
    }


def checker_schema() -> dict[str, Any]:
    fields = {
        "id": {"type": "string"},
        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
        "issues": {"type": "array", "items": {"type": "string"}},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["checks"],
        "properties": {
            "checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(fields),
                    "properties": fields,
                },
            }
        },
    }


# ---------------------------------------------------------------------------
# Task Result Checking, Coalesced Batching & Bounded Task Repair
# ---------------------------------------------------------------------------


async def check_results(backend: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    from prompt_governance_gate import PromptGovernanceGate
    compacted = compact_checker_context(context)
    prompt = PromptGovernanceGate.default().render_template("RESULT_CHECKER", context=compacted)
    response = await backend.spawn_restricted(
        prompt=prompt,
        role="Mimir-Result-Checker",
        model=backend.default_model,
        effort=backend.default_effort,
        json_schema=checker_schema(),
    )
    if response.status != "SUCCESS":
        raise WorkerFailure("Result checking", response.raw_response)
    data = response.data
    from jsonschema import validate

    validate(data, checker_schema())
    ids = [item["id"] for item in data["checks"]]
    expected = [item["id"] for item in compacted["candidates"]]
    if len(ids) != len(set(ids)) or set(ids) != set(expected) or len(expected) != len(set(expected)):
        raise ValueError("Checker omitted, duplicated or invented candidates")
    if any(
        (item["verdict"] == "PASS" and item["issues"])
        or (item["verdict"] == "FAIL" and not item["issues"])
        for item in data["checks"]
    ):
        raise ValueError("Checker returned contradictory verdict and issues")
    return data


async def check_task_result(
    backend: Any,
    node: Any,
    result: Any,
    dependency_results: Mapping[str, Any],
) -> dict[str, Any]:
    from atomic_worker import worker_contract

    context = {
        "supplied_sources": node.input_artifacts.get("supplied_sources", []),
        "dependency_results": dependency_results,
        "candidates": [
            {
                "id": "candidate_1",
                "contract": worker_contract(node.input_artifacts["task_contract"]),
                "result": result,
            }
        ],
    }
    checked = await check_results(backend, context)
    return {**checked["checks"][0], "policy": result_gate_policy()}


async def repair_task_result(backend: Any, node: Any, rejection: Mapping[str, Any]) -> dict[str, Any]:
    context = {
        "contract": node.input_artifacts["task_contract"],
        "failed_result": rejection["result"],
        "feedback": rejection["result_check"]["issues"],
        "retry": node.retry_count,
        "max_retries": 2,
    }
    prompt = (
        (PROMPTS / "RESULT_REPAIR.txt")
        .read_text(encoding="utf-8")
        .replace(
            "{{context}}",
            json.dumps(
                model_view(context, node.input_artifacts.get("supplied_sources", [])),
                ensure_ascii=False,
            ),
        )
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "objective", "reason"],
        "properties": {
            "action": {"type": "string", "enum": ["REPHRASE", "BLOCKED", "STOP"]},
            "objective": {"type": "string", "maxLength": 500},
            "reason": {"type": "string", "minLength": 1, "maxLength": 500},
        },
    }
    response = await backend.spawn_restricted(
        prompt=prompt,
        role="Mimir-Result-Repairer",
        model=backend.default_model,
        effort=backend.default_effort,
        json_schema=schema,
    )
    if response.status != "SUCCESS":
        raise WorkerFailure("Result repair", response.raw_response)
    from jsonschema import validate

    validate(response.data, schema)
    proposal = response.data
    if (proposal["action"] == "REPHRASE") != bool(proposal["objective"].strip()):
        raise ValueError("Repair objective contradicts action")
    return proposal


class ResultBatcher:
    """Bounded coalescing of completed results, with individual admission verdicts."""

    def __init__(self, backend: Any, *, size: int = 4, delay: float = 2.0) -> None:
        self.backend = backend
        self.size = min(4, max(1, size))
        self.delay = delay
        self.pending: list[tuple[Any, Any, Any, asyncio.Future]] = []
        self.timer: asyncio.TimerHandle | None = None
        self.tasks: set[asyncio.Task] = set()

    async def check(self, node: Any, result: Any, dependencies: Mapping[str, Any]) -> dict[str, Any]:
        future = asyncio.get_running_loop().create_future()
        self.pending.append((node, result, dependencies, future))
        if len(self.pending) >= self.size:
            self.flush()
        elif self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(self.delay, self.flush)
        return await future

    def flush(self) -> None:
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if not self.pending:
            return
        batch, self.pending = self.pending[: self.size], self.pending[self.size :]
        task = asyncio.create_task(self.run(batch))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        if self.pending:
            self.flush()

    async def run(self, batch: list[tuple[Any, Any, Any, asyncio.Future]]) -> None:
        from atomic_worker import worker_contract

        candidates = [
            {
                "id": f"candidate_{i}",
                "contract": worker_contract(node.input_artifacts["task_contract"]),
                "result": result,
                "supplied_sources": node.input_artifacts.get("supplied_sources", []),
                "dependency_results": dependencies,
            }
            for i, (node, result, dependencies, _) in enumerate(batch, 1)
        ]
        try:
            checked = await check_results(self.backend, {"candidates": candidates})
            verdicts = {v["id"]: v for v in checked["checks"]}
            for i, (_, _, _, future) in enumerate(batch, 1):
                if not future.done():
                    future.set_result({**verdicts[f"candidate_{i}"], "policy": result_gate_policy()})
        except (Exception, asyncio.CancelledError) as exc:
            for _, _, _, future in batch:
                if not future.done():
                    if isinstance(exc, asyncio.CancelledError):
                        future.cancel()
                    else:
                        future.set_exception(exc)

    async def close(self) -> None:
        if self.timer:
            self.timer.cancel()
        for _, _, _, future in self.pending:
            if not future.done():
                future.cancel()
        self.pending.clear()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Publication View, Synthesis, Final Answer Checking & Assembly Repair
# ---------------------------------------------------------------------------


def build_publication_view(
    context: Mapping[str, Any],
    quarantines: Sequence[Mapping[str, Any]] = (),
) -> dict[str, QuarantinedFinding]:
    """Publication status overlays preserve immutable worker records."""
    results = {**context.get("findings", {}), **context.get("checks", {}).get("critic_findings", {})}
    selected: dict[str, str] = {}
    for entry in quarantines:
        task_id, reason = entry["task_id"], entry["reason"]
        if task_id not in results or task_id in selected or not reason.strip():
            raise ValueError("Publication quarantine requires a unique existing task and reason")
        selected[task_id] = reason
    view: dict[str, QuarantinedFinding] = {}
    for task_id, result in results.items():
        item: QuarantinedFinding = {
            "status": "quarantined" if task_id in selected else "accepted",
            "original_hash": identity(result),
        }
        if task_id in selected:
            item.update(
                reason=selected[task_id],
                gaps=deepcopy(result.get("gaps", [])) if isinstance(result, dict) else [],
                sources=deepcopy(result.get("sources", [])) if isinstance(result, dict) else [],
            )
        else:
            item["result"] = deepcopy(result)
        view[task_id] = item
    return view


def synthesis_context(state: Mapping[str, Any]) -> dict[str, Any]:
    completed = state.get("completed_data", {})
    nodes = (state.get("graph") or {}).get("nodes", {})
    if isinstance(nodes, list):
        nodes = {n["id"]: n for n in nodes}
    scope = list((state.get("task_brief") or {}).get("constraints", []))
    domain = (state.get("planning_trace") or {}).get("domain_rules", "")
    if domain:
        scope.append(domain)
    rules = state.get("scope_rules", [])
    scope.extend([rules] if isinstance(rules, str) else rules)
    coverage = dict(state.get("component_coverage", {}))
    for node_id in dict.fromkeys([*nodes, *completed]):
        check = completed.get(node_id, {}).get("result_check") or state.get("result_checks", {}).get(node_id)
        coverage.setdefault(
            node_id,
            check.get("verdict", "RETURNED")
            if isinstance(check, dict)
            else "RETURNED"
            if node_id in completed
            else "NOT RUN",
        )
    sources, supplied, findings, critiques = EvidenceProvenance.from_state(state).build_synthesis_registry(state)
    from task_graph import separate_review_assignments

    request, assignments = (
        separate_review_assignments(state.get("goal", ""))
        if state.get("mode") == "review"
        else (state.get("goal", ""), {})
    )
    if assignments.get("synthesis"):
        scope.append("Assigned synthesis deliverable: " + assignments["synthesis"])
    context = {
        "request": request,
        "scope": scope,
        "coverage": {
            "components": coverage,
            "intended_components": (state.get("task_brief") or {}).get("components", []),
        },
        "sources": sources,
        "findings": findings,
        "checks": {
            "result_checks": {
                **state.get("result_checks", {}),
                **{
                    node_id: envelope["result_check"]
                    for node_id, envelope in completed.items()
                    if envelope.get("result_check")
                },
            },
            "critic_findings": critiques,
        },
    }
    context = model_view(context, supplied)
    for result in [*context["findings"].values(), *context["checks"]["critic_findings"].values()]:
        if isinstance(result, dict):
            for source in result.get("sources", []):
                source.pop("support_excerpt", None)
    return context


async def synthesize(
    backend: Any,
    context: Mapping[str, Any],
    *,
    model: str | None = None,
    max_answer_words: int | None = None,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    prompt = (PROMPTS / "SYNTHESIZER.txt").read_text(encoding="utf-8")
    values = {k: json.dumps(v, ensure_ascii=False) for k, v in context.items()}
    values["word_limit"] = (
        f"Answer at most {max_answer_words} whitespace-separated words." if max_answer_words else ""
    )
    prompt = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m[1]], prompt)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "limitations"],
        "properties": {
            "answer": {"type": "string"},
            "limitations": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "maxLength": 600},
            },
        },
    }
    native = getattr(backend, "native", backend)
    dispatch = backend.spawn_restricted if hasattr(native, "spawn_restricted") else backend.spawn
    response = await dispatch(
        prompt=prompt,
        role="Mimir-Synthesizer",
        model=model or backend.default_model,
        effort=backend.default_effort,
        json_schema=schema,
    )
    if response.status != "SUCCESS":
        raise WorkerFailure("Answer synthesis", response.raw_response)
    from jsonschema import validate

    validate(response.data, schema)
    answer = response.data["answer"]
    if not answer.strip():
        raise ValueError("Synthesis returned an empty answer")
    if max_answer_words and len(answer.split()) > max_answer_words:
        rejected = {
            "result": response.data,
            "raw_response": response.raw_response,
            "tokens_used": response.tokens_used,
            "reason": "Synthesis exceeds compact word limits",
        }
        for call in getattr(backend, "usage_calls", []):
            if call.get("operation_id") == response.operation_id:
                call.update(status="ERROR", rejected_output=rejected)
                backend.event(dict(call))
        raise ValueError("Synthesis exceeds compact word limits; original output retained without publication")
    return response.data, context


async def check_final_answer(
    backend: Any,
    context: Mapping[str, Any],
    assembled: Any,
    *,
    model: str | None = None,
    publication_view: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"task_context": context, "assembled": assembled}
    if publication_view is not None:
        payload["publication_view"] = publication_view
    conflict_verdict = EvidenceProvenance.verify_conflict_preservation(assembled, context)
    if conflict_verdict.failed:
        return {
            "verdict": "FAIL",
            "issues": list(conflict_verdict.issues),
            "policy": {
                "version": "final_answer_v1",
                "prompt_hash": hashlib.sha256((PROMPTS / "FINAL_ANSWER_CHECK.txt").read_bytes()).hexdigest(),
            },
            "input_hash": hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest(),
            "check_type": conflict_verdict.check_type,
        }
    prompt = (
        (PROMPTS / "FINAL_ANSWER_CHECK.txt")
        .read_text(encoding="utf-8")
        .replace("{{context}}", json.dumps(payload, ensure_ascii=False))
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "issues"],
        "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "issues": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "minLength": 1, "maxLength": 600},
            },
        },
    }
    native = getattr(backend, "native", backend)
    dispatch = backend.spawn_restricted if hasattr(native, "spawn_restricted") else backend.spawn
    response = await dispatch(
        prompt=prompt,
        role="Mimir-Final-Checker",
        model=model or backend.default_model,
        effort=backend.default_effort,
        json_schema=schema,
    )
    if response.status != "SUCCESS":
        raise WorkerFailure("Final answer checking", response.raw_response)
    from jsonschema import validate

    validate(response.data, schema)
    verdict = response.data
    if (verdict["verdict"] == "PASS") != (verdict["issues"] == []):
        raise ValueError("Final checker returned contradictory verdict and issues")
    return {
        **verdict,
        "policy": {
            "version": "final_answer_v1",
            "prompt_hash": hashlib.sha256((PROMPTS / "FINAL_ANSWER_CHECK.txt").read_bytes()).hexdigest(),
        },
        "input_hash": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    }


async def repair_assembled_answer(
    backend: Any,
    context: Mapping[str, Any],
    assembled: Any,
    feedback: Any,
    *,
    model: str | None = None,
    max_answer_words: int | None = None,
    publication: bool = False,
) -> dict[str, Any]:
    payload = {
        "task_context": context,
        "rejected_answer": assembled,
        "feedback": feedback,
        "max_answer_words": max_answer_words,
    }
    prompt = (
        (PROMPTS / "ASSEMBLY_REPAIR.txt")
        .read_text(encoding="utf-8")
        .replace("{{context}}", json.dumps(payload, ensure_ascii=False))
    )
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "limitations"],
        "properties": {
            "answer": {"type": "string", "minLength": 1},
            "limitations": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "maxLength": 600},
            },
        },
    }
    if publication:
        schema["required"].append("quarantined_tasks")
        schema["properties"]["quarantined_tasks"] = {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["task_id", "reason"],
                "properties": {
                    "task_id": {"type": "string"},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 600},
                },
            },
        }
    response = await backend.spawn_restricted(
        prompt=prompt,
        role="Mimir-Assembly-Repairer",
        model=model or backend.default_model,
        effort=backend.default_effort,
        json_schema=schema,
    )
    if response.status != "SUCCESS":
        raise WorkerFailure("Assembly correction", response.raw_response)
    from jsonschema import validate

    try:
        validate(response.data, schema)
        if publication:
            build_publication_view(context, response.data["quarantined_tasks"])
        if not response.data["answer"].strip() or (
            max_answer_words and len(response.data["answer"].split()) > max_answer_words
        ):
            raise ValueError("Assembly correction exceeds answer limits or is empty")
    except Exception as exc:
        response.rejected_output = {
            "result": response.data,
            "raw_response": response.raw_response,
            "reason": "Invalid assembly correction",
        }
        for call in getattr(backend, "usage_calls", []):
            if call.get("operation_id") == response.operation_id:
                call.update(status="ERROR", rejected_output=response.rejected_output)
                backend.event(dict(call))
        exc.rejected_output = response.rejected_output  # type: ignore[attr-defined]
        raise
    return response.data


async def assemble_checked(
    backend: Any,
    context: Mapping[str, Any],
    state: dict[str, Any],
    persist: Callable[[], None],
    emit: Callable[..., None],
    *,
    model: str | None,
    max_answer_words: int | None = None,
    _policy_fn: Callable[[], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Persisted one-correction final gate; interruptions never reset its allowance."""
    policy_getter = _policy_fn or assembly_repair_policy
    policy = policy_getter()
    binding = identity(
        {
            "context": context,
            "model": model,
            "effort": backend.default_effort,
            "max_answer_words": max_answer_words,
            "policy": policy,
        }
    )
    history = state.get("assembly_history")
    if history:
        if history.get("binding") != binding or history.get("policy") != policy:
            raise ConfigurationRequired("Assembly inputs or checker/repair policy changed; replan explicitly")
        if history.get("identity") != identity({k: v for k, v in history.items() if k != "identity"}):
            raise ConfigurationRequired("Assembly history identity changed; replan explicitly")
        if history["stage"] in {"synthesizing", "checking", "repairing", "rechecking", "failed"}:
            raise WorkerFailure(
                "Final answer",
                "Assembly attempt interrupted or exhausted; retained versions require review and a new run",
            )
    else:
        history = {
            "binding": binding,
            "policy": policy,
            "corrections_reserved": 0,
            "versions": [],
            "stage": "new",
        }
        state["assembly_history"] = history

    def save(stage: str) -> None:
        history["stage"] = stage
        history["identity"] = identity({k: v for k, v in history.items() if k != "identity"})
        persist()

    try:
        if history["stage"] == "new":
            save("synthesizing")
            assembled, _ = await synthesize(backend, context, model=model, max_answer_words=max_answer_words)
            history["versions"].append(
                {
                    "kind": "original",
                    "result": deepcopy(assembled),
                    "publication_view": build_publication_view(context),
                }
            )
            save("assembled")
        if history["stage"] == "passed":
            version = history["versions"][-1]
            state["publication_view"] = deepcopy(version["publication_view"])
            return deepcopy(version["result"]), deepcopy(version["check"])
        version = history["versions"][-1]
        if history["stage"] in {"assembled", "corrected"}:
            save("rechecking" if history["corrections_reserved"] else "checking")
            emit("final_check_started")
            check = await check_final_answer(
                backend,
                context,
                version["result"],
                model=model,
                publication_view=version["publication_view"],
            )
            version["check"] = deepcopy(check)
            state["final_answer_check"] = check
            emit("final_check_completed", verdict=check["verdict"], issues=check["issues"])
            if check["verdict"] == "PASS":
                state["publication_view"] = deepcopy(version["publication_view"])
                save("passed")
                state.pop("rejected_synthesis", None)
                persist()
                return deepcopy(version["result"]), check
            state["rejected_synthesis"] = {
                "result": deepcopy(version["result"]),
                "result_check": check,
                "reason": "Final answer acceptance check failed",
            }
            save("rejected")
        if history["corrections_reserved"]:
            save("failed")
            raise WorkerFailure("Final answer", "Acceptance check failed after the single assembly correction")
        history["corrections_reserved"] = 1
        save("repairing")  # Durable reservation before the paid correction call.
        emit("assembly_correction_started")
        corrected = await repair_assembled_answer(
            backend,
            context,
            version["result"],
            version["check"]["issues"],
            model=model,
            max_answer_words=max_answer_words,
            publication=True,
        )
        quarantines = corrected.pop("quarantined_tasks")
        history["versions"].append(
            {
                "kind": "correction",
                "result": deepcopy(corrected),
                "publication_view": build_publication_view(context, quarantines),
            }
        )
        save("corrected")
        emit("assembly_correction_completed")
        return await assemble_checked(
            backend,
            context,
            state,
            persist,
            emit,
            model=model,
            max_answer_words=max_answer_words,
            _policy_fn=policy_getter,
        )
    except BaseException as exc:
        if getattr(exc, "rejected_output", None):
            history["rejected_correction"] = deepcopy(exc.rejected_output)  # type: ignore[attr-defined]
        if history["versions"] and not state.get("rejected_synthesis"):
            state["rejected_synthesis"] = {
                "result": deepcopy(history["versions"][-1]["result"]),
                "checker_error": str(exc),
                "reason": "Assembly did not pass its final gate",
            }
        save(history["stage"])
        raise


def project_published_results(
    completed_data: Mapping[str, Any],
    publication_view: Mapping[str, Any],
) -> dict[str, Any]:
    """Project completed_data through publication_view, replacing quarantined tasks with diagnostic stubs."""
    published_data: dict[str, Any] = {}
    for node_id, data in completed_data.items():
        entry = publication_view.get(node_id, {})
        if entry.get("status") == "quarantined":
            published_data[node_id] = {
                **data,
                "result": {
                    "answer": "Quarantined task assertions; see publication status and original diagnostic record.",
                    "sources": entry["sources"],
                    "claims": [],
                    "gaps": entry["gaps"] + [entry["reason"]],
                },
            }
        else:
            published_data[node_id] = data
    return published_data


# ---------------------------------------------------------------------------
# Primary Deep Module: AdmissionAndAssemblyGate
# ---------------------------------------------------------------------------


class AdmissionAndAssemblyGate:
    """Deep module owning task admission, coalesced result checking, bounded 2-retry task repair,
    synthesis context construction, one-correction final assembly gating, and QuarantinedFinding overlays.
    """

    def __init__(
        self,
        backend: Any = None,
        *,
        provenance: EvidenceProvenance | None = None,
        batch_size: int | None = None,
        batch_delay: float = 2.0,
    ) -> None:
        self.backend = backend
        self.provenance = provenance or EvidenceProvenance()
        limit = getattr(backend, "max_concurrency", 4) if backend is not None else 4
        effective_size = batch_size if batch_size is not None else min(limit if isinstance(limit, int) and limit > 0 else 4, 4)
        self.batcher: ResultBatcher | None = (
            ResultBatcher(backend, size=effective_size, delay=batch_delay)
            if backend is not None and getattr(backend, "batch_result_checks", False)
            else None
        )

    async def __aenter__(self) -> "AdmissionAndAssemblyGate":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self.batcher is not None:
            await self.batcher.close()

    # --- Stage 1: Pre-Execution Contract & Policy Binding ---

    @staticmethod
    def bind_node_policies(node: Any, *, mode: str | None = None) -> None:
        """Attach material finding contract, result gate policy, and repair policy to a task node."""
        if mode and not node.input_artifacts.get("task_contract"):
            node.input_artifacts["task_contract"] = material_finding_contract(node.prompt)
        if mode or node.input_artifacts.get("worker_wrapper") == "atomic_v1":
            node.input_artifacts["result_gate"] = result_gate_policy()
            node.input_artifacts["result_repair"] = result_repair_policy()

    @classmethod
    def bind_graph_policies(cls, graph: Any, *, mode: str | None = None) -> None:
        """Bind contracts and admission/repair policies across all nodes in a TaskGraph."""
        for node in graph.nodes.values():
            cls.bind_node_policies(node, mode=mode)

    # --- Stage 2: Task Admission, Coalescing & Bounded Repair ---

    async def evaluate_candidate(
        self,
        node: Any,
        result_data: Any,
        dependency_results: Mapping[str, Any],
        *,
        fingerprint: str,
    ) -> dict[str, Any]:
        """Run deterministic provenance + calculation checks, then coalesced or direct model result check."""
        prov_verdict = self.provenance.verify_task_result(result_data, node=node)
        record_check = prov_verdict.to_dict()
        if not prov_verdict.failed and node.input_artifacts.get("task_contract", {}).get("operation") == "calculate":
            from formula_engine import check_calculation

            record_check = check_calculation(result_data, node, dict(dependency_results))
        if record_check["verdict"] == "FAIL":
            review: dict[str, Any] = {
                "id": "candidate_1",
                "verdict": "FAIL",
                "issues": record_check["issues"],
                "policy": result_gate_policy(),
                "check_type": record_check.get("check_type", "deterministic_records"),
            }
        elif self.batcher is not None:
            review = await self.batcher.check(node, result_data, dependency_results)
        else:
            review = await check_task_result(self.backend, node, result_data, dependency_results)
        review.update(result_hash=identity(result_data), input_fingerprint=fingerprint)
        return review

    async def admit_or_repair_task(
        self,
        node: Any,
        response: Any,
        results: Mapping[str, Any],
        *,
        fingerprint: str,
        prompt: str,
        goal: str = "",
        on_result_attempt: Callable[[Any], None] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Gate a completed worker response; on FAIL within the 2-retry allowance, reserve retry and
        return (review, next_prompt) when REPHRASE is proposed, or (review, None) otherwise.
        """
        if not node.input_artifacts.get("result_gate"):
            return None, None
        if node.input_artifacts["result_gate"] != result_gate_policy():
            raise ConfigurationRequired("Result-check policy changed; replan explicitly")

        dep_results = {dep: results[dep]["result"] for dep in sorted(node.dependencies)}
        checker_valid = False
        try:
            review = await self.evaluate_candidate(
                node,
                response.data,
                dep_results,
                fingerprint=fingerprint,
            )
            checker_valid = True
        except (Exception, asyncio.CancelledError) as exc:
            node.rejected_output = {
                "result": deepcopy(response.data),
                "raw_response": response.raw_response,
                "tokens_used": response.tokens_used,
                "reason": "Result checker did not return a valid verdict",
                "checker_error": str(exc),
            }
            if isinstance(exc, (asyncio.CancelledError, ConfigurationRequired)):
                raise
            review = {"verdict": "FAIL", "issues": ["Result checker failed: " + str(exc)]}

        if review["verdict"] != "PASS":
            node.rejected_output = {
                "result": deepcopy(response.data),
                "raw_response": response.raw_response,
                "tokens_used": response.tokens_used,
                "reason": "Task acceptance check failed",
                "result_check": review,
            }
            response.status = "ERROR"
            response.raw_response = "Task acceptance check failed: " + "; ".join(review["issues"])

        node.result_attempts.append(
            {
                "attempt": node.retry_count + 1,
                "status": review["verdict"],
                "result": deepcopy(response.data),
                "raw_response": (
                    response.raw_response
                    if response.status == "SUCCESS"
                    else node.rejected_output["raw_response"]
                ),
                "result_check": deepcopy(review),
                "prompt": prompt,
            }
        )
        if on_result_attempt:
            on_result_attempt(node)

        repair_policy = node.input_artifacts.get("result_repair")
        if checker_valid and review["verdict"] == "FAIL" and repair_policy and node.retry_count < 2:
            if repair_policy != result_repair_policy():
                raise ConfigurationRequired("Result-repair policy changed; replan explicitly")
            node.retry_count += 1  # Persist reservation before making a paid call.
            if on_result_attempt:
                on_result_attempt(node)
            try:
                proposal = await repair_task_result(self.backend, node, node.rejected_output)
            except (Exception, asyncio.CancelledError) as exc:
                node.result_attempts[-1]["repair_error"] = str(exc)
                if on_result_attempt:
                    on_result_attempt(node)
                if isinstance(exc, (ConfigurationRequired, asyncio.CancelledError)):
                    raise
                proposal = {"action": "STOP", "objective": "", "reason": "Repair failed: " + str(exc)}
            node.result_attempts[-1]["repair"] = proposal
            if on_result_attempt:
                on_result_attempt(node)
            if proposal["action"] == "REPHRASE":
                assignment = {**node.input_artifacts["task_contract"], "objective": proposal["objective"]}
                if node.input_artifacts.get("worker_wrapper") == "atomic_v1":
                    from atomic_worker import atomic_prompt

                    next_prompt = atomic_prompt(assignment, original_request=goal)
                else:
                    next_prompt = (
                        node.prompt + "\nTARGETED REPAIR (original assignment unchanged):\n" + proposal["objective"]
                    )
                next_prompt += "\nORIGINAL ACCEPTANCE CONTRACT (unchanged):\n" + json.dumps(
                    node.input_artifacts["task_contract"],
                    ensure_ascii=False,
                )
                return review, next_prompt
            response.raw_response += "; " + proposal["action"] + ": " + proposal["reason"]

        return review, None

    # --- Stage 3: Checked Assembly, 1-Correction Repair & Quarantine Overlay ---

    async def assemble_publication(
        self,
        state: dict[str, Any],
        *,
        persist: Callable[[], None],
        emit: Callable[..., None],
        model: str | None = None,
    ) -> tuple[Any, str, dict[str, Any]]:
        """Assemble or validate the final answer (single-worker or multi-worker), persist assembly_history
        and publication_view, and return (hardened_solution, reflection, published_data).
        """
        completed_data = state.get("completed_data", {})
        if state.get("mode") == "single":
            envelope = next(iter(completed_data.values()))
            check = envelope.get("result_check", {})
            if check.get("verdict") != "PASS" or check.get("policy") != result_gate_policy():
                raise ConfigurationRequired(
                    "Single publication requires a current accepted material-finding check; replan explicitly."
                )
            normalized = EvidenceProvenance.normalize_result(envelope["result"])
            hardened_solution = normalized["answer"]
            state["synthesis_result"] = {"answer": hardened_solution, "limitations": normalized["gaps"]}
            state["final_answer_check"] = {
                **check,
                "check_scope": "Existing single answer plus gaps; no synthesis transformation",
            }
            reflection = "Single-worker report; no separate critique or reflective model call was performed."
            if normalized["gaps"]:
                reflection += "\n" + "\n".join(normalized["gaps"])
            state["publication_view"] = build_publication_view(synthesis_context(state))
        else:
            context = synthesis_context(state)
            state["synthesis_context"] = context
            try:
                synthesis_result, final_check = await assemble_checked(
                    self.backend,
                    context,
                    state,
                    persist,
                    emit,
                    model=model,
                    max_answer_words=300 if state.get("mode") == "review" else None,
                )
                state["synthesis_result"] = synthesis_result
                state["final_answer_check"] = final_check
                hardened_solution = synthesis_result["answer"]
                reflection = "Answer assembled from supplied findings; no separate reflective model call."
                if state["assembly_history"]["corrections_reserved"]:
                    reflection += " One targeted assembly correction passed rechecking; rejected assembly retained in the checkpoint."
                if synthesis_result["limitations"]:
                    reflection += "\n" + "\n".join(synthesis_result["limitations"])
            finally:
                persist()

        published_data = project_published_results(completed_data, state.get("publication_view", {}))
        return hardened_solution, reflection, published_data

    # Static conveniences
    material_finding_contract = staticmethod(material_finding_contract)
    result_gate_policy = staticmethod(result_gate_policy)
    result_repair_policy = staticmethod(result_repair_policy)
    assembly_repair_policy = staticmethod(assembly_repair_policy)
    checker_schema = staticmethod(checker_schema)
    check_results = staticmethod(check_results)
    check_task_result = staticmethod(check_task_result)
    repair_task_result = staticmethod(repair_task_result)
    synthesis_context = staticmethod(synthesis_context)
    synthesize = staticmethod(synthesize)
    check_final_answer = staticmethod(check_final_answer)
    repair_assembled_answer = staticmethod(repair_assembled_answer)
    assemble_checked = staticmethod(assemble_checked)
    build_publication_view = staticmethod(build_publication_view)
    project_published_results = staticmethod(project_published_results)
    model_view = staticmethod(model_view)
    compact_checker_context = staticmethod(compact_checker_context)
