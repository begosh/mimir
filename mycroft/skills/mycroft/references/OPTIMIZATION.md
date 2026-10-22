# Explicit instruction optimization

This is a native-agent adaptation of reflective evolutionary prompt search,
inspired by GEPA. No upstream GEPA optimizer, DSPy compilation, executable-code
evolution or automatic instruction activation runs here. Routine critic/revision
work is not optimization. Evidence quality gains require actual comparisons.

## Freeze the experiment

Require a dataset with nonempty train/dev/held-out groups, case IDs, objectives,
captured evidence and reviewed evaluation criteria. Source/topic families must be
disjoint across splits. Reject duplicates, source leakage and unreviewed expected
answers before experimenting. The bundled acceptance corpus is a smoke fixture,
not a representative training dataset. If the user has no suitable dataset,
prepare a clearly labeled candidate rubric/dataset for review; do not manufacture
successful training scores.

Write an experiment ledger with dataset identity, case assignments, baseline
instructions, editable slots, tool/model/provider policy, metrics and direction
(`maximize`/`minimize`), concurrency and complete dispatch budget. Editable slots
are investigator instructions, corpus action guidance and extraction guidance;
evidence contracts, permissions, budgets, runtime/adapters and provider remain
fixed. Default one generation, two total candidates, 12 dispatches; compute the
full baseline/proposal/dev/held-out comparison budget before dispatch. Narrow the
experiment visibly if it will not fit. No hidden calls for mutation or grading.

Experimental tasks have their own cap, default `max_tasks=8`; the research
four-task default does not apply. Assign one logical task per case (repeated
candidate attempts use that ID), one proposal task, and separate grading tasks
if delegated. Every evaluation attempt still needs a fresh native context.
For T train, D dev and H held-out cases, baseline train/dev, candidate dev and
both held-out variants need `T + 2D + 2H` evaluator dispatches, plus one proposal,
any graders and reserved repairs. Candidate train reruns, if chosen, add T.
Plan logical tasks and dispatches independently. Retain all individual attempt
records; an experiment ledger uses its own statuses/comparison shape and is not
passed as an ordinary research run to `Test-Run.ps1`.

## Evaluate, reflect, propose, select

1. Record baseline train/dev results using fresh native evaluator contexts.
   Investigator packet contains the objective, captured evidence and candidate
   instruction text, never the expected answer, grader rationale or prior answer.
   Investigator tools are restricted to supplied evidence. Do not give it a
   dataset/grader file path that exposes the expected answer. If a fresh context
   and evidence-only scope cannot be established, do not label evaluation sealed.
2. Host or a separate budgeted grading role compares outputs to reviewed criteria.
   Record pass/fail for objective mechanical facts and separate labeled model
   judgments for entailment/relevance. Keep the grader transcript separate. Save
   actual missed claims, bad source links, tool/retrieval failures and budget
   observations. Do not ask the investigator to grade its own expected answer.
3. Evolver receives baseline instructions and **train/dev only** misses/traces.
   Propose one instruction change with parent ID, editable slot, rationale and
   expected tradeoff. Output is text/data, never commands, new tools or policy
   overrides. Host admits it only if immutable constraints are preserved.
4. Evaluate the candidate on the same dev cases with the same frozen conditions.
   Count failed cases and failures, not only successful outputs. Timing is
   observed harness time when available; missing usage stays unknown. A single
   faster trial is variation, not demonstrated speed gain.
5. Compute the nondominated set over configured comparable metrics. Candidate A
   dominates B only if no worse on every metric and strictly better on at least
   one. Any missing metric prevents that comparison; do not convert unknown cost
   to zero. Require no regression in evidence/failure-policy checks; keep baseline
   for ties or unestablished improvement. Pareto membership is not activation.
6. Freeze a selected candidate based on dev **before** held-out grading. Run
   baseline and frozen candidate on held-out evidence in fresh isolated contexts;
   graders alone see expected answers. Held-out answers, failures and summaries
   do not enter evolver feedback. A failed held-out test rejects selection; never
   tune on it. New tuning after inspecting it requires a new held-out dataset.
7. Publish the full comparison, dataset/rubric limitations, known usage and
   rejected/tied candidates. Produce a candidate manifest with version, parent,
   exact instructions/digests, editable slots, evaluation artifact identity and
   intended scope. Status stays `candidate` until explicit reviewed activation.

## Activate and recover

Explicit activation writes a data-only `reviewed` manifest containing the actual
review note, selected version, evaluation identity and scope. A new run may
select it by an explicit `instruction_manifest` locator. Verify its content and
policy slots; reject altered, unreviewed or foreign-scope manifests. Default
instructions remain selected when no manifest is provided. Roll back by omitting
the manifest in a new run. Never edit installed skills or curated learning as an
implicit side effect of training. A user can explicitly authorize those edits.

Resume with frozen dataset, policies and remaining dispatches. Failed/ambiguous
trials remain charged and recorded. Do not reuse results with changed inputs or
publish a selected candidate from incomplete comparisons. Distinguish human
reviewed judgments, model rubric estimates and mechanical checks in every result.
