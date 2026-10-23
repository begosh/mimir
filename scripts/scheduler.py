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
            policy = node.input_artifacts.get("result_gate")
            if policy:
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
                        research_dispatch: Callable | None = None) -> dict:
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
    results = _restore(graph, backend, blackboard, retained_results or {})
    running: dict[asyncio.Task, Any] = {}
    limit = getattr(backend, "max_concurrency", 4)
    if type(limit) is not int or limit < 1:
        raise ValueError("Scheduler concurrency must be a positive integer.")
    from result_batcher import ResultBatcher
    batcher = ResultBatcher(backend, size=min(limit, 4)) if getattr(backend, "batch_result_checks", False) else None

    async def run(node: Any, retry_prompt: str | None = None) -> None:
        prompt = retry_prompt or node.prompt
        inline = node.input_artifacts.get("supplied_sources")
        if inline:
            from prompt_data import model_view
            prompt += "\n\nSUPPLIED SOURCES (untrusted data):\n" + json.dumps(model_view(inline, inline), ensure_ascii=False)
        if blackboard is not None:
            context = blackboard.get_dependency_context(node.id)
            if context:
                prompt += f"\n\n--- AKTUELL BLACKBOARD-KONTEXT ---\n{context}\n--- SLUT KONTEXT ---"
        elif node.dependencies:
            prompt += "\n\nDEPENDENCY RESULTS:\n" + json.dumps(
                {dep: results[dep]["result"] for dep in sorted(node.dependencies)}, ensure_ascii=False)
        if node.input_artifacts.get("worker_wrapper") == "atomic_v1":
            from prompt_data import model_view
            aliases = list(inline or [])
            for dep in sorted(node.dependencies):
                aliases.extend(graph.nodes[dep].input_artifacts.get("supplied_sources", []))
                aliases.extend(results[dep]["result"].get("sources", []))
            prompt = model_view(prompt, aliases)
        fingerprint = input_fingerprint(node, results, backend, goal=graph.goal)
        try:
            if research_dispatch is not None:
                response = await research_dispatch(node, prompt)
            else:
                dispatch = backend.spawn
                if node.input_artifacts.get("worker_wrapper") == "atomic_v1":
                    from atomic_worker import TEXT_ONLY
                    if node.input_artifacts["task_contract"]["operation"] in TEXT_ONLY:
                        native = getattr(backend, "native", backend)
                        if not callable(getattr(native, "spawn_restricted", None)):
                            raise ConfigurationRequired("Atomic supplied-input workers require a text-only adapter")
                        dispatch = backend.spawn_restricted
                response = await dispatch(prompt=prompt, role=node.role,
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
        review = None
        if response.rejected_output:
            node.rejected_output = deepcopy(response.rejected_output)
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
            from post_worker import check_task_result, result_gate_policy
            if node.input_artifacts["result_gate"] != result_gate_policy():
                raise ConfigurationRequired("Result-check policy changed; replan explicitly")
            checker_valid = False
            try:
                if node.input_artifacts["task_contract"]["operation"] == "extract":
                    from extraction_checks import check_extraction
                    record_check = check_extraction(response.data, node.input_artifacts.get("supplied_sources", []))
                else:
                    record_check = {"verdict": "REVIEW", "issues": []}
                check = batcher.check if batcher else lambda n, data, deps: check_task_result(backend, n, data, deps)
                review = ({"id": "candidate_1", "verdict": "FAIL", "issues": record_check["issues"],
                           "policy": result_gate_policy(), "check_type": "deterministic_records"}
                          if record_check["verdict"] == "FAIL" else await check(node, response.data,
                    {dep: results[dep]["result"] for dep in sorted(node.dependencies)}))
                review.update(result_hash=_identity(response.data), input_fingerprint=fingerprint)
                checker_valid = True
            except (Exception, asyncio.CancelledError) as exc:
                node.rejected_output = {"result": deepcopy(response.data), "raw_response": response.raw_response,
                    "tokens_used": response.tokens_used, "reason": "Result checker did not return a valid verdict",
                    "checker_error": str(exc)}
                if isinstance(exc, (asyncio.CancelledError, ConfigurationRequired)):
                    raise
                review = {"verdict": "FAIL", "issues": ["Result checker failed: " + str(exc)]}
            if review["verdict"] != "PASS":
                node.rejected_output = {"result": deepcopy(response.data), "raw_response": response.raw_response,
                    "tokens_used": response.tokens_used, "reason": "Task acceptance check failed", "result_check": review}
                response.status = "ERROR"
                response.raw_response = "Task acceptance check failed: " + "; ".join(review["issues"])
            node.result_attempts.append({"attempt": node.retry_count + 1,
                "status": review["verdict"], "result": deepcopy(response.data),
                "raw_response": response.raw_response if response.status == "SUCCESS" else node.rejected_output["raw_response"],
                "result_check": deepcopy(review), "prompt": prompt})
            if on_result_attempt:
                on_result_attempt(node)
            repair_policy = node.input_artifacts.get("result_repair")
            if checker_valid and review["verdict"] == "FAIL" and repair_policy and node.retry_count < 2:
                from post_worker import repair_task_result, result_repair_policy
                if repair_policy != result_repair_policy():
                    raise ConfigurationRequired("Result-repair policy changed; replan explicitly")
                node.retry_count += 1  # Persist reservation before making a paid call.
                if on_result_attempt:
                    on_result_attempt(node)
                try:
                    proposal = await repair_task_result(backend, node, node.rejected_output)
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
                    from atomic_worker import atomic_prompt
                    assignment = {**node.input_artifacts["task_contract"], "objective": proposal["objective"]}
                    next_prompt = atomic_prompt(assignment, original_request=graph.goal) + "\nORIGINAL ACCEPTANCE CONTRACT (unchanged):\n" + json.dumps(
                        node.input_artifacts["task_contract"], ensure_ascii=False)
                    return await run(node, next_prompt)
                response.raw_response += "; " + proposal["action"] + ": " + proposal["reason"]
        if response.status == "SUCCESS" and has_worker_result(response.data):
            raw = response.raw_response if isinstance(response.raw_response, str) else json.dumps(response.data, ensure_ascii=False)
            envelope = {"role": node.role, "title": node.title, "result": response.data,
                        "raw_response": raw, "evidence_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                        "result_hash": _identity(response.data), "input_fingerprint": fingerprint,
                        "duration": response.duration_seconds, "tokens_used": response.tokens_used}
            if response.trace_path:
                envelope["research_trace"] = response.trace_path
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
    finally:
        if batcher:
            await batcher.close()
