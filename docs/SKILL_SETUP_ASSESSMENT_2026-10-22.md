# Mímir skill and operating setup assessment — 2026-10-22

Mímir has a useful shared execution core and is fit for supervised, bounded research and architecture reviews. The present setup is not demonstrably optimal. The next work should repair operating/recovery defects, simplify the default workflow and establish evidence-quality evaluations before expanding orchestration.

This note reconciles the actual Mímir review with independent host checks. No implementation or saved provider configuration was changed. Review artifacts were created; the engine automatically appended a candidate takeaway to the repository LEARNINGS.md. That automatic append is itself a finding for read-only operation.

## Current setup

- Harness skill discovery points to the installed package at `C:/Users/g740274/.agents/skills/mimir`.
- Project MCP configuration launches repository `scripts/mcp_server.py` with repository `.venv`, an explicit workspace and run root.
- MCP and terminal entrypoints call the same `engine.run_mimir`; this is one research engine with two frontends.
- Workers use Codex/Claude SDKs, owned OpenCode HTTP runtime or authenticated AGY CLI. Native worker configuration supplies credentials and tools; the calling host's tools are not lent to workers.
- Planning, graph execution and synthesis remain three host-controlled invocations. Planning requests 4–6 workers including an executive synthesizer; final synthesis makes another reflective model call.
- Agreed workers for this assessment: native Codex SDK, `gpt-6.1-sol`, low effort, existing direct Azure provider. No saved project worker profile exists.

## What happened during this assessment

The connected MCP run `2caa3fc33a694be292b6488e382ce3c8` failed during planning after 51.211 seconds. Its terminal event was the generic `Mimir worker failed: no usable result; check the CLI or provider configuration.` No completed report was obtained from that run.

A credential-presence check, without displaying its value, established that `AZURE_OPENAI_API_KEY` existed in Windows User and Machine environment scopes but was absent from this session's child-process environment. The global native configuration still selected the expected direct Azure endpoint. This establishes an operating prerequisite; it does not imply every possible cause inside the failed MCP process was exposed by its generic diagnostic.

After diagnosing that failure, terminal invocation loaded the existing User-scope credential into the command's process environment only. Provider, transport, model and effort remained unchanged. All three phases succeeded:

| Phase | Recorded duration | Result |
|---|---:|---|
| Planning | 48.62s | Four independent reviewers plus an executive synthesizer |
| Execution | 197.43s | 5/5 tasks successful |
| Reflective synthesis | About 70.96s | Markdown and JSON published; successful process exit |

Total recorded engine time was **317.011s**, excluding initial failed probes, host polling gaps and some lifecycle overhead. The successful workflow made seven model invocations: decomposition, five graph workers and final reflection. No JEV model calls were made: every task was protected or exempt and received automatic `1.0`. The planner produced five tasks despite the objective requesting at most four and no executive worker. Its defaults are prompt requirements, rather than enforced task-budget guarantees.

The executive worker alone took 80.259s after the four specialists finished. This measures the added serial stage in this run; it does not prove removing it would preserve answer quality. Actual billed cost and complete run token usage were not recorded.

Full generated artifacts:

- [Mímir report](../artifacts/2026-10-22-optimal-setup-report.md)
- [JSON sidecar](../artifacts/2026-10-22-optimal-setup-report.json)
- [Phase checkpoint](../artifacts/2026-10-22-optimal-setup-state.json)

The generated report's statements about no tests/model calls describe individual worker activity, not the hosting assessment. Its cross-harness table reflects the evidence provided before this run. This note adds the successful full native Codex terminal workflow and host reproductions below. The full authenticated three-phase MCP workflow was not established today.

## Prioritized improvements

### 1. Make failure and recovery dependable

Confirmed with a temporary local fixture: after synthesized checkpoint publication, a cleanup failure leaves managed status `failed`. MCP correctly rejects a final successful result, but also rejects synthesis retry because admission requires an `executed` checkpoint. Withholding success is correct; the missing recovery route is the defect.

The same code boundary permits process-death interruption after publication. The engine accepts synthesized state, while the manager rejects it. See `scripts/run_manager.py:145`, `scripts/run_manager.py:254` and `scripts/engine.py:298`.

Separately, successful graph outputs are checkpointed only after the whole graph succeeds. An incomplete graph raises first, so retry repeats successful work. See `scripts/engine.py:491` and `scripts/engine.py:508`.

Error information is also lost at the engine boundary. A local reproduction passed an already sanitized missing-environment-variable diagnostic through `worker_diagnostic("Mimir", error=RuntimeError(message))`; it became the generic no-result message. The engine calls that helper without the exception diagnostic text (`scripts/engine.py:830`). Use typed, sanitized failures through adapter, engine and MCP; avoid exposing provider response bodies.

Success criteria: a missing credential is named without revealing its value; late cleanup failures have an explicit safe recovery route; completed task artifacts survive failures with input identity checked before reuse; no premature success or duplicate learning/publication.

### 2. Simplify the skill and execution policy

The installed skill is 213 lines and includes extensive terminal instructions alongside MCP instructions. The compatibility reference adds another 219 lines. CLI terminology and legacy support observations remain mixed with native behavior.

Keep the entry skill focused on selection, agreed worker settings, invocation, evidence constraints, progress and failure handling. Move terminal/legacy procedures to references. Consolidate one dated support matrix.

Offer one-worker execution for focused questions and selective specialists for genuinely separable reviews, through the same engine. Remove the mandatory executive worker before final synthesis. Make critic dependencies and maximum task/call counts explicit. Separate task count from concurrency. Preserve the mythic voice as presentation, without making it an operating rule that obscures facts.

JEV currently exempts root, critic, synthesis and required-evidence tasks (`scripts/task_graph.py:248`). Show exempt/protected status instead of implying automatic `1.0` is a comparative model estimate. Keep pruning optional until it demonstrates net benefit.

Success criteria: a requested task budget is enforced; one final synthesis; simple questions avoid mandatory multi-worker decomposition; required evidence survives pruning.

### 3. Improve evidence quality beyond output identity

The current contract identifies worker text through `node://` and a hash. This is useful provenance, but it does not establish claim support, retrieval completeness or factual verification. Execution can finish while workers report missing evidence. See `scripts/task_graph.py:38`, `scripts/backend.py:420` and `scripts/engine.py:642`.

Add structured source locators, retrieval time/type, support excerpts, claim links, contradictions and required-evidence gaps. Separate execution status, research coverage and independent validation. Continue labeling public snippets and preprint abstracts as discovery material. A successful read or plausible citation is not an entailment check.

Success criteria: missing retrieval and conflicting evidence remain visible in the final answer and JSON; unsupported material claims cannot receive verified labels; evaluations score source-to-claim support rather than hashes or model agreement.

### 4. Unify operating identity and make learning explicit

Independent byte comparisons found the sampled installed skill/runtime files matched the repository, but the two `LEARNINGS.md` files differed. Default learning location follows the executing code root (`scripts/jarvis_memory.py:26`). Today's terminal synthesis explicitly appended to repository LEARNINGS.md; installed-code execution would select the installed bank. This confirms two differing banks, not a proven history of every harness reading both.

Move writable state outside the executable package. Configure memory location and scope explicitly, support memory-off/read-only operation, and keep candidate takeaways separate from promoted guidance with source references and supersession. One configured store may be project-scoped; sharing every project's conclusions globally is not automatically desirable.

Expose read-only diagnostics for installed/runtime revision, interpreter/dependencies, workspace, run root, learning path, selected provider/model, credential presence and permitted required tools. Resolve environment inheritance when launching the host/MCP; do not copy keys into project files. `--workspace` should also determine default run storage consistently when no run root is supplied.

Claude/OpenCode currently deny arbitrary MCP tools outside their approved query catalogs even if native configuration permits them. Codex filesystem read-only mode does not restrict remote MCP writes. Document actual permitted retrieval operations and gaps per worker.

Success criteria: the discovered skill describes the executing runtime; storage paths are explicit; read-only review creates no learning records; missing credentials/tools are diagnosed before lengthy planning.

### 5. Measure and then tune

Compare the same questions under one worker, selective specialists and the present workflow. Keep model, source snapshots, evidence access and total budgets consistent. Count planning, pruning, retries and synthesis in cost. Use known architecture defects, inaccessible/stale sources and conflicting-evidence cases; score anonymized answers for citation entailment, unsupported claims, defect detection, omissions and human review effort.

Persist complete usage counters. The Codex adapter obtains a usage value, but graph results/report do not retain it. Full dependency and synthesis text also have no explicit token-budget admission policy. Keep complete evidence artifacts and select context with source references and gap accounting, rather than silently truncating evidence.

Only then tune tier barriers, repeated runtime startup and duplicated context. A dependency-ready scheduler can avoid waiting on unrelated siblings. Keep scheduling behind one interface separate from runtime adapters when implementing that change; preserve isolation, failure propagation and joined cleanup.

Do not add more mandatory agents, recursive swarms, routine genetic optimization, vector memory, transports or distributed coordination yet. Single-reflection synthesis is not dataset-scored GEPA/Pareto optimization.

## Verification boundary

- Today: all three terminal phases succeeded using native Codex SDK/direct Azure; report and sidecar read; error-detail loss and late-synthesis recovery rejection reproduced locally; installed/repository learning divergence confirmed.
- Previously recorded: 178 passed, one POSIX-only skipped, 85 subtests passed. The suite was not rerun for this assessment, and mechanical tests do not establish research quality.
- Claude: last live provider response was HTTP 401; full authenticated research remains unverified.
- OpenCode: native configuration discovery timed out; owned server/session/cleanup lifecycle passed without inference. Full authenticated research remains unverified.
- AGY: historical one-call CLI success; complete managed research remains unqualified.

The official [Codex SDK documentation](https://developers.openai.com/codex/sdk) was fetched during diagnosis. It confirms the Python SDK's local app-server architecture and pinned runtime; it does not establish this user's credential availability or Mímir's research quality.
