# Revised pizza decomposition prompt: effort comparison

The revised general prompt separates role, limits, operations, clarification,
defaults, blockers, task context, output contract and final checks. Recipe rules
are supplied from `prompts/recipe_dough_rules.txt`, not embedded in general
decomposition instructions. Simple root components may be atomic, uncertainty is
preserved in predicate checks, and a structured `planning_error` stops a component
that cannot fit the limits. Partial plans now retain exact application prompts.

Code enforces child counts, grouping/leaf contracts, dependency validity and
global limits. Pending siblings reserve at least one leaf slot each. Recursive
calls receive parent input contracts and prerequisite expected outputs, so those
inputs need not be mistaken for external blockers. Semantic task simplicity,
evidence adequacy and source-to-claim entailment remain review responsibilities.

## Controlled setup

- Original request: `Give me the best napoli pizza dough recipe.`
- Identical saved interpretation from the earlier pizza run, reused without a
  new interpreter call for each effort. This isolates decomposition.
- Model: `gpt-6.1-sol`; three separately selected efforts: low, medium, high.
- Production native Codex SDK, text-only calls through InvocationBroker.
- Identical root prompt, recipe rules and limits: 8 calls, 120 seconds, 32 nodes,
  12 leaves, maximum depth 3. No research execution, search or synthesis.
- One observed plan per effort; these are sample measurements, not averages.

The initial shell Python lacked the required SDK and failed locally before model
work. The live comparison used the repository `.venv` with openai-codex 0.163.0.
Low and medium root completions declared zero output words for a non-executable
grouping. Contract validation initially rejected this. Zero output words are now
allowed only for groupings; executable leaves still require a positive bound.
Both root responses were replayed after checking their complete prompt/options
input identity. No root model call was repeated. The high process had already
loaded the earlier validator but returned a positive grouping output bound and
completed successfully under those stricter constraints.

## Observations

| Effort | Decomposition time | Model calls | Leaves | Reported tokens | Output tokens | Reasoning output tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| low | 26.6 s | 2 | 5 | 30,974 | 1,044 | 109 |
| medium | 33.6 s | 2 | 5 | 31,381 | 1,447 | 515 |
| high | 104.9 s | 3 | 6 | 49,277 | 4,416 | 3,152 |

Low/medium time includes the original paid root duration plus the continuation,
excluding the intervening debugging wait. High is an uninterrupted run. Root
completion times were 15.8, 22.3 and 48.1 seconds respectively. Root application
prompts were identical (4,778 characters); native reported input was 14,895 tokens
per root call. Each subsequent call also reported about 15,000 input tokens. The
runtime context is therefore a substantial part of the measured token overhead.
No cached input tokens were reported in these samples. Reported token totals
are cumulative across calls, not unique context or evidence of billed cost.

All three plans used an explicitly disclosed traditional-Neapolitan interpretation
of "best" and had no user-clarification blockers. They avoided inventing a user
yield, oven, preparation deadline, quantities or source URLs. They extracted yield
before other fields and stayed within dough-only scope.

Low and medium produced essentially the same five leaf assignments:

1. Retrieve one coherent recipe source using one query and at most two hits.
2. Extract declared yield, or report it unstated.
3. Extract source ingredient quantities without scaling.
4. Extract preparation/fermentation steps.
5. Check explicit source identification as Neapolitan dough, preserving uncertainty.

High added a separate extraction of supporting source statements before the
suitability predicate. Its checker more explicitly distinguishes affirmation,
denial and absence. That improves one task boundary, but does not establish that
the recipe is objectively best or independently authentic.

## Remaining plan quality problems

- Every effort still labels the entire dough method an atomic extraction. This
  can hide several steps, times and temperatures; the "STUPID EASY" requirement
  is not independently enforced.
- All chose a meaning for "best" without clarification. The assumption is
  disclosed, but whether it materially changes the result remains unverified.
- Retrieval remains planned because the saved interpretation requested source
  support. This comparison does not prove that search is necessary for a normal
  recipe question. No search actually ran.
- Low requests a recipe-bearing excerpt within 150 output words; high's retrieval
  explicitly requests only identity/yield excerpts, then later leaves require
  ingredient and method text. Medium names a retrieved-page input, but production
  artifact handoff has not been validated here. Source content must be preserved
  separately from a short result so dependent extraction can consume it.
- Inherited graph dependencies still include prerequisite outputs that a leaf's
  named input list does not use. Selective execution context remains pending.
- Written acceptance checks were inspected, not executed against research results.

Low is the preferable default for this sample: medium added little structural
value, while high took approximately four times as long. Repairing task admission
and evidence handoff is more useful than changing every worker to higher effort.
The agreed ordinary worker profile remains low; no saved profile was changed.

## Evidence and verification

- Raw root completions and prompts:
  `.mimir/pizza-prompt-effort-comparison-20261022-live/`.
- Low/medium continuation traces, prompts and usage:
  `.mimir/pizza-prompt-effort-comparison-20261022-replayed/`.
- Reproduce with `scripts/benchmark_recursive_planner.py` using the saved
  interpretation and explicit domain-rule file. Each output directory is new;
  root replay requires matching input identity.
- Focused recursive-planner/engine checks: 30 passed. Full suite was not run.
