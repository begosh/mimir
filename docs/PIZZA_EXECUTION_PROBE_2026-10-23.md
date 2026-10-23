# Pizza worker execution and result-check probe

Executed three accepted preparation leaves from the saved integrated pizza plan
against `tests/fixtures/pizza_extraction_source.txt`. This is an explicitly
synthetic test fixture, not an authentic or recommended recipe. It supplies
mixing/kneading, bulk fermentation, proof and shaping instructions, with deliberate
missing temperatures and durations. No web search or recipe retrieval ran.

Used production TaskGraph, scheduler, blackboard, compact worker-result schema
and native Codex SDK with gpt-6.1-sol / low. Concurrency was two; each worker used
text-only dispatch. The source prerequisite was replaced by the full supplied
fixture in each prompt; this tests direct source input, not production retrieval
artifact handoff. Each prompt was checked to contain the complete fixture,
including its final missing-detail line.

## Actual worker answers

Mixing/kneading:

> 1. Dissolve yeast in water.
> 2. Add flour and salt; mix for 2 minutes.
> 3. Knead for 8 minutes.
> Dissolving duration and mixing/kneading temperatures are not stated (L03–L04).

Fermentation:

> Before ball shaping: cover and bulk-ferment for 18 hours at 20°C. After ball
> shaping, before stretching: proof covered balls for 4 hours; final-proof
> temperature is unstated. Both fermentation durations are stated. Source:
> supplied synthetic fixture, lines L05–L08.

Shaping:

> After bulk fermentation, divide into four equal portions; shape each into a
> ball (L06). After final proof, hand-stretch each ball into a round; no rolling
> pin (L08). Ball weights, shaping durations, and temperatures are unstated.

All answers stayed within their existing contract word bounds, preserved the
assigned source instructions and stated missing details rather than inventing
values. A separate low-effort result checker received the original fixture,
task contracts and actual structured answers. It returned PASS for all three.

## Negative controls

Also supplied two deliberately corrupted answers, preserving the original source
records so correct quotations could not excuse wrong readable answers:

- Invented final-proof temperature of 25 C: FAIL. The checker identified the
  unsupported temperature and omitted covering/sequence details.
- Removed the eight-minute kneading step: FAIL. The checker identified the
  missing kneading instruction and missing explicit detail qualifications.

These demonstrate detection on two known errors, not general factual correctness
or calibrated reviewer reliability. The model may report additional issues beyond
the intentionally injected defect. No recipe authenticity was assessed.

## Measurements and remaining scope

Three workers plus one batched checker: 4 native model calls, 25.698 seconds,
63,310 cumulative reported tokens. Existing native context contributes substantial
input overhead; these totals are not unique context or billed cost.

This is a standalone execution/check experiment. Scheduler currently admits
well-formed worker results before the experimental checker runs. The checker is
not yet an enforced acceptance gate before downstream scheduling, and no failed
result repair/retry loop was added. Production retrieved-page handoff remains
unverified. Ordinary worker/model settings were unchanged.

Evidence: `.mimir/pizza-execution-probe-20261022/execution.json`, including full
source, contracts, structured results, checker verdicts and usage. Exact worker
prompts and checker prompt are retained alongside it. Reproduce with
`scripts/probe_pizza_execution.py <new-artifact-directory>`.
