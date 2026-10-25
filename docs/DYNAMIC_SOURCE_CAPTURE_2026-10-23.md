# Dynamic retrieve-task evidence — 2026-10-23

Explicit `retrieve` tasks now cause an engine-owned source read before result
checking or dependent admission. A worker-reported excerpt never creates a capture.
The engine rereads named workspace files or HTTPS pages on the source manifest's
explicit `allowed_domains` list. Redirects, credentials in URLs, unsupported
protocols, out-of-workspace local paths and sources above 20 MB are rejected.
At most two references are captured per retrieve result. Remote reads time out
after 15 seconds; cancellation joins the owned capture reader before cleanup.

Capture IDs derive from canonical locator plus content SHA256. Capture timestamps
come from the engine in UTC. The full decoded text and its hash are checkpointed;
worker source IDs, types and timestamps are replaced with the engine record, and
claim links are rebound. These records identify the engine's reread, not the
earlier tool read; a changed page or nonexact excerpt fails capture.

Each unique, nonempty exact supporting excerpt produces character start/end
offsets into the full snapshot, bounded to 16000 characters. Ambiguous repeated
excerpts fail instead of choosing a location silently. The checker receives those
exact spans. Once the result passes, dependents receive bounded frozen spans with
full-source hashes and offsets. Full capture lineage survives intermediate workers.
Captures and bindings persist before subsequent model calls, and accepted packets
persist before dependent release. Interrupted checking/repair reuses its saved
source read. Recovery validates packet, content, offsets, generated ID, timestamps
and lineage. Publication retains the full packet in the sidecar and source spans
in synthesis/final-check evidence.

## Verification and limits

Tests use the real review-limit expression in `scripts/task_graph.py`, verify
accepted/rejected release, multiple dependent hops, engine metadata, exact excerpts,
capture drift, packet tampering, offset corruption, domain/workspace boundaries,
owned-reader cancellation, checkpoint/sidecar preservation and publication recovery.
Approved HTTPS transport is tested with a controlled response; live web capture
and HTML extraction are not qualified here.

P1.2 remains open: ordinary mixed research workers are not automatically captured.
The current adapter protocols do not reliably expose which original page bytes
were read. This increment covers explicit retrieve-task references using an engine
reread. HTML pages whose worker-visible rendered text differs from raw captured
HTML fail exact matching rather than becoming an invented snapshot. Selective
spans are the retrieve task's exact cited excerpts, not a demonstrated independent
completeness assessment for each downstream assignment. Native tool credentials
are not copied into the capture reader; authenticated private HTTP retrieval is
not supplied by this mechanism. Missing capture/excerpt fails closed without
silently widening permissions or source limits.

Structural capture checks prove identity and exact membership. They do not prove
semantic support, association, missing conditions or completeness; P1.3 remains
open and model PASS remains a model assessment. Default whole-run budgets are P2.4.

Verification: full suite 340 passed, 9 skipped, 111 subtests passed (118.16s).
After the final small publication/extraction/validation changes, 23 focused tests
and 7 subtests passed, including the two added HTTPS/cancellation cases. All 17
research-program tests also passed in `.venv-research` (40.38s). No live web capture
or broad model-quality claim follows from these tests. Changes are uncommitted.
