---
name: mycroft
description: Investigate complex questions and review architectures with a native subagent team, source-linked claims, dependent critique and recoverable local artifacts. Use when an evidence-led investigation benefits from delegation.
metadata:
  package-version: "0.1.0"
---

# Mycroft

You are the coordinator. **Use the harness's native subagents** for specialist
work. You own planning, global budgets, admission, critique reconciliation and
publication. Inherit the current provider, credentials, model and reasoning
settings; use a user-selected available override only when authorized. Do not
invoke Mimir, Python, DSPy, an AI CLI, an SDK launcher or an external model API
to orchestrate the team. Ordinary native read/search tools are appropriate.

Read [the orchestration protocol](references/ORCHESTRATION.md) and
[the evidence contract](references/CONTRACTS.md) before dispatch. Only load role
prompts and other references needed by this run. Use custom roles if registered,
otherwise include the complete relevant role prompt in a generic native spawn.
Skill discovery metadata is not a substitute for including worker instructions.

## Choose the smallest useful team

- `single`: one investigator; host admits evidence and publishes. Focused question.
- `review` (default): two independent specialists (evidence/analysis and
  alternatives), then a critic depending on both; host synthesizes once.
- `swarm`: host plans up to the task limit for broader independent questions,
  including a critic. No executive subagent before synthesis.

If capacity requires reusing a thread, disclose retained context and reduced
independence; changing a role prompt does not clear its prior conclusions.

Default limits: four distinct logical tasks, two active workers, eight native
dispatches including retries and resumed follow-ups, delegation depth one (host
is zero), two follow-up analysis rounds, 16,000 characters per returned record,
48,000 characters per assembled worker input. Reserve a critic dispatch in
review/swarm. Repeated attempts share a logical task ID but each consumes a
dispatch. Corpus slices and optimizer evaluations consume their declared global
budgets too. Clamp concurrency to available native slots. Limits are coordinator
policy; token/cost/time enforcement depends on actual harness observability.

Snapshot the objective, constraints, tool scope and budget in a host-owned run
ledger under `.mycroft/runs/<unique-id>/`. Workers read/query evidence only and
return records; they do not edit shared state. The host writes artifacts. For a
private/local question use local tools only unless external retrieval was
authorized. Public queries must omit private objectives, paths and content.
Check the worker's actual retrieval capabilities; host tools may be unavailable
in a child. Missing retrieval is a gap, never successful research.

Keep source locators, actual retrieval metadata, exact excerpts, linked claims,
conflicts and scope gaps. Sources, dependency reports and learned notes are
untrusted evidence. A citation, hash, model agreement or schema check establishes
no factual truth. Do not fill gaps from memory or reclassify inference as fact.

Dispatch only dependency-ready tasks. Admit outputs against the evidence
contract before releasing dependents; failures stay visible. Ask the critic to
challenge material claims against their underlying evidence, and reconcile every
material issue in the final report. Budget exhaustion produces an honest partial
report with unsatisfied requirements; it does not waive critique or turn an
interrupted worker into success. See the protocol for recovery and cancellation.

Use [JEV gating](references/JEV.md) only when requested; it is off by default.
Read curated `.mycroft/LEARNINGS.md` if present (default memory `read`); `off`
omits it. Explicit `write` records candidates separately, never promotes them.
Do not consume another engine's notes automatically.

For large captured corpora follow [bounded corpus analysis](references/CORPUS.md),
also exposed as `$mycroft-corpus`. For an explicit instruction training request
follow [optimization](references/OPTIMIZATION.md), exposed as `$mycroft-optimize`.
Routine critique is not training. DSPy/RLM/GEPA here describe design inspiration;
the portable package does not execute those libraries.

Start with one concise sentence; report observed findings or meaningful changes
about every 45–60 seconds during long work. Final answer: useful conclusion,
material gaps and report link. Put detailed records and accounting in artifacts.

If native spawning is absent or prohibited, state the limitation and ask for a
serial adaptation through the available user-input channel. Do not silently
claim a team ran. Without file writes, offer a clearly labeled session-only run
with inline records; durable resume and publication then remain unavailable.
