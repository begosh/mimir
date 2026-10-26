"""Interpret first, then recursively split work into bounded leaf contracts."""
import asyncio
from copy import deepcopy
import json
import time
from pathlib import Path

from task_brief import TASK_BRIEF_SCHEMA, validate_task_brief
from mimir_config import ConfigurationRequired

from task_contracts import OPERATIONS, validate_tasks, validate_review, validate_repair


def validate_planning_budget(value=None):
    limits = {"max_calls": 8, "max_seconds": 120, "max_nodes": 32}
    if value is not None:
        if not isinstance(value, dict) or set(value) - set(limits):
            raise ValueError("Planning budget accepts max_calls, max_seconds and max_nodes")
        limits.update(value)
    for key, maximum in (("max_calls", 32), ("max_seconds", 600), ("max_nodes", 128)):
        if type(limits[key]) is not int or not 1 <= limits[key] <= maximum:
            raise ValueError(f"Invalid planning budget {key}")
    return limits


class RecursivePlanner:
    def __init__(self, backend, *, max_leaves=8, max_depth=3, budget=None, on_checkpoint=None,
                 domain_rules="", available_sources=()):
        if type(max_depth) is not int or not 1 <= max_depth <= 4:
            raise ValueError("Recursive planning depth must be within [1, 4]")
        if type(max_leaves) is not int or not 1 <= max_leaves <= 16:
            raise ValueError("Recursive leaf limit must be within [1, 16]")
        native = getattr(backend, "native", backend)
        if not callable(getattr(native, "spawn_restricted", None)):
            raise ConfigurationRequired("Recursive planning requires a text-only native adapter; no research-tool fallback")
        self.backend = backend
        self.max_leaves, self.max_depth = max_leaves, max_depth
        self.budget = validate_planning_budget(budget)
        self.on_checkpoint = on_checkpoint
        if not isinstance(domain_rules, str) or len(domain_rules) > 4000:
            raise ValueError("Domain rules must be a string of at most 4000 characters")
        self.domain_rules = domain_rules
        self.available_sources = list(available_sources)
        self.state = {"status": "interpreting", "interpretation": None, "tree": [],
                      "calls": [], "reviews": [], "repairs": [], "simplicity_policy": "review_and_repair_v1",
                      "domain_rules": domain_rules,
                      "limits": {**self.budget, "max_leaves": max_leaves, "max_depth": max_depth}}
        self.leaves = []
        self.nodes = 0

    def checkpoint(self):
        self.state["leaves"] = deepcopy(self.leaves)
        if self.on_checkpoint:
            self.on_checkpoint(deepcopy(self.state))

    async def ask(self, prompt, role, *, field, parent=None):
        if len(self.state["calls"]) >= self.budget["max_calls"]:
            raise ConfigurationRequired("Recursive planning call limit reached; unfinished branches retained")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ConfigurationRequired("Recursive planning deadline reached; unfinished branches retained")
        call = {"role": role, "parent": parent, "status": "inflight", "tokens_used": None}
        # Retain the application prompt for review and reproducible comparisons.
        call["prompt"] = prompt + "\nReturn the required JSON object directly, matching the supplied schema."
        self.state["calls"].append(call)
        self.checkpoint()
        started = time.monotonic()
        from planning_schemas import planning_schema
        schema = planning_schema(field)
        try:
            async with asyncio.timeout(remaining):
                response = await self.backend.spawn_restricted(
                    prompt=call["prompt"],
                    role=role, model=self.backend.default_model,
                    effort=self.backend.default_effort, json_schema=schema)
            call.update(status=response.status, tokens_used=response.tokens_used or None,
                        timing=response.timing, raw_response=response.raw_response)
            if response.status != "SUCCESS":
                raise ConfigurationRequired(f"{role} failed; inspect retained planning diagnostics")
            from jsonschema import validate, ValidationError
            try:
                validate(response.data, schema)
            except ValidationError:
                raise ValueError("Planner returned an invalid structured output") from None
            raw = json.dumps(response.data, ensure_ascii=False)
            if len(raw) > 16000:
                raise ValueError("Planning output exceeds 16000 characters; retained without truncation")
            return response.data
        except BaseException:
            call["status"] = "failed"
            raise
        finally:
            call["duration_seconds"] = round(time.monotonic() - started, 3)
            self.checkpoint()

    async def plan(self, goal, task_brief=None):
        self.deadline = time.monotonic() + self.budget["max_seconds"]
        self.state["original_goal"] = goal
        try:
            if task_brief is None:
                prompt = ("Interpret the user's request. Do not answer, research or decompose it yet. "
                          "Identify the intended deliverable, only explicit constraints, components, "
                          "evidence needs, material assumptions, and missing information that truly prevents execution.\n"
                          "CRITICAL DISTINCTION: Distinguish genuine required-input blockers from ambiguity "
                          "or unspecified recommendation preferences (such as 'best', 'optimal', or 'recommended'). "
                          "An unspecified preference permits evidence gathering and a qualified answer; do not treat "
                          "it as missing information that blocks retrieval or execution. "
                          "Label assumptions explicitly without inventing user constraints, equipment, quantities or sources. "
                          "Keep outcome under 60 words; each list at most five short items.\n"
                          "Required interpretation fields/schema: " + json.dumps(TASK_BRIEF_SCHEMA) +
                          "\nORIGINAL REQUEST:\n" + goal)
                prompt += "\nAVAILABLE CAPTURED SOURCES (frozen text available to workers; use exact IDs):\n" + json.dumps(self.available_sources)
                task_brief = validate_task_brief(await self.ask(prompt, "Mimir-Interpreter", field="brief_json"))
            else:
                task_brief = validate_task_brief(task_brief)
            self.state.update(interpretation=task_brief, status="decomposing")
            self.checkpoint()
            await self.split(goal, task_brief, parent="root", objective=task_brief["outcome"],
                             depth=1, inherited=[], branch=self.state["tree"])
            await self.harden(goal, task_brief)
            if time.monotonic() >= self.deadline:
                raise ConfigurationRequired("Recursive planning deadline reached before admission")
            self.state.update(status="planned", leaves=deepcopy(self.leaves))
            self.checkpoint()
            return task_brief, self.leaves, deepcopy(self.state)
        except BaseException:
            self.state["status"] = "incomplete"
            self.checkpoint()
            raise

    async def split(self, goal, brief, *, parent, objective, depth, inherited, branch,
                    inherited_blocked=(), supplied_inputs=(), reserved_leaves=0):
        leaf_slots = self.max_leaves - len(self.leaves) - reserved_leaves
        if leaf_slots < 1:
            raise ConfigurationRequired("Recursive leaf limit reached; unfinished branches retained")
        prompt = f"""ROLE
You are a task decomposer. Split ONE component into smaller child tasks.
Do not answer, search, calculate, or retrieve anything yourself.

HARD LIMITS (violating any of these = invalid output)
1. Return 1-4 children. Never more.
2. Depth {depth} of {self.max_depth}.
   At depth 1, create broad components where needed (atomic=false, operation="split").
   An already stupid-easy component may be atomic; do not add unnecessary levels.
   At maximum depth, admit only children that meet the leaf requirements.
   Never relabel a broad component atomic to fit a limit.
3. Leaf budget available to this branch: {leaf_slots}. Other pending branches have
   reserved slots. Your children may never imply more leaves than this budget.
4. Never mark a full investigation or synthesis as atomic.
5. Output raw JSON only. Include planning_error=null for successful splits.
   No prose, no markdown fences.
If this component cannot be split within the limits, return
{{"tasks":[],"planning_error":"one short reason"}} instead of inventing simple tasks.

LEAF OPERATIONS (atomic=true, exactly one per leaf)
- clarify: ask the user for ONE material missing choice. Input = original request.
- retrieve: one focused query, max 2 candidate hits, max 1 chosen page.
- extract: one named field group from one supplied page.
- calculate: one stated formula over supplied numbers.
- compare: one explicit comparison over supplied findings.
- check: one explicit predicate over supplied findings; return supported,
  contradicted, or insufficient evidence, with the supporting input reference.
Every leaf must be STUPID EASY for a low-effort worker: 1-2 named inputs,
one operation, and a tiny output (at most 150 words). No delegation.
Each retrieved page/input excerpt must be under 16000 characters.

PROPORTIONAL DECOMPOSITION: START WITH ONE BOUNDED LEAF
- If a component or request can be satisfied by a single bounded retrieval or extraction
  (1-2 inputs, <= 16000 characters input, <= 150 words output) or a short contiguous procedure,
  start with ONE atomic leaf. Do not proactively fracture or over-split it.
- Split a component into multiple children ONLY when:
  1. Input bounds are exceeded (> 16000 characters or multiple distinct sources requiring separate queries).
  2. Output bounds are exceeded (> 150 words expected output).
  3. Distinct operations or decisions are required (such as an extraction followed by a calculation formula,
     or an extraction followed by a multi-source comparison, or independent multi-stage processes).

CONTIGUOUS PROCEDURES & ADJACENT FIELDS
- A short contiguous procedure (such as mixing and kneading directly described together) or
  adjacent source fields requiring only faithful extraction can be one operation.
  Do not redundantly split simple contiguous procedures into separate leaves unless distinct
  decisions or limits require it.

CLARIFY VS. ASSUMPTION/QUALIFICATION VS. BLOCKED
- Distinguish genuine required-input blockers from ambiguity or unspecified recommendation preferences (e.g. 'best', 'optimal').
- Do NOT create a clarify task or block retrieval for unspecified recommendation preferences. Proceed with evidence gathering; label explicit assumptions in the task objective, and qualify the answer (e.g. noting 'best' is unestablished or stating criteria).
- Never invent user preferences, equipment, measurements or source claims as constraints.
- Use clarify/blocked_by ONLY when a decision or calculation genuinely requires a specific missing user input or missing target that neither the request, supplied parent inputs, nor retrieved evidence can provide.
- Genuine missing inputs block only their dependent decision. Never block upstream retrieval or independent parallel tasks on an unresolved dependent input.
- Otherwise a sensible default must be explicitly labelled as an assumption in the objective.
- Record an unresolved user choice in blocked_by only for tasks whose execution genuinely depends on it.

GENERAL RULES
- Factual values and source references must come from supplied inputs or retrieval.
  Calculated values must identify their formula and inputs.
- Stay within the scope of the request. Add nothing the user did not ask for.
- Retrieval is a tool choice justified by an evidence need, not a mandatory step.
- dependencies may reference sibling ids only. No cycles.
- Name all inputs a leaf needs, including any supplied by parent dependencies.

DOMAIN RULES (task-specific context, not evidence)
{self.domain_rules or 'None supplied.'}

INPUT
AVAILABLE CAPTURED SOURCES (already captured, bind by exact source ID): {json.dumps(self.available_sources)}
ORIGINAL REQUEST: {goal}
INTERPRETATION (context, not evidence): {json.dumps(brief, ensure_ascii=False)}
SUPPLIED PARENT INPUT CONTRACTS (future inputs, not retrieved evidence): {json.dumps(list(supplied_inputs), ensure_ascii=False)}
COMPONENT TO SPLIT: {objective}

OUTPUT SCHEMA (include every key in every child)
{{"tasks":[{{"id":"short_sibling_id","objective":"one short assignment",
"atomic":true,"operation":"extract","inputs":["named input"],
"expected_output":"small output","acceptance_check":"one concrete check",
"blocked_by":[],"dependencies":[],"max_input_items":1,"max_output_words":100}}]}}
atomic is a boolean; operation is one of split, {', '.join(OPERATIONS)}.
For operation="split": atomic=false, max_input_items=0; other fields may be empty
strings/arrays. Include useful parent input contracts when needed by recursive children.

BEFORE REPLYING, VERIFY
- Child count is 1-4, except the explicit planning_error response.
- The depth and leaf budget rules are respected.
- Every leaf has exactly one operation, 1-2 inputs, expected output and a concrete check.
- Every dependency id exists among the siblings and dependencies are acyclic.
- The JSON is valid.
"""
        data = await self.ask(prompt, "Mimir-Decomposer", field="tasks_json", parent=parent)
        if isinstance(data, dict) and data.get("planning_error") and data.get("tasks") == []:
            reason = data["planning_error"]
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 400:
                raise ValueError("Invalid recursive planning error")
            self.state["planning_error"] = {"parent": parent, "reason": reason}
            self.checkpoint()
            raise ConfigurationRequired("Recursive planner cannot fit component within limits; inspect retained planning_error")
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 4:
            raise ValueError("A recursive split must contain 1-4 children")
        if len(tasks) > leaf_slots:
            raise ConfigurationRequired("Recursive leaf limit reached; each child needs at least one leaf")
        await self.admit_tasks(tasks, goal, brief, parent=parent, depth=depth,
                               inherited=inherited, branch=branch, inherited_blocked=inherited_blocked,
                               supplied_inputs=supplied_inputs, reserved_leaves=reserved_leaves)

    async def admit_tasks(self, tasks, goal, brief, *, parent, depth, inherited, branch,
                          inherited_blocked=(), supplied_inputs=(), reserved_leaves=0):
        validate_tasks(tasks)
        if len(tasks) > self.max_leaves - len(self.leaves) - reserved_leaves:
            raise ConfigurationRequired("Recursive leaf limit reached; each child needs at least one leaf")
        # Contracts and sibling dependencies are validated before allocating leaves.
        pending = list(tasks)
        terminals = {}
        while pending:
            ready = [t for t in pending if set(t["dependencies"]).issubset(terminals)]
            if not ready:
                raise ValueError("Unknown or cyclic recursive sibling dependencies")
            for task in ready:
                self.nodes += 1
                if self.nodes > self.budget["max_nodes"]:
                    raise ConfigurationRequired("Recursive planning node limit reached")
                task_id = parent + "." + task["id"]
                dependencies = sorted(set(inherited + [leaf for dep in task["dependencies"] for leaf in terminals[dep]]))
                node = {**deepcopy(task), "id": task_id, "parent": parent, "depth": depth, "dependencies": dependencies,
                        "blocked_by": sorted(set([*inherited_blocked, *task["blocked_by"]])), "children": []}
                branch.append(node)
                self.checkpoint()
                before = len(self.leaves)
                if task["atomic"]:
                    if len(self.leaves) >= self.max_leaves:
                        raise ConfigurationRequired("Recursive leaf limit reached; broad tasks are not silently accepted")
                    self.leaves.append({k: v for k, v in node.items() if k != "children"})
                else:
                    if depth >= self.max_depth:
                        raise ConfigurationRequired("Recursive depth limit reached with a non-atomic component")
                    available_inputs = [*supplied_inputs, *task["inputs"],
                                        *[{"id": leaf["id"], "expected_output": leaf["expected_output"]}
                                          for leaf in self.leaves if leaf["id"] in dependencies]]
                    await self.split(goal, brief, parent=task_id, objective=task["objective"],
                                     depth=depth + 1, inherited=dependencies, branch=node["children"],
                                     inherited_blocked=node["blocked_by"], supplied_inputs=available_inputs,
                                     reserved_leaves=reserved_leaves + len(pending) - 1)
                terminals[task["id"]] = [leaf["id"] for leaf in self.leaves[before:]]
                pending.remove(task)
                self.checkpoint()

    def node(self, task_id):
        def walk(branch):
            for item in branch:
                if item["id"] == task_id:
                    return item
                found = walk(item["children"])
                if found:
                    return found
        found = walk(self.state["tree"])
        if found is None:
            raise ValueError("Repair target absent from planning tree")
        return found

    def input_contracts(self, dependencies):
        return [*self.available_sources, *[{"id": leaf["id"], "expected_output": leaf["expected_output"],
                 "status": "future_prerequisite_not_executed"}
                for leaf in self.leaves if leaf["id"] in dependencies]]

    async def review(self, goal, brief, tasks, original, inherited, *, parent, check_coverage=True):
        context = {"original_request": goal, "interpretation": brief,
                   "task_contract": original, "proposed_repair": {"tasks": tasks},
                   "inherited_prerequisites": inherited,
                   "available_inputs": self.input_contracts(inherited),
                   "domain_rules": self.domain_rules,
                   "check_coverage": check_coverage}
        from prompt_governance_gate import PromptGovernanceGate

        prompt = PromptGovernanceGate.default().render_template(
            "TASK_SIMPLICITY_REVIEW", review_context_json=context
        )
        review = await self.ask(
            prompt,
            "Mimir-Simplicity-Reviewer",
            field="review_json",
            parent=parent,
        )
        validate_review(review, [task["id"] for task in tasks])
        record = {"parent": parent, "task_ids": [t["id"] for t in tasks],
                  "review": deepcopy(review), "check_coverage": check_coverage}
        self.state["reviews"].append(record)
        self.checkpoint()
        return review

    async def harden(self, goal, brief):
        # Small batches avoid one runtime startup per leaf. Whole-plan coverage
        # is assessed once; replacements are checked against their original task.
        pending = list(self.leaves)
        rejected = []
        for start in range(0, len(pending), 4):
            batch = pending[start:start + 4]
            review = await self.review(goal, brief, batch, {"objective": brief["outcome"]},
                                       sorted({dep for task in batch for dep in task["dependencies"]}),
                                       parent="root", check_coverage=len(pending) <= 4)
            if not review["coverage_preserved"]:
                self.state["planning_error"] = {"parent": "root", "reason": "; ".join(review["coverage_gaps"])}
                raise ConfigurationRequired("Simplicity batch review reported a coverage problem; partial plan retained")
            for verdict in review["tasks"]:
                task = next(task for task in batch if task["id"] == verdict["id"])
                if verdict["decision"] == "ACCEPT":
                    task["simplicity_review"] = deepcopy(verdict)
                    self.node(task["id"])["simplicity_review"] = deepcopy(verdict)
                else:
                    rejected.append((task, verdict))
            self.checkpoint()
        for task, feedback in rejected:
            await self.repair_task(goal, brief, task, feedback)
        if any(t.get("simplicity_review", {}).get("decision") != "ACCEPT" for t in self.leaves):
            raise ConfigurationRequired("Unreviewed replacement task cannot enter the executable plan")
        # Batch reviews cannot detect a requirement omitted from every batch.
        if len(pending) > 4 or rejected:
            context = {"original_request": goal, "interpretation": brief,
                       "tasks": [{k: t[k] for k in ("id", "objective", "expected_output", "acceptance_check", "dependencies", "blocked_by")}
                                 for t in self.leaves], "domain_rules": self.domain_rules}
            prompt = PromptGovernanceGate.default().render_template(
                "TASK_PLAN_COVERAGE", coverage_context_json=context
            )
            review = await self.ask(
                prompt,
                "Mimir-Plan-Coverage-Reviewer",
                field="coverage_json",
                parent="root",
            )
            if not isinstance(review, dict) or set(review) != {"coverage_preserved", "coverage_gaps"}:
                raise ValueError("Invalid whole-plan coverage fields")
            validate_review({"tasks": [], **review}, [])
            self.state["reviews"].append({"parent": "root", "review": deepcopy(review), "type": "coverage"})
            if not review["coverage_preserved"]:
                self.state["planning_error"] = {"parent": "root", "reason": "Whole-plan review rejected coverage or task simplicity",
                                               "review": review}
                raise ConfigurationRequired("Whole-plan review rejected the final plan; unresolved work retained")
            self.checkpoint()

    async def repair_task(self, goal, brief, original, feedback):
        history = []
        node = self.node(original["id"])
        dependencies = original["dependencies"]
        candidate_leaves = [original]
        original_ids = {original["id"]}
        for attempt in range(1, 3):
            context = {"original_request": goal, "interpretation": brief,
                       "task_contract": original, "available_inputs": self.input_contracts(dependencies),
                       "inherited_prerequisites": dependencies, "feedback": feedback,
                       "attempt_history": history, "domain_rules": self.domain_rules,
                       "model": self.backend.default_model, "effort": self.backend.default_effort,
                       "remaining_budget": {"max_calls": self.budget["max_calls"] - len(self.state["calls"]),
                           "max_seconds": max(0, int(self.deadline - time.monotonic())),
                           "max_depth": self.max_depth, "current_depth": original["depth"],
                           "replacement_leaf_slots": self.max_leaves - len(self.leaves) + len(candidate_leaves),
                           "max_repair_attempts": 3 - attempt}}
            prompt = PromptGovernanceGate.default().render_template(
                "TASK_REPAIR", repair_context_json=context
            )
            record = {"task_id": original["id"], "attempt": attempt, "status": "repairing",
                      "original": deepcopy(original), "feedback": deepcopy(feedback)}
            self.state["repairs"].append(record)
            self.checkpoint()
            repair = await self.ask(
                prompt,
                "Mimir-Task-Repairer",
                field="repair_json",
                parent=original["id"],
            )
            record["proposal"] = deepcopy(repair)
            validate_repair(repair)
            action = repair["action"]
            if action in {"BLOCKED", "STOP"}:
                record["status"] = action.lower()
                self.state["planning_error"] = {"parent": original["id"], "reason": repair["reason"],
                                               "missing_inputs": repair["missing_inputs"]}
                raise ConfigurationRequired("Task repair stopped with unresolved work; inspect retained planning diagnostics")
            if action == "SPLIT" and original["depth"] >= self.max_depth:
                record["status"] = "depth_exhausted"
                raise ConfigurationRequired("Recursive depth limit reached; rejected task cannot be forced atomic")
            candidate_ids = {t["id"] for t in candidate_leaves}
            self.leaves = [t for t in self.leaves if t["id"] not in candidate_ids]
            before = len(self.leaves)
            if action == "REPHRASE":
                task = {**deepcopy(repair["tasks"][0]), "id": original["id"], "parent": original["parent"],
                        "depth": original["depth"], "dependencies": dependencies,
                        "blocked_by": sorted(set(original["blocked_by"] + repair["tasks"][0]["blocked_by"]))}
                if repair["tasks"][0]["dependencies"]:
                    raise ValueError("Rephrased task cannot introduce sibling dependencies")
                node.update(deepcopy(task), children=[])
                self.leaves.append(task)
            else:
                node.update(atomic=False, operation="split", max_input_items=0, children=[])
                await self.admit_tasks(repair["tasks"], goal, brief, parent=original["id"],
                    depth=original["depth"] + 1, inherited=dependencies, branch=node["children"],
                    inherited_blocked=original["blocked_by"], supplied_inputs=self.input_contracts(dependencies))
            candidate_leaves = self.leaves[before:]
            review = await self.review(goal, brief, candidate_leaves, original, dependencies,
                                       parent=original["id"], check_coverage=True)
            record.update(review=deepcopy(review), status="reviewed")
            history.append({"repair": repair, "review": review})
            if review["coverage_preserved"] and all(v["decision"] == "ACCEPT" for v in review["tasks"]):
                record["status"] = "accepted"
                new_ids = {t["id"] for t in candidate_leaves}
                for leaf in self.leaves:
                    if leaf["id"] in new_ids:
                        verdict = next(v for v in review["tasks"] if v["id"] == leaf["id"])
                        leaf["simplicity_review"] = deepcopy(verdict)
                        self.node(leaf["id"])["simplicity_review"] = deepcopy(verdict)
                    else:
                        removed_ids = candidate_ids | original_ids
                        leaf["dependencies"] = sorted({dep for dep in leaf["dependencies"] if dep not in removed_ids} |
                                                       (new_ids if set(leaf["dependencies"]) & removed_ids else set()))
                        self.node(leaf["id"])["dependencies"] = leaf["dependencies"]
                self.checkpoint()
                return
            record["status"] = "rejected"
            feedback = {"task_verdicts": review["tasks"], "coverage_gaps": review["coverage_gaps"]}
            self.checkpoint()
        self.state["planning_error"] = {"parent": original["id"], "reason": "Two repair attempts rejected"}
        raise ConfigurationRequired("Task repair limit reached; rejected work retained without execution")
