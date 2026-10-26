"""Dependency-ready DAG execution with validated retained results.

Runtime adapters only execute workers. This module owns readiness, output
identity, failure propagation and joined cancellation. A synchronous commit
callback runs before downstream admission so callers can persist complete
results before their dependents consume them.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from admission_and_assembly_gate import AdmissionAndAssemblyGate
from backend import SwarmResult, has_worker_result, worker_diagnostic
from evidence_provenance import EvidenceProvenance, identity as _identity
from mimir_config import ConfigurationRequired
from task_graph import EvidenceContract, TaskStatus


def input_fingerprint(node: Any, dependency_results: dict, backend: Any,
                      *, goal: str = "") -> str:
    """Identify all persisted inputs controlling task execution; never keys."""
    profile = {"adapter": getattr(backend, "native", backend).__class__.__name__,
               "model": getattr(node, "model", None) or backend.default_model,
               "effort": getattr(node, "effort", None) or backend.default_effort,
               "execution_identity": getattr(backend, "execution_identity", None),
               "workspace": str(Path.cwd().resolve())}
    for name in ("base_url", "api_base", "endpoint", "worker_transport"):
        value = getattr(backend, name, None)
        if isinstance(value, (str, int, float, bool)):
            profile[name] = value
    return _identity({"version": 1, "goal": goal, "id": node.id,
                      "role": node.role, "title": node.title, "prompt": node.prompt,
                      "schema": getattr(node, "json_schema", None),
                      **({"max_answer_words": node.max_answer_words} if node.max_answer_words is not None else {}),
                      "input_artifacts": node.input_artifacts, "profile": profile,
                      "dependencies": {dep: {"evidence_hash": dependency_results[dep]["evidence_hash"],
                                             "result_hash": dependency_results[dep]["result_hash"]}
                                       for dep in sorted(node.dependencies)}})


def _contract(node: Any, envelope: dict, backend: Any) -> EvidenceContract:
    return EvidenceContract(
        grounding_ref=f"node://{node.id}", raw_evidence_hash=envelope["evidence_hash"],
        verification_passed=False,
        assertion_notes=f"Worker output identity recorded via {backend.__class__.__name__}; factual claims have not been independently verified.",
    )


def _register(node: Any, envelope: dict, backend: Any, blackboard: Any) -> EvidenceContract:
    contract = _contract(node, envelope, backend)
    if blackboard is not None:
        blackboard.register_evidence(envelope["raw_response"])
        if not blackboard.commit_evidence(node_id=node.id, key=f"{node.id}_result",
                                          value=envelope["result"], contract=contract):
            raise ValueError("Blackboard rejected worker output provenance")
        identities = getattr(blackboard, "input_identities", None)
        if isinstance(identities, dict):
            identities[node.id] = envelope["input_fingerprint"]
    return contract


def _restore(graph: Any, backend: Any, blackboard: Any, retained: dict,
             *, provenance: EvidenceProvenance | None = None) -> dict:
    completed = {nid for nid, node in graph.nodes.items() if node.status == TaskStatus.COMPLETED}
    if completed != set(retained):
        raise ValueError("Retained results must match completed tasks; partial execution resume requires complete provenance.")
    prov = provenance or EvidenceProvenance(
        workspace=getattr(backend, "workspace", Path.cwd()),
        allowed_domains=getattr(backend, "capture_allowed_domains", ()),
    )
    results = {}
    for tier in graph.get_execution_tiers():
        for node in tier:
            if node.id not in completed:
                continue
            envelope = retained[node.id]
            if not isinstance(envelope, dict):
                raise ValueError("Invalid retained result envelope")
            if not node.dependencies.issubset(results):
                raise ValueError("Retained task has an incomplete dependency.")
            prov.restore_task_evidence(node, envelope, results)
            if (not isinstance(envelope, dict) or not has_worker_result(envelope.get("result"))
                    or not isinstance(envelope.get("raw_response"), str)
                    or hashlib.sha256(envelope["raw_response"].encode("utf-8")).hexdigest() != envelope.get("evidence_hash")
                    or _identity(envelope["result"]) != envelope.get("result_hash")
                    or _identity(node.output_data) != envelope.get("result_hash")
                    or input_fingerprint(node, results, backend, goal=graph.goal) != envelope.get("input_fingerprint")):
                raise ValueError(f"Retained task '{node.id}' has changed inputs or invalid output identity; replan explicitly.")
            policy = node.input_artifacts.get("result_gate")
            if policy:
                prov.verify_retained_citations(node, envelope)
                review = envelope.get("result_check", {})
                if (review.get("verdict") != "PASS" or review.get("issues") != [] or
                        review.get("policy") != policy or review.get("result_hash") != envelope["result_hash"] or
                        review.get("input_fingerprint") != envelope["input_fingerprint"] or
                        _identity(review) != envelope.get("result_check_hash")):
                    raise ValueError(f"Retained task '{node.id}' has missing or changed result-check identity; replan explicitly.")
            results[node.id] = deepcopy(envelope)
    # All fingerprints are validated before publishing any retained outputs.
    for nid, envelope in results.items():
        _register(graph.nodes[nid], envelope, backend, blackboard)
    return results


def validate_retained(graph: Any, backend: Any, retained: dict) -> None:
    """Validate retained outputs and execution inputs without mutating storage."""
    valid, message = graph.validate_acyclic_and_integrity()
    if not valid:
        raise ValueError(f"Invalid retained execution graph: {message}")
    _restore(graph, backend, None, retained)


async def execute_graph(graph: Any, backend: Any, *, blackboard: Any = None,
                        jev_gate: Any = None, on_task_start: Callable | None = None,
                        on_task_finish: Callable | None = None, retained_results: dict | None = None,
                        on_result_commit: Callable | None = None,
                        on_result_attempt: Callable | None = None,
                        research_dispatch: Callable | None = None,
                        provenance: EvidenceProvenance | None = None,
                        gate: AdmissionAndAssemblyGate | None = None) -> dict:
    """Run ready tasks up to the adapter limit, validating every reused output."""
    valid, message = graph.validate_acyclic_and_integrity()
    if not valid:
        raise ValueError(f"Invalid execution graph: {message}")
    if any(node.status not in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.COMPLETED)
           for node in graph.nodes.values()):
        raise ValueError("Graph execution requires pending/ready tasks or validated completed results.")
    for node in graph.nodes.values():
        if node.input_artifacts.get("result_repair") and (type(node.retry_count) is not int or not 0 <= node.retry_count <= 2):
            raise ValueError("Result repair retry count must remain within the two-retry limit")
    if blackboard is not None:
        blackboard.task_dag = graph.nodes
    prov = provenance or EvidenceProvenance(
        workspace=getattr(backend, "workspace", Path.cwd()),
        allowed_domains=getattr(backend, "capture_allowed_domains", ()),
    )
    results = _restore(graph, backend, blackboard, retained_results or {}, provenance=prov)
    running: dict[asyncio.Task, Any] = {}
    limit = getattr(backend, "max_concurrency", 4)
    if type(limit) is not int or limit < 1:
        raise ValueError("Scheduler concurrency must be a positive integer.")
    owns_gate = gate is None
    active_gate = gate or AdmissionAndAssemblyGate(backend, provenance=prov, batch_size=min(limit, 4))

    async def run(node: Any, retry_prompt: str | None = None) -> None:
        if prov.bind_upstream_evidence(node, results) and on_result_attempt:
            on_result_attempt(node)
        from prompt_governance_gate import PromptGovernanceGate

        prompt = PromptGovernanceGate.default().assemble_task_prompt(
            node,
            dependency_results=results,
            blackboard_context=blackboard.get_dependency_context(node.id) if blackboard is not None else None,
            retry_prompt=retry_prompt,
            graph_nodes=graph.nodes,
        )
        fingerprint = input_fingerprint(node, results, backend, goal=graph.goal)
        dep_data = {dep: results[dep]["result"] for dep in sorted(node.dependencies)}
        if hasattr(backend, "dispatch_task"):
            response = await backend.dispatch_task(
                node, prompt=prompt, dependency_data=dep_data, research_dispatch=research_dispatch
            )
        else:
            try:
                if research_dispatch is not None:
                    response = await research_dispatch(node, prompt)
                else:
                    contract = node.input_artifacts.get("task_contract", {})
                    op = contract.get("operation")
                    deterministic_response = None
                    if op == "calculate":
                        from formula_engine import can_evaluate_deterministically, execute_deterministic_calculation
                        if can_evaluate_deterministically(node, dep_data):
                            deterministic_response = execute_deterministic_calculation(node, dep_data)

                    if deterministic_response is not None:
                        response = deterministic_response
                    else:
                        needs_tools = getattr(node, "needs_tools", None)
                        if node.input_artifacts.get("worker_wrapper") == "atomic_v1":
                            from atomic_worker import TEXT_ONLY
                            needs_tools = (op not in TEXT_ONLY) if op else False
                        elif node.id == "critique" or "critic" in node.role.lower():
                            needs_tools = False
                        elif needs_tools is None:
                            needs_tools = True

                        if not needs_tools:
                            native = getattr(backend, "native", backend)
                            if callable(getattr(backend, "spawn_restricted", None)):
                                dispatch = backend.spawn_restricted
                            elif callable(getattr(native, "spawn_restricted", None)):
                                dispatch = native.spawn_restricted
                            else:
                                dispatch = backend.spawn
                        else:
                            dispatch = backend.spawn

                        response = await dispatch(
                            prompt=prompt,
                            role=node.role,
                            model=getattr(node, "model", None) or getattr(backend, "default_model", None),
                            effort=getattr(node, "effort", None),
                            json_schema=getattr(node, "json_schema", None),
                            input_data=None,
                        )
            except ConfigurationRequired:
                raise
            except Exception as exc:
                response = SwarmResult(
                    node.role,
                    "ERROR",
                    None,
                    worker_diagnostic(backend.__class__.__name__, str(exc), error=exc),
                )
        contract = None
        review = None
        if response.rejected_output:
            node.rejected_output = deepcopy(response.rejected_output)
        if response.status == "SUCCESS":
            try:
                ws = Path(getattr(backend, "workspace", prov.workspace)).resolve()
                allowed = getattr(backend, "capture_allowed_domains", prov.allowed_domains)
                active_prov = (
                    prov
                    if prov.workspace == ws and tuple(prov.allowed_domains) == tuple(allowed)
                    else EvidenceProvenance(
                        prov.to_list(),
                        workspace=ws,
                        allowed_domains=allowed,
                        source_statuses=prov.source_statuses,
                        https_fetcher=prov.https_fetcher,
                    )
                )
                response.data, did_capture = await active_prov.capture_worker_evidence(node, response.data, results)
                if did_capture:
                    fingerprint = input_fingerprint(node, results, backend, goal=graph.goal)
                    if on_result_attempt:
                        on_result_attempt(node)
            except Exception as exc:
                node.rejected_output = {"result": deepcopy(response.data), "raw_response": response.raw_response,
                    "tokens_used": response.tokens_used, "reason": "Engine source capture failed", "capture_error": str(exc)}
                response.status = "ERROR"
                response.raw_response = "Engine source capture failed: " + str(exc)
        if response.status == "SUCCESS" and node.max_answer_words is not None:
            import jsonschema
            violation = None
            try:
                jsonschema.validate(response.data, node.json_schema)
            except jsonschema.ValidationError:
                violation = "Worker result exceeds the compact schema or has invalid evidence records"
            if not violation and len(response.data["answer"].split()) > node.max_answer_words:
                violation = f"Worker answer exceeds the {node.max_answer_words}-word limit"
            if violation:
                node.rejected_output = {"result": deepcopy(response.data), "raw_response": response.raw_response,
                                        "tokens_used": response.tokens_used, "reason": violation}
                response.status = "ERROR"
                response.raw_response = violation + "; original output retained in checkpoint, not admitted to dependencies"
        if response.status == "SUCCESS" and has_worker_result(response.data) and node.input_artifacts.get("result_gate"):
            review, next_prompt = await active_gate.admit_or_repair_task(
                node,
                response,
                results,
                fingerprint=fingerprint,
                prompt=prompt,
                goal=graph.goal,
                on_result_attempt=on_result_attempt,
            )
            if next_prompt is not None:
                return await run(node, next_prompt)
        if response.status == "SUCCESS" and has_worker_result(response.data):
            raw = response.raw_response if isinstance(response.raw_response, str) else json.dumps(response.data, ensure_ascii=False)
            envelope = {"role": node.role, "title": node.title, "result": response.data,
                        "raw_response": raw, "evidence_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                        "result_hash": _identity(response.data), "input_fingerprint": fingerprint,
                        "duration": response.duration_seconds, "tokens_used": response.tokens_used}
            if response.trace_path:
                envelope["research_trace"] = response.trace_path
            prov.attach_envelope_lineage(node, envelope, results)
            if review:
                envelope["result_check"] = review
                envelope["result_check_hash"] = _identity(review)
                envelope["result_attempts"] = deepcopy(node.result_attempts)
            try:
                contract = _register(node, envelope, backend, blackboard)
            except ValueError:
                response = SwarmResult(node.role, "ERROR", None, "Blackboard rejected worker output provenance")
            else:
                node.status = TaskStatus.COMPLETED
                node.output_data = response.data
                node.rejected_output = None
                node.duration_seconds = response.duration_seconds
                results[node.id] = envelope
                if on_result_commit:
                    on_result_commit(node, deepcopy(envelope))
        elif response.status == "SUCCESS":
            response = SwarmResult(node.role, "ERROR", None, "Worker returned no usable result")
        if response.status != "SUCCESS":
            node.status = TaskStatus.FAILED
            node.output_data = None
            node.error_trace = response.raw_response
            graph.cascade_failure(node.id)
        if on_task_finish:
            on_task_finish(node, response, contract)

    try:
        while True:
            for node in graph.nodes.values():
                if node.status not in (TaskStatus.PENDING, TaskStatus.READY):
                    continue
                if any(graph.nodes[dep].status in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED) for dep in node.dependencies):
                    node.status = TaskStatus.CANCELLED
                    continue
                if not all(graph.nodes[dep].status == TaskStatus.COMPLETED for dep in node.dependencies):
                    continue
                contract = node.input_artifacts.get("task_contract") or {}
                blocked_by = contract.get("blocked_by", [])
                if blocked_by:
                    node.status = TaskStatus.BLOCKED
                    node.error_trace = "Task blocked by unresolved required inputs: " + ", ".join(blocked_by)
                    graph.cascade_failure(node.id)
                    continue
                if jev_gate and node.jev_score < 0.25:
                    node.status = TaskStatus.CANCELLED
                    continue
                if len(running) >= limit:
                    break
                node.status = TaskStatus.RUNNING
                if on_task_start:
                    on_task_start(node)
                worker = asyncio.create_task(run(node))
                running[worker] = node
            if not running:
                break
            done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for worker in done:
                running.pop(worker)
                worker.result()
        return results
    except BaseException:
        for worker in running:
            if worker.cancelling() == 0:
                worker.cancel()
        joined = asyncio.gather(*running, return_exceptions=True)
        while not joined.done():
            try:
                await asyncio.shield(joined)
            except asyncio.CancelledError:
                continue
        joined.result()
        for node in running.values():
            if node.status == TaskStatus.RUNNING:
                node.status = TaskStatus.CANCELLED
        raise
    finally:
        if owns_gate:
            await active_gate.close()
