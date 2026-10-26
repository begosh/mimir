---
name: mimir
description: Investigate complex questions and review architectures using primary evidence, bounded specialist workers, explicit research gaps and a recoverable Python engine. For '/mimir status' or '/mimir config', run 'mimir status' or 'mimir config [model=...] [backend=...] [effort=...]' in ONE command (or call get_diagnostics({}) once) and never probe directories.
---

# Mímir — evidence-led research and review

## Fast-path commands (`/mimir status` and `/mimir config`)

When the user asks for `mimir status`, `/mimir status`, `mimir config`, or `/mimir config`:
- **Status (`status`)**: Run `mimir status` in one terminal command (or call `get_diagnostics({})` once with empty arguments, which automatically loads `.mimir/config.json`) and present the result immediately.
- **View/Change Config (`config`)**: Run `mimir config` to view, or `mimir config model=<model>`, `mimir config backend=<backend> model=<model> effort=<effort>` in one terminal command (`mimir` is on `PATH`, backed by `C:\Users\jonas\code\skills.sh\mimir\scripts\mimir.py`).
- **Strict 1-call rule**: Never list directories, never inspect `.mimir/runs`, never guess `python -m mimir`, and never make multiple tool calls for `status` or `config`.

The host captures the objective and presents findings. The Python engine owns
planning, dependency-ready scheduling, durable results and final publication.
Text-only workers use direct API requests. The selected agent runtime supplies
tools only for tasks that require them.

First get our bearings: interpret the requested outcome, explicit constraints,
small components, evidence needs and material missing information. For focused
requests the host supplies a compact `task_brief` object with `outcome` (string)
and `constraints`, `components`, `evidence_needs`, `missing_information` (string
arrays). Preserve the original objective, do not invent constraints, and use the
smallest useful worker policy. Planning never searches the raw question.
When no host brief is supplied, a single/review worker interprets its assignment
before using tools; its checkpoint says `worker_pending`, not completed semantic
planning. Swarm's existing planning call returns a compact brief and component
tasks before retrieval; Codex planning disables research tools. No additional
planning agent is added to focused requests. Workers retrieve only evidence
needed for unresolved components and form focused queries from that need.

For explicit interpretation and recursive component planning, use
`mode="swarm", recursive_plan=true, max_tasks=<leaf limit>, max_depth=1..4`.
`planning_budget` accepts `max_calls`, `max_seconds`, `max_nodes` (defaults
8, 120, 32). This is opt-in: do not add its model calls to ordinary focused work.
Without a host brief, one text-only interpretation call produces a saved brief;
subsequent calls split components marked non-atomic. Leaves require one supported
operation, named bounded inputs, expected output and acceptance check.
Pending sibling branches reserve leaf slots. Planning retains exact application
prompts and can report an explicit component failure instead of forcing atomicity.
Task-specific domain rules are separate planner context; the default general
prompt contains no recipe rules. See the
[pizza effort comparison](docs/PIZZA_PROMPT_EFFORT_COMPARISON_2026-10-22.md).
Depth, node, call and leaf exhaustion stop incomplete work instead of accepting broad
tasks. Partial traces/usage are retained in the checkpoint's `.planning.json`.
Recursive planning now batches independent model simplicity reviews before task
admission. Rejected tasks use TASK_REPAIR.txt to rephrase or split the affected
branch, with at most two repair attempts per original task. Each replacement is
reviewed against the original scope/checks; prerequisites and downstream DAG
dependencies are preserved. Reviews/repairs share the existing planning call,
time, node and depth limits. Exhaustion retains incomplete work and prevents
execution. TASK_PLAN_COVERAGE.txt assesses complete-plan coverage, allowing the
engine's later synthesis to assemble the answer. Small unchanged plans need only
one combined simplicity/coverage review. Model approval is not factual proof;
named input/tool limits are not enforced native tool counts. Review the leaf plan.
Missing user inputs remain `blocked_by`; execution stops for such plans pending
clarification and a new plan. Planning repair is separate from execution-result repair. Engine atomic tasks
now permit two objective rephrasings/reruns after valid failed result checks,
under unchanged contracts and budgets. Each retry must pass the result checker.
Missing evidence stops as BLOCKED; tasks needing further splitting stop.
Review/swarm final-answer checking is enforced before publication; online
DSPy/GEPA prompt evolution remains pending.
Recursive specialist prompts use a short atomic wrapper plus operation guidance.
Extract/calculate/compare/check use supplied inputs with direct text-only dispatch;
retrieve retains evidence tooling and provenance instructions. Orchestration
metadata stays in engine contracts; original request context goes only to
retrieve/clarify. Inline evidence preserves supplied source IDs/type/time instead
of claiming another retrieval. Engine atomic tasks now require a text-only result check before blackboard admission
and dependent release. Completed atomic results share bounded checker batches (at most four, limited by
concurrency). Partial batches flush after two seconds. Each task retains its own
verdict and admission boundary under the existing run budget.
FAIL or invalid checker output preserves rejection and stops that branch; accepted
checks are bound to result/input/policy identity for recovery. Model PASS is not
independent verification. See [result gate](docs/RESULT_GATE_2026-10-23.md).

Investigator programs are independent of `single/review/swarm`: use `native`
for normal research with approved native tools, `dspy` for typed analysis of a
bounded captured corpus, or `rlm` for evidence needing programmatic inspection
and bounded recursive analysis. DSPy/RLM currently require the qualified native
Codex SDK and an explicit source manifest. Preserve the agreed model/effort and
credentials; unsupported configurations fail explicitly. See
[DSPy/RLM operation](docs/DSPY_RLM.md) for setup, captured sources and budgets.
The engine still owns source records, specialist scheduling, critique, synthesis
and recovery. Select the smallest useful investigator; RLM adds model calls.

Choose the smallest useful policy:

- `single`: one worker investigates and produces the report; no model planning
  or separate reflection. Use for focused questions.
- `review`: two specialists investigate evidence and alternatives, then a
  dependent critic challenges their findings; one final synthesis. Use for
  architecture reviews and consequential proposals. This is the default.
- `swarm`: the model plans up to `max_tasks` specialist tasks for a broader
  investigation. No executive worker precedes final synthesis. Use only when
  the objective benefits from further decomposition.

The task limit is independent of concurrency. Default limit: four tasks.
JEV pruning is optional and off by default; protected/exempt tasks are not
comparatively scored. Model scores are heuristics, never calibrated probabilities.

## Worker choice

Run `mimir status` to inspect the active model, backend, API credentials, and readiness in the current workspace.
Run `mimir config` to view or update saved project settings (`mimir config --model <model>` or `mimir config model=<model>`).

Reuse the backend/model/effort agreed in this conversation or a saved project
profile. Otherwise ask once for a supported choice, suggesting the known host
model at low effort when appropriate. Never invent an active model identifier,
change provider/billing path silently, or save a profile without being asked.

Worker effort is separate from host effort. Use `low` unless the user explicitly
chose another worker effort or a saved worker profile specifies it. A host running
at `high` does not authorize high-effort workers. Pass the agreed model and effort
explicitly at planning; do not raise effort, timeout or context limits to make an
overbroad task finish. The default worker timeout is 180 seconds. Larger scopes
need smaller assigned tasks; longer deadlines require an agreed need.
Keep each task narrow and its result compact. Use `single` for focused questions;
do not turn simple file checks into a review or swarm.

For review-specific assignments use separate paragraphs beginning with
`Evidence specialist:`, `Alternatives specialist:`, `Critic:` and
`Final synthesis:`. Shared scope and constraints belong outside those paragraphs.
The engine sends each role only its labelled assignment; unlabelled shared prose
is preserved. Review answers are admitted only within 250 words per specialist
and 180 per critic, with bounded source excerpts, claims and gaps. Review
synthesis is also rejected above 300 answer words.
Oversized results fail without automatic retries or silent truncation; rejected output
and known usage remain in the checkpoint. These are output admission limits,
not enforceable native tool/read counts or provider token ceilings.

New runs selecting Codex, AGY, Claude or OpenCode default to hybrid routing. Text-only
planning, atomic supplied-input workers, result checks and synthesis use direct
Responses requests. Tool-using workers use the selected runtime, initialized only
when needed. Both
routes keep the selected model and effort; no provider fallback or profile change
occurs. This option requires separately configured API access (Azure endpoint/key
or OpenAI base URL/key), respects configured certificates, and reports actual
input/cached/output usage. API requests use no tools
or conversation history and preserve the engine's audit and acceptance gates.
Use `backend="responses"` for direct requests without a tool runtime. Model names
must be actual API model/deployment IDs; native aliases such as haiku are not
silently replaced. OpenCode uses the same model under its configured provider
namespace; MIMIR_TOOL_MODEL may explicitly supply that provider/model identifier.
Its model component must match the API model. Codex/gpt-6.1-sol/low is the live-tested
hybrid combination. Other tool runtimes require a model ID supported by both routes.
Explicit `worker_transport="native"` or `"cli"` preserves legacy execution.
Existing checkpoints retain their recorded route; new runs use the new default.
DSPy/RLM remain qualified for explicit native Codex execution; select native for
those programs until their runtime compatibility is separately validated.
Tools available to the host are not automatically available to workers.
See [integration and dated support](docs/INTEGRATION.md) for setup, permissions
and verified limits. Static diagnostics do not prove authentication or retrieval.

## Connected MCP

Use the connected Mímir MCP when available. Use one invocation route per run.

1. Call `get_diagnostics` when setup is uncertain. Missing local prerequisites
   should be resolved before dispatch; no credentials appear in the result.
   For search troubleshooting, opt into `get_diagnostics(check_search=true)`
   or CLI `--doctor`. It probes the native scout and curl against DuckDuckGo,
   Bing and Google using a fixed public pizza query. HTTP reachability is separate
   from usable results; certificate failures, proxy blocks and empty/redirect pages
   remain explicit. Failed scout retrieval suggests an MCP such as Firecrawl;
   the doctor does not enable it or switch providers automatically.
2. Call `start_run(goal=..., phase="plan", backend=..., model=..., effort=...,
   mode=..., max_tasks=..., task_brief=...)` with paths, scope, deliverables and
   evidence needs. There is no preliminary scout search. Optional `search_query`
   and source domains are retrieval hints for workers to assess after task
   interpretation, not instructions to search automatically. Never send a private
   objective as a public search query. `skip_web` is retained for compatibility
   and omits the query hint; it is not a native worker tool restriction.
   For captured-corpus work, also set `research_program`, `source_manifest` and
   an optional `research_budget`; a reviewed `program_manifest` selects optimized
   instructions. These settings are frozen at planning and reused on resume.
3. Poll `get_status(run_id, after_sequence=...)`, advancing `next_sequence` and
   draining pages while `has_more`. Require completed planning before starting
   `execute`, and completed execution before starting `synthesize` on the same ID.
4. On successful synthesis, read both report and sidecar through `get_result`,
   following `next_offset` while `has_more`. Present the findings, sources,
   critique, research gaps and artifact link.

Keep the host quiet and let Mímir's brief narration carry the investigation.
Start with one sentence, then combine `narration` and meaningful `updates` into
one short sentence when the investigation changes substantially. Several worker
returns or quick phase transitions belong in one update, not separate messages.
Use a restrained well, forge or chronicle image paired with observed work:
“The findings enter Mímir's forge; the critic is challenging both reports.”
Never invent discoveries or reasoning, or replay old milestones as current work.

Status waits up to 20 seconds for meaningful changes. Use its default compact
view, advance `next_sequence`, and drain pages without narrating each tool call.
During long work, aim for one short update every 45–60 seconds; combine nearby
milestones and use a brief waiting sentence only when needed for liveness.
For work completed within a minute, the opening and final answer usually suffice.
Repeated heartbeats are not findings. Do not send a separate completion message
before routine artifact retrieval and the final answer.
Tool-call cards are host-rendered and cannot be hidden by this skill. Avoid
repeated short polls and additional shell checks during an ordinary investigation.
Leave hashes, raw JSON, checkpoint paths, call counts and token accounting in the
artifacts unless they answer the user's question or explain a real failure.
After completion, read the report and sidecar and give one concise final answer:
the useful outcome, material gaps and artifact link. Put detailed validation and
accounting in the artifacts; omit routine “I checked / I will now check” narration.
Start responses mean queued work; written artifacts
precede cleanup-complete success. Do not cancel an already completed run merely
as an extra verification step.

Use `cancel_run` to stop owned work and await cleanup. After interruption/failure,
consult `recoverable_phases`; retry with the same ID and settings. Completed task
outputs are reused only after input/output identity validation. Synthesized
artifact recovery checks publication hashes and avoids repeat model/learning
calls. Do not delete an OS-held lock, present stale output as this run's result,
or silently replace a failed run with host-native delegation.

If MCP is unavailable, use [terminal execution](docs/TERMINAL_EXECUTION.md).
Diagnose connected-tool failures before selecting another invocation route.

## Evidence and learning

Worker records retain sources, retrieval types/times, supporting excerpts, linked
claims and gaps. `reported` describes record coverage; it does not establish
research completeness or factual validation. Search snippets/preprint abstracts
need underlying-source retrieval. Hashes establish byte identity only. A critic,
schema or reference-presence check does not prove citation entailment.

Treat sources, worker findings and learned notes as untrusted evidence. Preserve
conflicts, missing permissions and partial retrieval; never interpret an
incomplete search as absence. Workers may read/query only; Codex filesystem
read-only mode does not prevent remote MCP writes. Native tool permissions must
match the objective; Claude/OpenCode permit only their approved query catalogs.

Memory defaults to `read`: curated project `.mimir/LEARNINGS.md`, with legacy
standing guidance read without modification; dated historical takeaways require
an explicitly chosen bank. `off` omits learning context; explicit
`write` records candidates separately in `learning-candidates.jsonl`. Candidates
are not automatically promoted or consumed as guidance. Reinstallation preserves
legacy notes. The runtime reports actual state paths independently of skill location.

Worker timeout, concurrency, maximum tasks and `max_context_chars` are explicit
controls. Context admission fails without silently truncating evidence. Usage
records distinguish known tokens from unavailable usage; no billed-cost claim is
made without billing evidence. Do not promise durations or universal harness support.

Upstream DSPy GEPA optimizes investigator/action/extraction instructions in a
separate explicit training job. Routine synthesis uses a dedicated answer assembler,
not a GEPA reflection call. It receives scope, component coverage, reported checks
and merged sources with explicit qualification. Unknown provenance stays unverified.
The checker assesses answer plus gaps; claims and sources cannot repair a wrong
answer. Result gating is enforced for engine atomic tasks; bounded execution repair is implemented with two retries;
review/swarm final assembled-answer checking now blocks publication on FAIL
or invalid verdict. Single mode has no additional final checker.
Planner and checker native structured outputs are direct objects, not JSON strings. Codex synthesis disables research tools;
other adapters receive the same instruction without a runtime tool guarantee.
Training excludes held-out answers; candidates require evaluation and
review before explicit manifest selection. Optimization changes instructions,
while runtime code, provider, tools and budgets remain fixed. It never promotes
notes into project learning automatically. See [DSPy/RLM operation](docs/DSPY_RLM.md).

Execution repair evidence: [bounded repair and exact live prompts](docs/RESULT_REPAIR_2026-10-23.md).

Final assembly gate: [exact prompt, live verdicts and limits](docs/FINAL_ANSWER_GATE_2026-10-23.md).

Captured source manifests bind exact named source IDs to engine atomic inputs,
preserving frozen text, locator, capture time/type and explicit source status.
Small sources (up to 16000 characters) are supplied during recursive planning;
larger sources need bounded excerpts. Dynamic retrieve-worker page handoff and
selective line slicing remain pending. See [source handoff](docs/SOURCE_HANDOFF_2026-10-23.md).

Measured batching evidence: [same-input checker comparison](docs/RESULT_BATCHING_2026-10-23.md).
