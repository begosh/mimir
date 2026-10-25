# Bound citation integrity and semantic support — 2026-10-23

All gated worker policies now validate citations against engine-bound evidence
before semantic checking and dependent release. This applies to manifest inline
captures and dynamically retrieved spans, including ordinary research dependents.
Unknown/stale source IDs, conflicting versions under one ID, changed capture
type/time, invented locators/offsets and quotes outside the bound span fail the
structural gate. Full inline capture text is checked against its content hash.
Retained results repeat bound-citation validation on recovery.

Supported locator forms are the exact source locator, exact supplied source ID,
an explicit `#chars=start-end` matching its bound offsets, or a line range within
the supplied source. Dynamic spans carry engine-computed line start/end values.
A quote must occur inside its cited line range. An abbreviated source ID is an
explicit identity mapping, not a literal full-path match or a claim of entailment.
Unknown abbreviations and arbitrary fragments remain invalid.

Structural checks return REVIEW when they pass; defects retain
`check_type=structural_provenance`. They never return factual PASS. The semantic
checker separately checks field/entity association, units, ordering, conditions,
required omissions and conflicts against bound text. Its prompt rejects resolving
incompatible assertions through majority/critic agreement. Worker instructions
preserve the engine ID, capture metadata and exact supporting quote. Policy version
is `bound_material_findings_v3`; previous unchecked policy results require replan
for new publication, while existing published artifact recovery retains its policy.

## Qualification

`tests/test_source_support.py` corrupts source IDs, timestamps, types, offsets,
line references, excerpts and claim links. Each rejected parent stays outside the
blackboard, never calls the semantic checker and never releases a child. Additional
cases accept documented locator forms without returning semantic PASS, reject
conflicting versions and exclude evidence between separately bound spans.
The existing retrieval publication fixture now preserves its dependency source
instead of inventing a new source record. Focused recovery/publication tests pass.

`scripts/probe_bound_source_support.py` freezes the real `task_graph.py` word-limit
expression, supplies one isolated candidate per direct gpt-6.1-sol/low call and
does not send expected verdicts to the model. It checks every branch and condition.
The original supposed positive control said "a supplied task contract" and was
rejected because the expression requires a truthy contract; its packet remains at
`.mimir/bound-source-support-probe.json`. After correcting the positive control,
fresh checks returned PASS for all correct branches, FAIL for reversed field
association, FAIL for applying review limits to every mode and FAIL for omitted
requested branches. The corrected probe uses timestamped local packets so previous
results survive. All candidates passed structural REVIEW; semantic defects were
model judgments. These few observations are not a general accuracy estimate.

## Remaining work

P1.2 remains open for ordinary mixed-worker tool capture and independently adequate
downstream span selection. P1.3 remains open for broader conflict-retention and
omission evaluation; a prompt rule is not a demonstrated general guarantee.
Version checking uses immutable engine source IDs and packet hashes; no separate
model-authored version field is added to the finding schema. Exact identity and
quote membership do not prove a claim's meaning or detect omitted unseen evidence.
Uncaptured ordinary worker findings retain existing qualification behavior.
Automatic assembly repair is still P1.5. Model PASS is not independent verification.

Verification: full suite 356 passed, 9 skipped, 111 subtests passed (132.27s).
After the final line-range changes, 27 focused tests and 7 subtests passed, followed
by 33 gate/repair/source/locator tests. Documentation links resolve and scoped
`git diff --check` passed. Changes remain uncommitted.
