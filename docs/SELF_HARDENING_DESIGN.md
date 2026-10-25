# The Self-Hardening Agent Swarm

Design discussion recorded 2026-10-22. This is an implementation backlog and
working design, not a statement that the full loop already exists.

Presentation title: **The Self-Hardening Agent Swarm**.
Proposed subtitle: **Eliminating hallucinations through recursive decomposition
& adversarial evolution**. Elimination is an ambition; current verification does
not establish that guarantee. Reducing hallucinations is the supported aim.

## Intended sequence

1. Interpret the original request: requested outcome, explicit constraints,
   ambiguity, missing information and evidence needs. Produce a sensible task
   statement without inventing requirements or losing the original wording.
2. Decompose that interpretation into small, checkable tasks. Keep the original
   request alongside it so a structured plan cannot silently pursue another goal.
3. Recursively split any task that is still difficult. Every specialist task must
   be "stupid easy": one clear operation, bounded input, compact output and an
   explicit completion check. Use ordinary code for deterministic calculations.
4. Execute eligible tasks up to the concurrency limit. Retrieve evidence only for
   unresolved needs, using focused queries or supplied sources.
5. Record results and provenance on the blackboard; apply narrow checks and
   red-team challenges before accepting results for dependent work.
6. Rephrase, retry or further decompose failed tasks within explicit limits.
   Recheck corrections and invalidate affected downstream results.
7. Assemble satisfactory component results into the requested answer, then check
   the assembly against the original request, accepted results and remaining gaps.
8. Publish the answer and evidence after checks and owned cleanup complete.

## Interpretation and decomposition

These are logically separate operations with separate outputs. Interpretation
answers "what does the user want?"; decomposition answers "what small tasks will
deliver it?". Separate outputs do not automatically require separate model calls.
Keep simple questions inexpensive and make the interpreted objective reviewable.

For "best Napoli pizza dough recipe", identify an actionable dough recipe with
quantities, preparation and fermentation. "Best" is ambiguous; authenticity is a
possible criterion, not a supplied constraint. Oven type, batch size and available
time may change the answer. Do not silently add toppings or assume a pizza oven.

Suitable small tasks include extracting flour/water quantities from a supplied
recipe, calculating hydration, extracting fermentation time/temperature, or
checking one source against one claim. "Research pizza dough" and "challenge the
entire recipe" are too broad for the intended specialist contract.

Current implementation: unconditional pre-planning search has been removed;
host briefs are supported and persisted. Swarm asks for a brief and tasks in one
planning call. Single/review can use a host brief or instruct workers to interpret
before tools. It does not yet enforce recursive task simplicity or a separate
semantic interpretation review. Live model-driven pizza planning failed with a
stream disconnection; host-supplied single planning passed without model calls.

## Worker settings and scheduling

Use the agreed **gpt-6.1-sol / low** profile explicitly. Narrow or split work
instead of silently raising effort, deadlines or context limits. Small tasks
reduce error risk but do not remove the need for checks or failure handling.

Task count and concurrency are independent. Eight tasks with concurrency three
means at most three active workers; another eligible task starts when a slot is
free. Dependencies control readiness and required input handoffs. Current Codex
execution creates fresh sessions per task. A reusable worker pool is a potential
performance experiment, not an agreed replacement; measure startup gains and
context contamination before deciding.

## Blackboard and adversarial checking

Keep findings, source locators, claimed support, uncertainty, failed checks and
corrections associated with their producing tasks and attempt versions. Stored
output is an assertion with provenance, not a proven fact. Conflicts remain
visible; a hash establishes byte identity only.

Current blackboard is engine-owned: completed results are stored and direct
dependency outputs enter a new worker's prompt. Agents cannot currently query or
update it live, post intermediate discoveries, or receive live peer updates.
Consider selective read/write tools when the correction loop needs them; avoid
broadcasting every result into every agent's context.

Red-team work must also be small. Example: supplied flour is 1,000 g, water is
650 g, and a worker reports 60% hydration. Check only that calculation: the
expected correction is 650 / 1,000 * 100 = 65%. Another task can check whether a
source supports "24 hours at room temperature" when it actually says refrigerated.
Criticism requires evidence too; do not accept a critic's disagreement as truth.

## Bounded rephrase, retry and recheck loop: to implement

After a failed check, preserve the failed attempt and the supported failure
reason. Rephrase the task more precisely, preserving its objective and acceptance
criteria. Supply the bounded inputs and concrete feedback; do not merely repeat
the same broad prompt or instruct the worker to agree with an unverified critic.

Proposed initial limit: **two retries, three attempts total per task**. This is a
working default to validate, with explicit run-wide attempt/time/token limits so
recursive splitting cannot evade the budget. Keep model and effort unchanged.
Each corrected result must pass its check before dependent tasks consume it.
If the task still requires several judgments, split it into easier components.
Invalidate or reconsider results that consumed an earlier rejected version.
Reuse unaffected satisfactory results. On exhaustion retain attempts, explain
the unresolved gap and prevent required failures from becoming published success.

Current implementation rejects invalid/oversized outputs and cancels dependents;
well-formed wrong answers can still enter the blackboard. Normal review performs
one broad critic task and synthesis, without an enforced correction/recheck loop.

## Assembly after satisfactory task results

Synthesis assembles accepted results into the requested deliverable. It must not
quietly introduce new factual claims or erase uncertainty. Check completeness
against the original request, source/claim consistency, compatible quantities and
assumptions, and incorporation of accepted corrections. A failure in the assembled
answer should produce a narrow correction task rather than restart the swarm.
Final checks should themselves be bounded. This assembly-check loop is proposed;
current synthesis does not independently establish factual correctness.

## Retrieval and performance follow-ups

- Keep preliminary raw-question search removed. Search follows interpretation
  and a specific missing-evidence need; long objectives remain intact.
- Doctor now has explicit native scout/curl probes for DuckDuckGo, Bing and
  Google. Distinguish TLS failure, proxy refusal and HTTP 200 without usable
  results. Honor enterprise CA configuration; keep certificate verification.
- Firecrawl keyless MCP returned usable pizza links/snippets on this machine.
  Integration is still pending; no connection was configured. Prefer compact
  search results (`highlights: false` in the probe), then fetch selected pages.
  Do not infer a verified best recipe from search snippets.
- Profile real duration, model/effort, cumulative input/cache/output usage and
  invocation count. Avoid unnecessary calls and context duplication.
- Small changes get affected tests and one practical check. Broad suite runs are
  reserved for substantial shared changes or delivery preparation, not every edit.
