# Development update: direct text workers, 2026-10-23

Current increment: [shared material-finding admission](MATERIAL_FINDING_GATE_2026-10-23.md) adds ordinary worker checks, checked single publication and final appendix checking. Older measurements below describe their dated implementations.

[Durable whole-run budgets](RUN_BUDGET_2026-10-23.md) now apply by default to
ordinary runs as well as DSPy/RLM. Planning, execution and publication share fixed
attempt limits and an elapsed deadline, with journaled publication reservations
that survive interruption and resume.

Direct API calls now execute text-only work by default. Native runtimes are lazy
tool executors. The same six-task fixture used 91.2% fewer reported tokens through
direct requests. Planning simplification and OpenCode tool readiness remain open.
See [execution conclusions](EXECUTION_CONCLUSIONS_2026-10-23.md) for measured
results, errors, scope and delivery validation.

The notes below describe earlier implementation snapshots and qualification.
Their all-native execution statements do not describe the current default.

# Development update: work in progress, very BETA

This update consolidates the engine, native worker integrations, evidence and
recovery hardening, and optional DSPy/RLM/GEPA implementation.
These are experimental mechanisms with bounded qualification, not a
production release or a claim of general research superiority. Changes to APIs,
checkpoint formats, dependencies and host instructions should be expected.

## Engine and invocation

- `scripts/mimir.py` remains a compatibility entrypoint; `cli.py` and `engine.py`
  implement shared invocation and execution policy.
- `single` uses one investigator. Default `review` uses two specialists followed
  by a dependent critic and one synthesis. `swarm` permits bounded custom planning.
  Task caps and concurrency are separate; JEV is optional and off by default.
- `run_manager.py`, `run_locks.py` and `mcp_server.py` expose asynchronous plan,
  execute and synthesize phases on the same run ID, cancellation, diagnostics,
  bounded status/results and recoverable phases. Queued work is not completion.
- `scheduler.py` dispatches dependency-ready work rather than waiting for whole
  graph tiers. Successful task artifacts are persisted before dependent admission.
  Recovery validates inputs, dependency identities and raw/parsed output identities.
- Publication records report/sidecar identity and can recover a completed synthesis
  without repeating model or learning calls. Final success follows owned cleanup;
  it does not certify cleanup from an earlier lost process.

## Native workers and installation

- Codex uses its pinned Python SDK with fresh ephemeral threads. Claude uses its
  Agent SDK. OpenCode uses an owned localhost HTTP runtime. AGY retains its
  authenticated CLI route; explicitly selected legacy CLI/direct HTTP paths remain.
- Provider, model, effort and existing credentials stay on the selected native
  route. There is no silent provider/model fallback. Diagnostics distinguish static
  credential/dependency presence from successful authentication or retrieval.
- Claude/OpenCode query catalogs are restricted. Codex filesystem read-only mode
  does not establish denial of remote MCP writes; permissions still need to match
  the objective. Host tools are not automatically available to workers.
- The installer stages a shared skill package, preserves existing notes/backups,
  validates links and targets, and handles temporary Windows replacement failures.
  Native worker requirements and optional research requirements are separate files.
  Skill installation does not install a virtual environment or configure host MCP.

## Evidence, learning and observable progress

- Worker interfaces retain readable answers, source locators, actual retrieval
  metadata, supporting excerpts, linked claims and explicit gaps. Search snippets,
  abstracts and worker reports are discovery evidence, not primary corroboration.
- Record coverage, output identity, excerpt membership and citation entailment are
  different checks. A hash or critic does not establish factual truth or completeness.
- Project learning defaults to read-only curated guidance. Explicit write mode
  appends unvalidated candidates separately; installation, ordinary research and
  optimization do not automatically promote them into guidance.
- `progress.py` turns observed stage events into concise narration and supports
  cursor paging and meaningful waits. Heartbeats remain liveness rather than
  findings. Raw journal events are available separately for diagnostics.
- Usage distinguishes adapter invocations from provider requests, known tokens
  from unavailable usage, and measured duration from unsupported billed-cost claims.

## Optional DSPy, RLM and upstream GEPA

- Typed DSPy prediction runs over an explicitly captured corpus through a
  normalized native Codex engine bridge. The provider/login route stays in the
  parent; child interpreter processes do not receive credential environments.
- RLM runs generated analysis in guarded Deno/Pyodide. Source access uses narrow
  metadata/search/span callbacks. Guest host files, environment, arbitrary network
  and process execution are denied. Nested Predict/RLM calls receive fixed policy.
- `invocation_broker.py` tracks attempts, parent/depth, deadlines, input/output
  identity and reported usage. Review reserves critique/synthesis calls. Interpreter
  leases and process ownership bound optional research execution.
- Source capture supports explicit local files and allowlisted HTTPS GETs. Evidence,
  instructions and implementation identities freeze at planning. Recovery rejects
  changed local sources and restarts interpreter computation rather than replaying
  interpreter memory. Failed or interrupted calls remain accounted for.
- Upstream `dspy.GEPA` runs only in a separately requested training job. It changes
  investigator/action/extraction instructions, not runtime code, tools or budgets.
  Training/dev and held-out comparisons remain separate. Data-only candidates need
  evaluation and explicit reviewed selection in a new run; omission rolls back.
- Synthetic fixtures cover revisions, conflicts, missing facts, distractors,
  injection and scattered records. Exact-answer metrics demonstrate fixture
  behavior, not research quality. Qualified proposals did not establish a better
  instruction set; selecting unchanged instructions is not an optimization gain.

[Operation](DSPY_RLM.md), [design](DSPY_RLM_DESIGN_2026-10-22.md) and
[dated qualification](DSPY_RLM_IMPLEMENTATION_2026-10-22.md) contain setup,
budgets, implementation references and practical limits.

## Verification and limits

Focused regression tests cover scheduling, failures, cancellation, locks,
publication recovery, source qualification, memory modes, installer behavior,
native transport seams, actual MCP stdio protocol, progress and optional research
policy. Tests with fake native completions exercise mechanisms without reusing
production credentials for inference. Optional dependency tests need the research
environment; a skipped test is not qualification.

Dated live qualification used the existing native Codex/Azure route on Windows
for native single/review, typed DSPy, large-corpus RLM, nested RLM and explicit
GEPA proposal jobs. Other provider/harness routes have narrower qualification or
authentication/setup gaps. POSIX process groups exist but equivalent memory-limit
qualification is outstanding. Deno startup can require runtime downloads.

Mímir itself is not universally sealed: ordinary native evaluation with read-only
workspace access is different from the restricted DSPy/RLM text-only path.
Captured membership checks do not establish a claimed line suffix's correctness,
semantic source-family separation, citation entailment or live-system truth.

The standard regression command is `python -m pytest -q` in the worker environment.
Run optional research tests in the separately prepared research environment.

Checks repeated for this Git delivery on 2026-10-22:

| Check | Measured result |
| --- | --- |
| Worker environment: full `pytest -q` suite | 240 passed, 9 skipped; 112 subtests passed |
| Research environment: `test_research_program.py` and `test_research_policy.py` | 27 passed; 14 subtests passed |

These checks use fixtures for native transport behavior and do not establish live
authentication, provider availability, independent source verification or better
research answers. The optional suite supplies qualification for the DSPy-related
tests skipped in the worker environment; platform-specific skips remain explicit.

Before consequential use, inspect underlying evidence and test the target harness,
permissions, recovery and representative questions. No general speed, cost or
quality improvement is claimed.

Machine-local configs and environments stay local. Completed development runs,
raw source captures, generated archives/decks and test caches were removed during
workspace cleanup. The Mycroft and presentation experiments were also removed.
Dated qualification records describe earlier snapshots; their local artifacts
are no longer retained. The checked-in tests and fixture generators are the
reproducible starting point.
