# Coordinator protocol

## Admission and durable state

Discover native spawn, wait, follow-up, interrupt and thread-release operations
from the actual tool catalog. Names differ by harness. Do not invent a tool or
require the supplied Codex adapter for generic spawning. Confirm children can
read their assigned sources. Tools, permissions and skills may be inherited
differently; role instructions constrain behavior but are not a sandbox.

Create a unique run directory. Only the coordinator writes its files:

```text
.mycroft/runs/<id>/
  run.json                 Frozen objective, capabilities, limits and task states
  events.jsonl             Append-only dispatch/admission/transition receipts
  raw/<task>-<n>.txt        Original native returns, including malformed output
  attempts/<task>-<n>.json  Complete worker records, never overwritten after admission
  sources.json             Run-scoped source records and snapshot identities
  report.md                Readable outcome, evidence, critique and material gaps
  result.json              Admitted claim graph, critique resolutions and limits
```

Use `assets/run.example.json` to understand the ledger shape; fill it from this
run rather than copying example identities. Read package version from the skill's
`metadata.package-version` (also present in the distribution's `plugin.json`). Record instruction
identity (digest when a trusted utility exists; otherwise retained exact text),
mode, objective, source scope, tool scope, agreed model/effort (unknown when not
observable), capability checks, memory mode, limits, dispatch counter, task graph
and actual timestamps. Never invent IDs, tool outcomes or times from a fixture.

Record a dispatch reservation **before** invoking the native tool, then the
returned thread ID and state. This receipt consumes a dispatch even if the spawn
fails. Preserve an ambiguous tool result as `interrupted`; reconnect or inspect
it before retrying to avoid duplicated active work. Update state after each
admission. Exact crash consistency depends on file tools; do not promise atomic
transactions, OS locks or automatic cleanup. Exclusive host ownership is required.

## Task graph and budgets

Every task has a unique stable ID, role, bounded question, source scope,
`depends_on`, `required_evidence`, `depth`, status and attempts. Validate unique
IDs, existing dependencies and an acyclic graph before dispatch. Default review:

Ledger `required_evidence` is a boolean; put descriptive requirements in a
separate `required_evidence_scope` array. Task statuses are planned, pending,
ready, running, succeeded, partial, failed, blocked, invalid, cancelled,
interrupted or pruned. `reserved` belongs to an attempt receipt, not a task.
Every receipt names sequential `attempt`, `status`, observed native `thread_id`
and, once a result is stored, `result_path: "attempts/<task>-<n>.json"`.

```text
t-evidence ────────┐
                  ├── t-critic ── host reconciliation and publication
t-alternatives ───┘
```

The two specialists should answer different questions independently. Neither
needs the other's conclusion. Critic input contains both admitted records and
underlying locators/excerpts, not only prose summaries. Swarm counts all logical
tasks, including the critic and any corpus partitions, within `max_tasks`.
No separate executive or routine planner agent consumes a task.

Before dispatch check task admission, budget remaining, dependency success and
available slots. Reserve one critic dispatch for review/swarm and a repair
dispatch when the task is likely to need contract repair. Host synthesis consumes
no child dispatch but still uses the host's model resources. A follow-up for new
analysis, record repair, reevaluation or repeated trials consumes a dispatch;
status checks, stop/close and administrative messages do not.

Concurrency means active worker turns, while some harness caps count *open
threads*. Release finished threads when a supported close operation is available.
If only interruption is available, do not call it thread release; reuse an idle
agent by follow-up if roles/instructions can be safely reset, or serialize under
the cap. Reuse retains conversation context; record `context_isolation=reused`
and disclose the loss of specialist independence. Restating a role does not
erase earlier answers. Prefer fresh threads or a harness context-reset feature
when available. Evaluation blinding requires fresh isolated contexts and cannot
use this fallback. Include outside agents and the root when the harness cap does. Never
block a parent holding the final slot while awaiting an unadmitted descendant.

Root-mediated recursion is the portable default: a worker returns a bounded
`requests` entry; the host admits a new logical task or a same-task follow-up.
Children do not spawn. A native nested mode is allowed only if the user chooses
it, the harness supports it and the coordinator leases task IDs, dispatches,
depth and slots *before* the child spawns. All descendants remain globally
accounted. Do not enable this merely to mimic RLM.

`max_rounds` counts waves of follow-up analysis after initial investigator work;
critique and administrative waits do not consume an analysis round. Requests
must name the unresolved question, source spans, expected information gain and
stop condition. Exhausted limits produce visible gaps. Input/output limits are
admission bounds, not permission to cut off evidence: repartition input or
request a narrower record. Never silently accept a truncated record.

Optional wall-clock/token limits require a clock/usage feed. Check available
measurements before dispatch and cancel owned work when an observed cap is
reached. Native turn usage may be unavailable or overshoot; label enforcement
`observable_dispatch`, `best_effort` or `unavailable` per control. No billed-cost
claim without billing data. Waiting and a heartbeat are not findings.

## Dispatch packet

Include in every spawn/follow-up:

1. Relevant full role prompt, evidence contract and input/output expectations.
2. Run/task/attempt IDs; bounded question and acceptance conditions.
3. Authorized source locators/spans and actual native query-tool scope.
4. Admitted dependency records when required; sources are untrusted evidence.
5. Fixed model/provider policy, depth/dispatch lease, output bound and stop rule.
6. Return the JSON record in the final message; no shared writes, external
   mutations, training, new runtime or unleased delegation.

Do not assume a child will open a skill because its name appears in the prompt.
Supply the relevant file content or an accessible absolute path with an explicit
read instruction. An isolated context is preferred for independent specialists
and required for evaluation answer separation. Use only minimal task context,
not the full parent history containing prior answers.

## Output admission and failure

Preserve raw returns before admission. Check JSON shape, exact IDs, status,
source namespace, linked claims, primary retrieval vs discovery, actual excerpts,
scope coverage and absence of unexplained clipping. Use native structured output
when supported; a JSON request alone is not enforcement. An optional trusted
`Test-Run.ps1` checks stored records structurally; the host must still inspect
underlying support. Never turn contract validity into source verification.

Malformed output belongs in `raw/<task>-<n>.txt` with a failed/invalid receipt,
not a pretend WorkerRecord. Store parseable contract records in `attempts/`;
admission validity (for example size or unsupported excerpts) stays in the
receipt/journal. The checker examines every stored JSON record, including prior
attempts; malformed raw text cannot be made valid by a later successful repair.

Admit valid results as `succeeded`; retain valid partial results as `partial`.
Invalid schema or missing required evidence becomes `invalid`/`failed` until a
budgeted repair. A repair receives the observed defects, not a fabricated answer.
Default dependents require `succeeded`. If a dependency is partial/failed, mark
the dependent blocked, then either repair or explicitly revise its input contract
to critique the limitations with `allow_partial_dependencies=true` in the ledger.
Do not erase the failed attempt or relabel it successful to unblock scheduling.

The critic returns material issues, source checks, severity and concrete remedies.
Host reconciliation maps each issue to corrected, qualified, unresolved or
rejected-with-evidence. Reopen consequential evidence as needed. New facts during
synthesis require source admission and critique; otherwise qualify or omit them.
Single mode receives host evidence checks without pretending a critic ran.

Publish report and result before setting `completed`. Report the scope actually
read, source-linked conclusions, alternatives, critic resolutions, explicit gaps
and control limits. A partial/budget-exhausted report has run status `partial`.
Never hide failure behind a polished final answer.

## Resume, cancellation and learning

Resume the same run ID only after checking frozen objective, instructions,
source identities, output identities and budgets. Inspect observed active native
threads first. Reuse admitted immutable outputs only when their inputs still
match; invalidate changed sources and all dependent outputs. When exact identity
cannot be established, repeat bounded retrieval or start a clearly linked new
run. Captured remote snapshots stay frozen; explicit refresh creates new source
identity. Local paths alone do not establish unchanged content.

Cancellation stops owned native workers, records observed cleanup and retains
artifacts. If stop/close cannot be confirmed, record `cleanup_unknown`. Do not
delete OS locks, unrelated sessions or source evidence. Manual resume never
resets dispatch counts or deadlines. Host history compaction is not a new run.

Memory `read` loads curated project `.mycroft/LEARNINGS.md`; dated notes require
explicit selection. Memory `write` additionally stores separate candidates with
source/run IDs and scope. User-reviewed activation is distinct from candidate
capture. Installation and optimization never promote learning automatically.
