"""Result checking and answer assembly; distinct from reflective optimization."""
import json
from pathlib import Path

from backend import WorkerFailure

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
SOURCE_STATUSES = {"synthetic_fixture", "retrieved", "user_supplied", "unverified"}


def material_finding_contract(prompt):
    """Keep the original assignment as the admission and repair contract."""
    return {"objective": prompt, "operation": "research", "inputs": ["assigned evidence and direct dependency results"],
            "expected_output": "Assigned answer with source-linked material claims, qualifications, conflicts and gaps",
            "acceptance_check": "Address the original assignment; no unsupported factual additions or omitted material requirements. "
                                "Preserve source qualifications, conflicts and gaps; model agreement is not independent verification."}


def check_material_records(result):
    """Validate the shared record structure and links, never source entailment."""
    from jsonschema import validate, ValidationError
    from research_contract import worker_result_schema
    try:
        validate(result, worker_result_schema())
    except ValidationError:
        return {"verdict": "FAIL", "issues": ["Malformed material-finding records"], "check_type": "structural_provenance"}
    issues = []
    ids = [s["id"] for s in result["sources"]]
    if any(not sid.strip() for sid in ids) or len(ids) != len(set(ids)):
        issues.append("Source identities must be nonempty and unique")
    for claim in result["claims"]:
        if not claim["text"].strip() or not claim["rationale"].strip():
            issues.append("Material claims require text and a support rationale")
        if any(sid not in ids for sid in claim["source_ids"]):
            issues.append("Material claim references an unknown source")
        if claim["support_status"] != "unsupported" and not claim["source_ids"]:
            issues.append("Reported source support requires source links")
    return {"verdict": "FAIL" if issues else "REVIEW", "issues": issues, "check_type": "structural_provenance"}


def result_gate_policy():
    import hashlib
    return {"version": "bound_material_findings_v3", "prompt_hash": hashlib.sha256(
        (PROMPTS / "RESULT_CHECKER.txt").read_bytes()).hexdigest()}


def result_repair_policy():
    import hashlib
    return {"version": "rephrase_only_v1", "max_retries": 2, "prompt_hash": hashlib.sha256(
        (PROMPTS / "RESULT_REPAIR.txt").read_bytes()).hexdigest()}


async def repair_task_result(backend, node, rejection):
    from prompt_data import model_view
    context = {"contract": node.input_artifacts["task_contract"],
               "failed_result": rejection["result"], "feedback": rejection["result_check"]["issues"],
               "retry": node.retry_count, "max_retries": 2}
    prompt = (PROMPTS / "RESULT_REPAIR.txt").read_text(encoding="utf-8").replace(
        "{{context}}", json.dumps(model_view(context, node.input_artifacts.get("supplied_sources", [])), ensure_ascii=False))
    schema = {"type": "object", "additionalProperties": False,
              "required": ["action", "objective", "reason"], "properties": {
                  "action": {"type": "string", "enum": ["REPHRASE", "BLOCKED", "STOP"]},
                  "objective": {"type": "string", "maxLength": 500},
                  "reason": {"type": "string", "minLength": 1, "maxLength": 500}}}
    response = await backend.spawn_restricted(prompt=prompt, role="Mimir-Result-Repairer",
        model=backend.default_model, effort=backend.default_effort, json_schema=schema)
    if response.status != "SUCCESS":
        raise WorkerFailure("Result repair", response.raw_response)
    from jsonschema import validate
    validate(response.data, schema)
    proposal = response.data
    if (proposal["action"] == "REPHRASE") != bool(proposal["objective"].strip()):
        raise ValueError("Repair objective contradicts action")
    return proposal


async def check_task_result(backend, node, result, dependency_results):
    from atomic_worker import worker_contract
    context = {"supplied_sources": node.input_artifacts.get("supplied_sources", []),
               "dependency_results": dependency_results,
               "candidates": [{"id": "candidate_1", "contract": worker_contract(
                   node.input_artifacts["task_contract"]), "result": result}]}
    checked = await check_results(backend, context)
    return {**checked["checks"][0], "policy": result_gate_policy()}


def checker_schema():
    fields = {"id": {"type": "string"}, "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
              "issues": {"type": "array", "items": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["checks"],
            "properties": {"checks": {"type": "array", "items": {"type": "object",
                "additionalProperties": False, "required": list(fields), "properties": fields}}}}


async def check_results(backend, context):
    from prompt_data import compact_checker_context
    context = compact_checker_context(context)
    prompt = (PROMPTS / "RESULT_CHECKER.txt").read_text(encoding="utf-8").replace(
        "{{context}}", json.dumps(context, ensure_ascii=False))
    response = await backend.spawn_restricted(prompt=prompt, role="Mimir-Result-Checker",
        model=backend.default_model, effort=backend.default_effort, json_schema=checker_schema())
    if response.status != "SUCCESS":
        raise WorkerFailure("Result checking", response.raw_response)
    data = response.data
    from jsonschema import validate
    validate(data, checker_schema())
    ids = [item["id"] for item in data["checks"]]
    expected = [item["id"] for item in context["candidates"]]
    if len(ids) != len(set(ids)) or set(ids) != set(expected) or len(expected) != len(set(expected)):
        raise ValueError("Checker omitted, duplicated or invented candidates")
    if any((item["verdict"] == "PASS" and item["issues"]) or
           (item["verdict"] == "FAIL" and not item["issues"]) for item in data["checks"]):
        raise ValueError("Checker returned contradictory verdict and issues")
    return data


def synthesis_context(state):
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
        coverage.setdefault(node_id, check.get("verdict", "RETURNED") if isinstance(check, dict) else
                            "RETURNED" if node_id in completed else "NOT RUN")
    registry = {}
    supplied = list(state.get("source_registry", []))
    config = state.get("research_config") or {}
    supplied += [{**s, "status": config.get("source_statuses", {}).get(s["id"],
                 "user_supplied" if s.get("retrieval_type") == "local_file" else "retrieved")}
                 for s in config.get("sources", [])]
    for node in nodes.values():
        supplied += node.get("input_artifacts", {}).get("supplied_sources", [])
    for envelope in completed.values():
        packet = envelope.get("captured_evidence")
        if packet:
            from retrieved_evidence import inline_spans
            supplied += inline_spans(packet, "frozen_publication_span")
    statuses = {}
    for source in supplied:
        status = source.get("status", "user_supplied")
        if status not in SOURCE_STATUSES:
            status = "unverified"
        key = source.get("id")
        if key in statuses and statuses[key] != status:
            status = "unverified"
        statuses[key] = status

    def merge(source):
        key = source.get("id")
        if not key:
            return
        status = statuses.get(key, "retrieved" if source.get("retrieved_at") and
                              source.get("retrieval_type") in {"web_page", "primary_document", "search_snippet", "abstract"}
                              else "unverified")
        entry = registry.setdefault(key, {"id": key, "locators": [], "status": status,
                                          "support_excerpts": [], "retrieval_records": []})
        provenance = {k: source[k] for k in ("retrieval_type", "retrieved_at", "sha256") if k in source}
        if provenance and provenance not in entry["retrieval_records"]:
            entry["retrieval_records"].append(provenance)
        for field, value in (("locators", source.get("locator")),
                             ("support_excerpts", source.get("support_excerpt") or
                              (source.get("text") if source.get("delivery", "").startswith("frozen_") else None))):
            if value and value not in entry[field]:
                entry[field].append(value)
        if entry["status"] != status:
            entry["status"] = "unverified"

    for source in supplied:
        merge(source)
    findings, critiques = {}, {}
    if (state.get("intel_brief") or {}).get("items") or (state.get("intel_brief") or {}).get("retrieval_gaps"):
        findings["retrieval_records"] = state["intel_brief"]
    if state.get("intel_context"):
        findings["scout_context"] = state["intel_context"]
    for node_id, envelope in completed.items():
        result = envelope.get("result")
        target = critiques if any(word in envelope.get("role", "").lower() for word in ("red-team", "critic")) else findings
        target[node_id] = result
        if isinstance(result, dict):
            for source in result.get("sources", []):
                merge(source)
    from task_graph import separate_review_assignments
    request, assignments = separate_review_assignments(state.get("goal", "")) if state.get("mode") == "review" else (state.get("goal", ""), {})
    if assignments.get("synthesis"):
        scope.append("Assigned synthesis deliverable: " + assignments["synthesis"])
    context = {"request": request, "scope": scope,
            "coverage": {"components": coverage, "intended_components": (state.get("task_brief") or {}).get("components", [])},
            "sources": list(registry.values()), "findings": findings,
            "checks": {"result_checks": {**state.get("result_checks", {}), **{
                node_id: envelope["result_check"] for node_id, envelope in completed.items()
                if envelope.get("result_check")}}, "critic_findings": critiques}}
    from prompt_data import model_view
    context = model_view(context, supplied)
    for result in [*context["findings"].values(), *context["checks"]["critic_findings"].values()]:
        if isinstance(result, dict):
            for source in result.get("sources", []):
                source.pop("support_excerpt", None)  # already merged in the source registry
    return context


async def synthesize(backend, context, *, model=None, max_answer_words=None):
    prompt = (PROMPTS / "SYNTHESIZER.txt").read_text(encoding="utf-8")
    # Replace placeholders once; untrusted values cannot insert new placeholders.
    import re
    values = {k: json.dumps(v, ensure_ascii=False) for k, v in context.items()}
    values["word_limit"] = f"Answer at most {max_answer_words} whitespace-separated words." if max_answer_words else ""
    prompt = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m[1]], prompt)
    schema = {"type": "object", "additionalProperties": False, "required": ["answer", "limitations"],
              "properties": {"answer": {"type": "string"},
                             "limitations": {"type": "array", "maxItems": 8,
                                             "items": {"type": "string", "maxLength": 600}}}}
    native = getattr(backend, "native", backend)
    dispatch = backend.spawn_restricted if hasattr(native, "spawn_restricted") else backend.spawn
    response = await dispatch(prompt=prompt, role="Mimir-Synthesizer", model=model or backend.default_model,
                              effort=backend.default_effort, json_schema=schema)
    if response.status != "SUCCESS":
        raise WorkerFailure("Answer synthesis", response.raw_response)
    from jsonschema import validate
    validate(response.data, schema)
    answer = response.data["answer"]
    if not answer.strip():
        raise ValueError("Synthesis returned an empty answer")
    if max_answer_words and len(answer.split()) > max_answer_words:
        rejected = {"result": response.data, "raw_response": response.raw_response,
                    "tokens_used": response.tokens_used, "reason": "Synthesis exceeds compact word limits"}
        for call in getattr(backend, "usage_calls", []):
            if call.get("operation_id") == response.operation_id:
                call.update(status="ERROR", rejected_output=rejected)
                backend.event(dict(call))
        raise ValueError("Synthesis exceeds compact word limits; original output retained without publication")
    return response.data, context


async def check_final_answer(backend, context, assembled, *, model=None, publication_view=None):
    payload = {"task_context": context, "assembled": assembled}
    if publication_view is not None:
        payload["publication_view"] = publication_view
    conflicts = list(context.get("conflicting_evidence") or [])
    if not conflicts and "findings" in context:
        from source_support import detect_conflicts
        conflicts = detect_conflicts(context["findings"])
    if conflicts:
        from source_support import check_conflict_preservation
        conflict_res = check_conflict_preservation(assembled, conflicts)
        if conflict_res["verdict"] == "FAIL":
            import hashlib
            return {
                "verdict": "FAIL",
                "issues": conflict_res["issues"],
                "policy": {"version": "final_answer_v1", "prompt_hash": hashlib.sha256(
                    (PROMPTS / "FINAL_ANSWER_CHECK.txt").read_bytes()).hexdigest()},
                "input_hash": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                "check_type": "conflict_integrity"
            }
    prompt = (PROMPTS / "FINAL_ANSWER_CHECK.txt").read_text(encoding="utf-8").replace(
        "{{context}}", json.dumps(payload, ensure_ascii=False))
    schema = {"type": "object", "additionalProperties": False, "required": ["verdict", "issues"],
              "properties": {"verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
                             "issues": {"type": "array", "maxItems": 8,
                                        "items": {"type": "string", "minLength": 1, "maxLength": 600}}}}
    native = getattr(backend, "native", backend)
    dispatch = backend.spawn_restricted if hasattr(native, "spawn_restricted") else backend.spawn
    response = await dispatch(prompt=prompt, role="Mimir-Final-Checker", model=model or backend.default_model,
                              effort=backend.default_effort, json_schema=schema)
    if response.status != "SUCCESS":
        raise WorkerFailure("Final answer checking", response.raw_response)
    from jsonschema import validate
    validate(response.data, schema)
    verdict = response.data
    if (verdict["verdict"] == "PASS") != (verdict["issues"] == []):
        raise ValueError("Final checker returned contradictory verdict and issues")
    import hashlib
    return {**verdict, "policy": {"version": "final_answer_v1", "prompt_hash": hashlib.sha256(
        (PROMPTS / "FINAL_ANSWER_CHECK.txt").read_bytes()).hexdigest()},
        "input_hash": hashlib.sha256(json.dumps(payload,
                ensure_ascii=False, sort_keys=True).encode()).hexdigest()}


def assembly_repair_policy():
    import hashlib
    return {"version": "publication_assembly_v2", "max_corrections": 1,
            "repair_prompt_hash": hashlib.sha256((PROMPTS / "ASSEMBLY_REPAIR.txt").read_bytes()).hexdigest(),
            "checker_prompt_hash": hashlib.sha256((PROMPTS / "FINAL_ANSWER_CHECK.txt").read_bytes()).hexdigest()}


async def repair_assembled_answer(backend, context, assembled, feedback, *, model=None, max_answer_words=None, publication=False):
    payload = {"task_context": context, "rejected_answer": assembled, "feedback": feedback,
               "max_answer_words": max_answer_words}
    prompt = (PROMPTS / "ASSEMBLY_REPAIR.txt").read_text(encoding="utf-8").replace(
        "{{context}}", json.dumps(payload, ensure_ascii=False))
    schema = {"type": "object", "additionalProperties": False, "required": ["answer", "limitations"],
              "properties": {"answer": {"type": "string", "minLength": 1},
                             "limitations": {"type": "array", "maxItems": 8,
                                             "items": {"type": "string", "maxLength": 600}}}}
    if publication:
        schema["required"].append("quarantined_tasks")
        schema["properties"]["quarantined_tasks"] = {"type": "array", "maxItems": 16, "items": {
            "type": "object", "additionalProperties": False, "required": ["task_id", "reason"],
            "properties": {"task_id": {"type": "string"}, "reason": {"type": "string", "minLength": 1, "maxLength": 600}}}}
    response = await backend.spawn_restricted(prompt=prompt, role="Mimir-Assembly-Repairer",
        model=model or backend.default_model, effort=backend.default_effort, json_schema=schema)
    if response.status != "SUCCESS":
        raise WorkerFailure("Assembly correction", response.raw_response)
    from jsonschema import validate
    try:
        validate(response.data, schema)
        if publication:
            from publication_view import build_publication_view
            build_publication_view(context, response.data["quarantined_tasks"])
        if not response.data["answer"].strip() or (max_answer_words and len(response.data["answer"].split()) > max_answer_words):
            raise ValueError("Assembly correction exceeds answer limits or is empty")
    except Exception as exc:
        response.rejected_output = {"result": response.data, "raw_response": response.raw_response,
                                    "reason": "Invalid assembly correction"}
        for call in getattr(backend, "usage_calls", []):
            if call.get("operation_id") == response.operation_id:
                call.update(status="ERROR", rejected_output=response.rejected_output)
                backend.event(dict(call))
        exc.rejected_output = response.rejected_output
        raise
    return response.data
