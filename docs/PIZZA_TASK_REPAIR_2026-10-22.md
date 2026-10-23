# Pizza task repair prompt: live experiment

Tested `prompts/TASK_REPAIR.txt` with the saved low-effort pizza preparation
contract and host planning feedback that it combined several preparation stages.
Model: gpt-6.1-sol, effort low, production native Codex SDK, text-only calls.
The input source was a future prerequisite contract, not an actually retrieved
recipe. No research execution, recipe retrieval or task-result validation ran.

## Repair and review

The first repair selected SPLIT and returned three leaf contracts:

- Mixing and kneading: 50 output words.
- Fermentation and rests: 50 output words.
- Dividing and shaping: 50 output words.

Each named the chosen source excerpt as its one input, required source-order
markers and references, retained stated times/temperatures, and explicitly
reported missing details. The independent simplicity reviewer accepted each
task's size but rejected overall coverage, believing the yield dependency had
been lost. This was a review-context problem: the original external prerequisites
are intended to remain inherited by every replacement child. Local dependency
lists contain only sibling ids.

Updated the reviewer prompt to explain inherited prerequisites and checked the
proposed dependency attachment with code. A single recheck no longer objected
to ordering, but found a substantive scope gap: handling between rests, such as
source-present folds, was excluded by all three child scopes.

Fed that review finding into a second repair of the original task, preserving the
earlier repair in attempt history. This produced four leaf contracts:

| Child | Output bound |
| --- | ---: |
| Mixing and kneading | 40 words |
| Fermentation and rests | 40 words |
| Dividing and shaping | 35 words |
| Intervening handling and preparation setup | 35 words |

The fourth assignment explicitly covered source-present folds, turns, transfers,
covering and related setup outside the other scopes. These are extraction
categories, not claims that a retrieved pizza recipe contains those actions.
The reviewer accepted all four and returned coverage_preserved=true with no
coverage gaps. This is model assessment of a plan, not proof of factual correctness
or sufficiency for every possible recipe source. A complex fermentation schedule
or handling section may still need further splitting once its input is known.

## Measured overhead

- First repair and review: 23.789 s, 2 calls, 31,373 reported tokens.
- Review-context recheck: 10.850 s, 1 call, 15,705 reported tokens.
- Second repair and review: 26.073 s, 2 calls, 33,312 reported tokens.
- Total observed model work: 60.712 s, 5 calls, 80,390 reported tokens.

These durations exclude intervening host inspection/editing. Tokens are cumulative
native reports across calls, not unique context or billed cost. Native context
overhead remains substantial. This experiment used two repair attempts and
three reviews; it does not justify adding this cost to every already-simple task.
The prompts should be invoked selectively, and compact reviewer context remains
a performance follow-up.

## Implementation status and evidence

The two prompts now exist as reviewable files. `scripts/probe_task_repair.py`
runs a standalone bounded repair/review experiment and validates child count,
operation, bounds, expected outputs/checks and acyclic sibling references.
An explicit deterministic admission check verified rejection of unknown
dependencies, zero output bounds for leaves, input overflow and missing checks.

At the time of this probe, production integration remained pending. Planning
review/repair has since been integrated under shared planning limits; see
[integrated planning gate](PLANNING_REPAIR_INTEGRATION_2026-10-22.md).
Execution-result retries, dependent result invalidation and DSPy/GEPA system
prompt optimization remain pending.

Raw inputs, exact application prompts, completions and usage are retained under:
`.mimir/pizza-task-repair-20261022T214109Z/`. The first probe is `probe.json`, the
context recheck is `review-recheck-result.json`, and the accepted second repair is
`repair-attempt-2/probe.json`. Earlier rejected reviews remain available.
