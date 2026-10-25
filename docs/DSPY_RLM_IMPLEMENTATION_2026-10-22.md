# DSPy/RLM implementation qualification — 2026-10-22

> Historical development snapshot. Local run/capture artifacts were cleared
> during workspace cleanup; use current setup docs and tests to reproduce behavior.

The approved design is implemented as optional investigator programs at Mimir's
scheduler seam. Standard research remains the default. The Python engine retains
planning, dependency scheduling, critic/synthesis, durable source/claim/gap records,
learning rules and cleanup-complete publication.

Implemented components:

- Normalized synchronous/asynchronous DSPy engines over the parent-owned native
  Codex SDK, preserving the existing provider, credentials, model and effort.
- Private IPC and owned DSPy/Deno processes, with denied guest host access,
  guarded nested Predict/RLM, shared interpreter leases and authoritative failures.
- One durable native attempt journal with parent/depth, input/output identity,
  reported usage, review reservations, crash accounting and persisted deadlines.
- Explicit local/allowlisted HTTPS source capture, narrow source queries, matching
  capture/excerpt checks and frozen instruction/runtime/source identities.
- Separate upstream GEPA typed/RLM instruction training, disjoint dataset splits,
  sealed comparison, data-only candidates and explicit reviewed activation/rollback.
- CLI/MCP controls, optional dependency diagnostics, installation support and
  updated skill instructions. Setup and operational limits are in [DSPY_RLM.md](DSPY_RLM.md).

## Evidence

Live tests used native Codex `gpt-6.1-sol`, low effort, on the existing native
credential/provider route. No provider/config/login changes were made.

Typed DSPy produced the correct Blue deployment port and owner with source records.
RLM processed a captured corpus larger than the 120000-character prompt limit.
The nested native run explicitly constructed a child RLM with its own interpreter;
its successful trace contains native calls at depths 0 and 1. An earlier rejected
policy run remains in the attempt history; it was not represented as success.

The real stdio MCP review `0b75504ba79f40b8aeb30d2deef27651` completed planning,
two RLM specialists, native critic and native synthesis, with bounded report and
sidecar retrieval. It reports port 8443 / owner Operations as a source assertion,
retaining missing live configuration, ownership precision and corroboration gaps.
Its critic identified a raw-byte versus normalized-text hash difference; the
capture digest semantics are now documented explicitly.

The synthetic dataset contains 12 train, 6 development and 6 held-out cases with
disjoint source/topic groups. The first native comparison measured:

| Investigator | Correct held-out cases | Native attempts | Seconds |
| --- | --- | --- | --- |
| Standard native | 5/6 | 6 | 69.13 |
| Typed DSPy | 6/6 | 6 | 25.42 |
| RLM | 6/6 | 14 | 87.62 |
| GEPA-selected RLM instructions | 6/6 | 12 | 71.69 |

The first selected candidate equals the original instructions; timing differences
are run variation, not proof of optimization. Later native GEPA jobs generated
changed typed and RLM-action instruction proposals but retained the original
after scoring. Proposal records and required-call accounting are preserved.
The final RLM job recorded two proposals (10 metric calls); its selected
instructions also remained unchanged. Unexecuted extraction components can lack
reflective examples; GEPA records that limitation instead of inventing a trace.
The default JSON proposer was replaced with upstream `InstructionProposer` using
the qualified ChatAdapter because native generation overrides are rejected.

These results demonstrate execution mechanisms and synthetic correctness. They
do not establish statistical quality gains, general speedups or human citation
entailment. No candidate was automatically activated.

Artifacts under `artifacts/dspy-rlm-qualification/` include checkpoints, operation
journals, interpreter traces, dependency lock, native comparisons, source capture,
MCP results and test/install logs. They contain local research data and are not
automatically staged or published. The captured PyPI release metadata succeeded;
the raw GitHub source GET returned HTTP 403 and was retained as a failed retrieval.

## Delivery and limits

The optional environment is isolated in `.venv-research`; normal `.venv` remains
available. The installed shared skill matches the checkout, including nested
runtime files and optional requirements; installed learning notes match their
pre-refresh backup. Reconnect existing MCP sessions to load the new controls.

Acceptance: 248 tests and 112 subtests passed; one POSIX-only test skipped.
Compilation, whitespace checks, dependency consistency and UTF-8 skill validation
passed. The final sealed candidate check scored 6/6 in 14 native attempts (83.60s).

Qualified DSPy/RLM transport is native Codex SDK on Windows. Normal research
continues to support its other adapters. Deno startup can require downloads;
POSIX process groups exist but equivalent memory qualification is outstanding.
Initialization is capped at 4 MB, source records at 20 MB individually, and read
spans at 16000 characters. Arbitrary guest retrieval and Work IQ bridging are
not exposed; use approved capture or the native research program.

Native capabilities are disabled per process and observed tool items fail the
completion; basic utility tools may remain advertised by the model catalog.
Iteration exhaustion, denied policy, required subcall failures and cancellation
cannot publish success. Resume restarts interpreter computation from frozen
sources and charges repeated work; no interpreter-memory replay is claimed.
Reported usage covers native turns and can overshoot a token threshold; no billed
cost or token-breakdown claim is made. Human review remains required before
activating a candidate for operational research.
