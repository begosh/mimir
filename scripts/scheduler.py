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

from backend import SwarmResult, has_worker_result, worker_diagnostic
from task_graph import EvidenceContract, TaskStatus
from mimir_config import ConfigurationRequired


def _identity(value: Any) -> str:
    content = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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


def _restore(graph: Any, backend: Any, blackboard: Any, retained: dict) -> dict:
    completed = {nid for nid, node in graph.nodes.items() if node.status == TaskStatus.COMPLETED}
    if completed != set(retained):
        raise ValueError("Retained results must match completed tasks; partial execution resume requires complete provenance.")
    results = {}
    for tier in graph.get_execution_tiers():
        for node in tier:
            if node.id not in completed:
                continue
            envelope = retained[node.id]
            if not node.dependencies.issubset(results):
                raise ValueError("Retained task has an incomplete dependency.")
            if (not isinstance(envelope, dict) or not has_worker_result(envelope.get("result"))
                    or not isinstance(envelope.get("raw_response"), str)
                    or hashlib.sha256(envelope["raw_response"].encode("utf-8")).hexdigest() != envelope.get("evidence_hash")
                    or _identity(envelope["result"]) != envelope.get("result_hash")
                    or _identity(node.output_data) != envelope.get("result_hash")
                    or input_fingerprint(node, results, backend, goal=graph.goal) != envelope.get("input_fingerprint")):
                raise ValueError(f"Retained task '{node.id}' has changed inputs or invalid output identity; replan explicitly.")
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
                        research_dispatch: Callable | None = None) -> dict:
    """Run ready tasks up to the adapter limit, validating every reused output."""
    valid, message = graph.validate_acyclic_and_integrity()
    if not valid:
        raise ValueError(f"Invalid execution graph: {message}")
    if any(node.status not in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.COMPLETED)
           for node in graph.nodes.values()):
        raise ValueError("Graph execution requires pending/ready tasks or validated completed results.")
    if blackboard is not None:
        blackboard.task_dag = graph.nodes
    results = _restore(graph, backend, blackboard, retained_results or {})
    running: dict[asyncio.Task, Any] = {}
    limit = getattr(backend, "max_concurrency", 4)
    if type(limit) is not int or limit < 1:
        raise ValueError("Scheduler concurrency must be a positive integer.")

    async def run(node: Any) -> None:
        prompt = node.prompt
        if blackboard is not None:
            context = blackboard.get_dependency_context(node.id)
            if context:
                prompt += f"\n\n--- AKTUELL BLACKBOARD-KONTEXT ---\n{context}\n--- SLUT KONTEXT ---"
        elif node.dependencies:
            prompt += "\n\nDEPENDENCY RESULTS:\n" + json.dumps(
                {dep: results[dep]["result"] for dep in sorted(node.dependencies)}, ensure_ascii=False)
        fingerprint = input_fingerprint(node, results, backend, goal=graph.goal)
        try:
            if research_dispatch is not None:
                response = await research_dispatch(node, prompt)
            else:
                response = await backend.spawn(prompt=prompt, role=node.role,
                                           model=getattr(node, "model", None) or backend.default_model,
                                           effort=getattr(node, "effort", None),
                                           json_schema=getattr(node, "json_schema", None),
                                           input_data=None)
        except ConfigurationRequired:
            # Admission/configuration failures apply to the run, rather than
            # being a recoverable finding from one worker. Join peers then let
            # the engine expose the explicit configuration requirement.
            raise
        except Exception as exc:
            response = SwarmResult(node.role, "ERROR", None,
                                   worker_diagnostic(backend.__class__.__name__, str(exc), error=exc))
        contract = None
        if response.status == "SUCCESS" and has_worker_result(response.data):
            raw = response.raw_response if isinstance(response.raw_response, str) else json.dumps(response.data, ensure_ascii=False)
            envelope = {"role": node.role, "title": node.title, "result": response.data,
                        "raw_response": raw, "evidence_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                        "result_hash": _identity(response.data), "input_fingerprint": fingerprint,
                        "duration": response.duration_seconds, "tokens_used": response.tokens_used}
            if response.trace_path:
                envelope["research_trace"] = response.trace_path
            try:
                contract = _register(node, envelope, backend, blackboard)
            except ValueError:
                response = SwarmResult(node.role, "ERROR", None, "Blackboard rejected worker output provenance")
            else:
                node.status = TaskStatus.COMPLETED
                node.output_data = response.data
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
                if any(graph.nodes[dep].status in (TaskStatus.FAILED, TaskStatus.CANCELLED) for dep in node.dependencies):
                    node.status = TaskStatus.CANCELLED
                    continue
                if not all(graph.nodes[dep].status == TaskStatus.COMPLETED for dep in node.dependencies):
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
