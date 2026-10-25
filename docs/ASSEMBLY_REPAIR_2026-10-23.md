# One targeted assembly correction — 2026-10-23

Review/swarm assembly permits one correction after a valid final FAIL, followed
by the same final checker. Single retains one worker and its admission check.
Malformed checker output, worker/schema errors and oversized initial assembly do
not trigger correction. A second FAIL blocks report, sidecar and learning publication.

Correction uses the original context, rejected answer and specific feedback at
unchanged model/effort, objective, sources, checker policy and answer limits.
It makes two additional model calls: correction and recheck. Existing configured
cumulative attempt/deadline/token limits still apply; limits are never increased.
Default whole-run budgeting remains P2.4.

Assembly history persists input/policy binding, integrity hash, stage, original
and corrected versions, verdicts and a pre-call single-correction reservation.
Completed boundaries can resume. An interrupted in-flight operation or exhausted
correction cannot restart synthesis to reset its allowance. Changed inputs or
policy require replan. Published artifact recovery makes no new model calls.
Invalid/oversized correction output is retained. The readable report publishes
only the accepted corrected answer; checkpoint and sidecar retain rejected history.

Worker findings and evidence are immutable. An unsupported appendix assertion
cannot be erased by assembly correction and still blocks publication. Fixing its
underlying worker result is separate work. Model PASS is not factual verification.

## Verification

Tests cover identical recheck context, durable reservation, retained versions,
malformed verdicts, invalid/oversized correction retention, cancellation, budget
exhaustion, history tampering, engine publication and recovery without model calls.
Existing stale-appendix and final-gate tests still reject publication on failure.

A fresh gpt-6.1-sol/low direct probe used the real review-limit code expression:
the checker rejected swapped 250/180 associations, targeted correction restored
critique 180 and other tasks 250, and unchanged checking returned PASS. Three
calls, no tools or effort increase. Optional packet:
`.mimir/assembly-repair-live-probe.json`. This is one observed correction,
not a general reliability estimate.

Verification: final full suite 367 passed, 9 skipped, 111 subtests passed
(111.27s). The 11 assembly tests, including completed-rejection resume and changed
policy checks added during verification, passed separately. Updated links resolve
and scoped `git diff --check` passed. Changes are uncommitted.
