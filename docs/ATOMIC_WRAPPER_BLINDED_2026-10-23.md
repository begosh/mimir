# Operation wrappers and blinded pizza result check

Implemented a short atomic core plus operation-specific instructions in
`scripts/atomic_worker.py`. Recursive specialist prompts include only objective,
expected output, acceptance check and named inputs. Parent/depth/review metadata
remain in engine contracts, not worker text. Only retrieve/clarify receive the
original request. Ordinary single/review research prompts are unchanged.

Extraction uses supplied evidence without retrieval or general knowledge. Inline
source delivery is explicit; source IDs replace user-specific fixture paths in
the probe. Missing retrieval time is represented by an empty field and does not
by itself require a gap. Provenance type is preserved: supplied web content must
not be relabelled as a local file merely because it is inline. Calculate,
compare/check and clarify have separate instructions; retrieval retains research
provenance and discovery-versus-support rules. Native supplied-input operations
use restricted text-only dispatch, including through ResearchDispatcher.

## Revised test

Reused the same synthetic fixture and three accepted task contracts. Workers used
gpt-6.1-sol, low effort, concurrency two. The checker received shuffled anonymous
candidate IDs with no kind/origin labels, stripped worker contracts, the source,
and structured answers. The mapping is retained in host artifacts only.

The injected temperature defect was isolated by appending a unsupported 25 C
final-proof assertion to the original fermentation answer, retaining its original
steps. The missing-kneading control retained the omission. Checker instructions
require assessment against objective, expected output and acceptance check, not
additional unstated preferences.

- Mixing/kneading: PASS.
- Fermentation: PASS.
- Shaping: FAIL. The actual worker omitted explicitly unstated durations,
  temperatures and ball weights despite its expected-output requirement to report
  missing shaping details.
- Injected final-proof temperature: FAIL.
- Omitted eight-minute kneading instruction: FAIL.

This is evidence of a real result-checking need, not universal checker reliability.
The checker remains an experiment after scheduler admission; production result
acceptance/retry is not implemented by this change. Full retrieval artifact handoff
and exact routing of only named dependency inputs remain pending.

## Measurements

| Prompt | Previous characters | Revised characters | Reduction |
| --- | ---: | ---: | ---: |
| Mixing/kneading | 4,465 | 2,383 | 46.6% |
| Fermentation | 4,556 | 2,473 | 45.7% |
| Shaping | 4,539 | 2,467 | 45.6% |
| Checker | 13,444 | 11,532 | 14.2% |

Four calls took 24.577 s versus 25.698 s previously, and reported 61,754 versus
63,310 cumulative tokens. One sample per version, not a benchmark average.
Revised extraction calls still reported roughly 14,580 input tokens: shortening
the application prompt substantially improved clarity but removed little native
runtime context overhead. No billed-cost claim follows from reported token counts.

Numeric/unit containment was not added as a universal acceptance rule: conversions
and calculations can legitimately produce values absent from the source, while
an invented value could coincidentally exist elsewhere in the source. Scoped
field/value checks need operation-aware semantics rather than global containment.

Focused wrapper, scheduler, planner, engine, research and packaging checks:
75 passed, 8 existing optional-dependency skips.

Evidence and exact prompts: `.mimir/pizza-atomic-wrapper-blinded-20261023/`.
`execution.json` includes raw outputs, anonymous verdicts, host-only candidate
mapping, source and usage. The earlier prompts/results packet is retained unchanged.
