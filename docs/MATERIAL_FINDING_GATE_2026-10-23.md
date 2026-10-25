# Shared material-finding admission — 2026-10-23

Ordinary single/review/nonrecursive swarm workers now use the existing structured
`answer/sources/claims/gaps` schema and a persisted assignment contract. No new
planner or synthesis worker is added. Atomic workers retain their bounded contracts.

The scheduler checks ordinary record structure and source links deterministically,
then checks answer, claims and gaps against the assigned evidence using the existing
text-only result checker. Structural acceptance returns REVIEW, never factual PASS.
Qualified inference and conflicts are not structurally rejected. Missing/duplicate
source identities and unknown claim links fail the structural gate. These identities
are local worker records; engine-owned source/version/span verification is P1.2/P1.3.

Only an accepted identity-bound version is checkpointed and released to dependents.
Valid rejection uses the existing two-retry repair limit, original assignment,
model/effort and configured budgets. Ordinary repair retains the original prompt
and appends targeted correction instructions. Malformed checker output fails closed.
Older unchecked ordinary results cannot be consumed for new publication; replan.
Already published artifacts retain the existing identity-checked recovery behavior.

Single publishes the exact accepted answer and preserves its gaps in assembly notes;
it reuses the admission check and performs no synthesis or duplicate final call.
Review/swarm retain final checking, now explicitly including all task-result appendix
assertions. A corrected summary cannot excuse a stale conflicting appendix claim.
Such publication fails closed; targeted assembly correction is still P1.5.
Rejected attempts remain quarantined in checkpoints. The readable appendix contains
the accepted version, a model-check qualification and rejected-attempt count.

## Verification

`tests/test_material_finding_gate.py` uses the actual review word-limit expression
in `scripts/task_graph.py`: critic 180 words, specialists 250 words. Both numbers
exist in the span, so token membership alone cannot detect reversal. Parameterized
single/review tests verify rejection, blocked dependent release, checked repair,
accepted-only readable publication and retained rejected attempts. A further test
simulates an admission miss and a correct assembled answer; final FAIL prevents
publication and learning when the appendix remains wrong. Structural tests keep
unknown source references separate from semantic verdicts.

A fresh direct gpt-6.1-sol/low probe made four independent checker calls using the
same real span. Admission rejected the reversed association and accepted the correct
one. Final checking rejected the wrong appendix despite a correct summary, and
accepted the supported appendix. Candidate prompts supplied no expected verdict.
Local optional packet: `.mimir/material-gate-live-check.json`.

This small probe establishes those observed model verdicts, not general accuracy or
independent factual verification. Frozen dynamic retrieval, semantic source support,
intent completeness, whole-run default budgets and assembly repair remain separate
backlog work. This regression does not yet recreate E1's omitted checkpoint guard.

Final full-suite verification: 333 tests and 111 subtests passed; 9 explicit skips.
Duration: 106.93 seconds. Updated documentation links resolve and git diff --check
reported no whitespace errors. These engineering checks do not establish general
live-model accuracy. Changes remain uncommitted.
