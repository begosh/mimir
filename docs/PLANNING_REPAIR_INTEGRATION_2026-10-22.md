# Integrated recursive planning review and repair

Recursive planning (`mode=swarm`, `recursive_plan=true`) now reviews proposed
leaves before producing an executable DAG. This is enabled with recursive
planning; it requires no additional opt-in and leaves ordinary single/review
policies unchanged. Calls preserve the selected backend/model/effort.

## Behavior

1. Validate task contracts and local dependencies with code.
2. Review task simplicity in batches of at most four. A plan of four or fewer
   tasks can have its complete coverage assessed in the same review.
3. For a rejected task, preserve the original assignment and concrete feedback.
   `TASK_REPAIR.txt` selects REPHRASE, SPLIT, BLOCKED or STOP. Allow at most two
   repair attempts per original task, sharing the existing global planning limits.
4. Review each proposed replacement against the original assignment and checks.
   If rejected, retain the proposal/review and feed the failure into the next
   repair. No rejected replacement is admitted for execution.
5. Keep original prerequisites on every replacement. Replace downstream references
   to the original task with its accepted leaf replacements. Unaffected tasks stay
   intact; original objectives, proposals and reviews remain in the planning trace.
6. After repairs or multiple batches, check complete-plan coverage separately.
   The engine already provides final synthesis; no new specialist assembly task
   is required. Rejected coverage stops planning with an explicit gap.

Every interpretation, decomposition, simplicity review, repair, replacement
review and coverage call counts against the same default 8-call, 120-second
planning budget. All newly allocated tree nodes count against the node cap, and
splitting consumes depth/leaf slots. Budget/depth/repair exhaustion retains an
incomplete `.planning.json` and prevents dispatch. The trace includes exact
application prompts, raw outputs, known usage, review verdicts and repair history.
Execution checks accepted simplicity markers for plans carrying this new policy.
Previously saved plans retain their original policy for compatibility.

These are model judgments about plans, not independent proof of factual truth.
Execution-result rejection/retry, evidence artifact handoff, final answer checking
and DSPy/GEPA prompt optimization remain separate follow-ups.

## Verification

Focused tests cover accepted/rejected repairs, feedback history, rephrasing,
inherited prerequisites, downstream rewiring, unknown/duplicate review ids,
inconsistent coverage, call/leaf/depth/repair exhaustion, unavailable reviewer,
BLOCKED/STOP, persisted traces and execution of accepted replacements only.
Execution rejects a persisted replacement missing its accepted review marker.
Ordinary single/review and existing recovery paths are covered by engine tests.
The focused planner, engine, MCP transport and packaging checks passed: 66 tests.

## Live pizza observations

The first fresh integrated run used the saved interpretation but fresh
decomposition, native Codex, gpt-6.1-sol, low effort, memory/JEV off and no search.
It proposed nine leaves, took about 85 seconds and 7 calls, and was rejected by
whole-plan review. Batched reviewers accepted assignments that the final reviewer
then questioned; it also demanded specialist assembly already supplied by the
engine. The failure trace remains at
`.mimir/pizza-integrated-repair-20261022/checkpoint.planning.json`.

Separated complete-plan coverage from task simplicity to avoid competing verdicts
and explained engine assembly responsibilities. Clarified that an entire
multi-stage procedure is not one extraction field group merely because it is
copied from a page.

Then passed the earlier saved five-leaf pizza plan through the integrated gate,
reusing its completed decomposition rather than paying for another root call.
The live reviewer rejected the whole preparation method. Automatic repair split
it into mixing/kneading, fermentation/rests, and dividing/shaping; replacement
review accepted all three and complete-plan coverage passed. Seven executable
leaves remained and dependency integrity/acyclicity passed.

Review and repair added 41.594 seconds across five live text-only calls. Including
the two reused decomposition calls, the ledger has seven calls, within the
eight-call cap. Source/user prerequisites remain contracts: no recipe source was
retrieved and replacement research tasks were not executed. Raw calls, original
contracts, feedback and accepted repairs remain at
`.mimir/pizza-integrated-repair-20261022-reused-plan/planning.json`.

The positive run confirms the automatic planning path, not universal simplicity
or factual success. Some recipe sources may still have complex fermentation or
handling sections. The review gate adds runtime/context cost; no default budget
or effort was increased to accommodate it.
