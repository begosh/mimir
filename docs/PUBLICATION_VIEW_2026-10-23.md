# Quarantined publication view — 2026-10-23

Publication now has an explicit task-status view separate from immutable original
worker results. Accepted entries publish the accepted task result. A disputed
task can be quarantined during the existing single assembly correction, with a
specific source-backed reason matching final-check feedback. Original results,
hashes and evidence remain unchanged for diagnostics and recovery.

The repair schema names existing task IDs and reasons. Unknown/duplicate IDs and
empty reasons fail structural validation. Whole-task quarantine is deliberately
conservative: assertions are withheld, while sources and gaps stay in the readable
appendix. Required supported facts, conflicts and material gaps must remain in
the answer or limitations. The final checker assesses the exact status view with
the original evidence and corrected answer. It rejects unjustified quarantine,
hidden disagreements, missing requirements or promotion of quarantined claims.
There is still at most one correction and recheck under unchanged run limits.

The readable report shows quarantine status/reason and original sources/gaps,
instead of the quarantined assertion body. The research claim aggregate excludes
quarantined task assertions and retains gaps and quarantine reasons. The sidecar
retains original task_results explicitly labelled diagnostic records, plus the
publication_view and assembly history; originals are not silently overwritten.
Critic text in assembly notes uses the same publication view. Single retains its
accepted worker/check path without additional model calls or quarantine repair.

## Verification

Tests verify original/source/gap preservation, invalid quarantine references,
final approval before publication, final rejection when quarantine hides a conflict,
accepted corrected report, exclusion from released research claims, diagnostic
sidecar originals and recovery without new calls. Existing assembly allowance,
budget/interruption and final-failure gates remain in effect.

A fresh gpt-6.1-sol/low probe froze the actual review word-limit code expression.
The initial final check rejected a correct summary with a reversed appendix finding.
One repair named that task for quarantine, retained the correct 180/250 values
and unassessed-settings gap, and explicitly described the original contradiction.
Rechecking returned PASS. Optional packet: `.mimir/publication-quarantine-probe.json`.
This is observed model behavior on one case, not independent factual verification
or a general conflict-retention guarantee.

The quarantine unit is a whole task, not individual claim revisions. Consumers of
the sidecar must use publication_view for released status; original task_results
are archival assertions. P1.3 broader conflict/omission evaluation and P1.2 mixed
tool capture remain open. Policy version is publication_assembly_v2.

Verification: final full suite 372 passed, 9 skipped, 111 subtests passed
(135.11s). Two focused publication/assembly/gate runs passed 25 tests each.
Updated documentation links and scoped `git diff --check` pass. Changes remain
uncommitted.
