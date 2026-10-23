# First recursive planning test: pizza dough

Implemented opt-in `recursive_plan` for swarm mode. Interpretation is a separate
saved output consumed by decomposition. Components declared non-atomic are split
recursively, with deterministic leaf/node/depth/call/time admission. Leaves carry
one operation, named bounded inputs, expected output, acceptance check, blockers
and dependencies. Dependency expansion preserves parent prerequisites. Partial
tree, leaves, original responses and known usage survive planning failure.

The model's atomic declaration and acceptance-check text are not independent
semantic validation. Input item/page-read limits remain instructions rather than
native tool enforcement. The generated plan still needs review. This stage does
not implement red-team corrections, result retries or final assembly checks.

Live input: `Give me the best napoli pizza dough recipe.`
Model/effort: gpt-6.1-sol / low; native Codex, text-only planning, memory/JEV off.
Planning limits: 8 calls, 120 seconds, 32 tree nodes, depth 3, 12 executable leaves.
Run: `.mimir/runs/5a887bb5d89546f9a815a95038cdc165/checkpoint.json`.

## Observed interpretation

- Outcome: a recommended Neapolitan pizza dough recipe.
- Explicit constraints: none.
- Components: ingredients and method.
- Evidence need: support for suitability for Neapolitan pizza.
- Missing information: meaning of best, equipment, quantity and preparation time.

The planner did not invent equipment, recipe quantities or source URLs. It kept
the dough-only scope and original question.

## Observed leaf plan

1. Clarify the primary meaning of best.
2. Retrieve one source matching that criterion: one query, at most two hits,
   at most one selected page.
3. Extract baseline ingredients and amounts from that source.
4. Extract its declared yield, or report absence.
5. Extract its ordered dough preparation method.
6. Extract its stated support for suitability/selection claims.
7. Check explicit identification as Neapolitan dough.
8. Check support against the clarified selection criterion.

There were four top-level components, three recursively expanded; eight leaves
at depths 1-2. Kahn validation passed. Run stopped after planning, with no source
retrieval and no research workers.

## Measurements and limits

Planning completed in 55.63 seconds using five successful text-only calls:
one interpretation (4.94s) and four splits (14.83s, 13.55s, 10.95s, 11.25s).
Cumulative native reported tokens: 73,845, including cached input. This is neither
unique context nor a billed cost. Recursive planning is materially more expensive
than host interpretation and is not justified for every recipe request.

The first attempt retained its interpretation but failed because a non-executable
grouping had zero inputs. Groupings now permit zero; executable leaves require
1-2. Additional focused checks cover inherited blockers and input-count admission.

Plan quality limitations: the planner makes "best" a clarification blocker,
although a disclosed criterion could be a preferable product choice. It assigns
some broader dependencies than the named inputs need; that can duplicate context.
Extracting an entire preparation method may remain broader than the intended
stupid-easy leaf standard. The source's own suitability claims do not independently
establish authenticity or bestness. These are visible review issues, not passed
factual checks. Later changes preserve blockers through child splits and reject
declared input overflow; those were verified with focused tests, not another live
model run.
