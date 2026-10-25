# Worker transports and local MCP

Mímir has one engine in `scripts/engine.py`. The terminal adapter and local MCP
adapter call its `run_mimir` interface. The engine owns the graph, evidence,
checkpoints, reflection and report publication. Worker implementations remain
behind `BaseSwarmBackend.spawn`; neither host adapter duplicates orchestration.

## Installation

Use Python 3.10+ and install the verified dependencies into the interpreter that
will launch the server:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-workers.txt
.\.venv\Scripts\python.exe scripts/mimir.py --check --backend codex --model gpt-6.1-sol --effort low
```

`python scripts/install.py` installs native worker dependencies and refreshes
the shared skill while retaining learned notes and backups. The installer does
not register MCP in host configuration. A copied skill still uses the configured
absolute Python interpreter; no virtual environment is copied into the package.

New runs selecting a tool runtime default to `worker_transport="hybrid"`: Python
sends text-only operations directly to the Responses API and initializes the
selected native runtime only for tool-using work. Azure uses the configured
AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY; OpenAI uses OPENAI_BASE_URL and
OPENAI_API_KEY. MIMIR_TEXT_API_PROVIDER can explicitly choose azure or openai.
Credentials never enter prompts or checkpoints. Configured certificates remain
enforced. `backend="responses"` uses direct requests with no tool runtime.

The selected model must be an API model/deployment ID. Native model aliases are
not translated. Codex/gpt-6.1-sol/low is tested live; other tool-runtime/model
combinations require access on both routes. Missing API credentials stop the run
instead of silently falling back to a more expensive runtime. Text-only work
does not require an installed tool runtime; tool prerequisites are checked when
tool work begins. Native implementations for tool work remain:

OpenCode's tool identifier adds the configured provider namespace to the selected
API model (for example azure/gpt-6.1-sol). MIMIR_TOOL_MODEL can supply an explicit
namespace; its model component must match the selected API model. No different
model or effort is substituted.

| Worker | Native implementation | Authentication and tools |
| --- | --- | --- |
| Codex | Python SDK 0.163.0, pinned app-server runtime | Native Codex configuration; ephemeral read-only threads |
| Claude | Agent SDK 0.2.172, bundled runtime | Native settings/MCP; fresh nonpersistent query; query-only hook |
| OpenCode | Private local HTTP server using 1.19.3 routes | Native provider config; copied reusable auth; owned disposable sessions |
| AGY | Existing headless CLI | Cached AGY login and disposable home; no assumed SDK login equivalence |
| Direct HTTP | Existing explicitly selected adapter | Caller-selected endpoint/key; no worker MCP tools |

`--worker-transport native` explicitly restores all-native calls.
`--worker-transport cli` explicitly selects the legacy CLI implementation for
Codex, Claude or OpenCode. There is no automatic fallback. SDK dependency errors
are actionable failures. Model, effort and transport are independent from the
hosting assistant's settings. Existing checkpoints without a transport field
retain legacy CLI execution when resuming the same backend; an explicit argument
or `MIMIR_WORKER_TRANSPORT` overrides it. New checkpoints persist transport.

Native configuration selects the provider. In particular, a fresh Codex worker
reads current configuration and does not resume the hosting conversation's stale
provider metadata. The implementation never rewrites global provider settings.

## Connect a local MCP

Use absolute interpreter, script and run-root paths. The durable run root should
be the same when switching hosts; the working directory determines native
project configuration and local research context. Adapt the placeholders below.

Codex `config.toml`:

```toml
[mcp_servers.mimir]
command = "C:/path/to/mimir/.venv/Scripts/python.exe"
args = ["C:/path/to/mimir/scripts/mcp_server.py", "--run-root", "C:/path/to/project/.mimir/runs"]
cwd = "C:/path/to/project"
```

Claude project `.mcp.json` (explicit workspace avoids relying on a host-specific `cwd` field):

```json
{"mcpServers":{"mimir":{"command":"C:/path/to/mimir/.venv/Scripts/python.exe","args":["C:/path/to/mimir/scripts/mcp_server.py","--run-root","C:/path/to/project/.mimir/runs","--workspace","C:/path/to/project"]}}}
```

Antigravity `.agents/mcp_config.json` uses the same `mcpServers` command/args
shape; an explicit `--workspace` also fixes project context there.

OpenCode `opencode.jsonc`:

```json
{"mcp":{"mimir":{"type":"local","command":["C:/path/to/mimir/.venv/Scripts/python.exe","C:/path/to/mimir/scripts/mcp_server.py","--run-root","C:/path/to/project/.mimir/runs"],"cwd":"C:/path/to/project","enabled":true}}}
```

Restart/reconnect the host after registration. Native project trust and tool
permissions remain host-owned. Primary-source contracts and version qualifications
are recorded in [the research note](INTEGRATION_RESEARCH_2026-10-22.md).

## Run lifecycle

1. `start_run(goal=..., backend=..., model=..., effort=..., phase="plan")`
   returns a unique run ID and queued status promptly. Supply `task_brief` for
   the host's interpretation. Planning performs no preliminary public search.
2. `get_status(run_id, after_sequence=..., limit=...)` returns durable status,
   concise `narration` and meaningful `updates`. The default `wait_seconds=20`
   waits for meaningful changes (0–25 seconds); heartbeat-only activity does not
   wake it early. `include_events=true` exposes up to 100 diagnostic events.
   Advance `next_sequence` and drain pages while `has_more`.
   Sequences remain monotonic across phase invocations; each event also keeps
   its engine phase sequence. Waiting means no new result has been recorded.
   The host combines nearby milestones into one brief Mímir chat update about
   every 45–60 seconds during long work. It does not relay every event or routine
   check, replay historical updates or announce completion before reading the
   artifacts and giving one final answer. Short runs usually need only an opening
   sentence and final answer. Raw hashes, paths and usage belong in artifacts or
   requested diagnostics. Tool-call card rendering remains controlled by the host.
3. When planning is completed, call `start_run(run_id=..., phase="execute")`.
   After execution completes, start synthesis using the same run ID. Phase
   validation rejects out-of-order calls and duplicate owners.
4. After successful synthesis and cleanup, `get_result` returns bounded report
   or sidecar chunks plus their local path. Follow `next_offset` while `has_more`.
5. `cancel_run` requests cancellation and joins worker cleanup before returning.
   It only controls tasks owned by that manager/host. Reading status and results
   from another host is supported; cancelling that host's active work is not.

Run metadata, event journal, checkpoints and report files live below the run ID
in the selected root. An OS-held lease prevents duplicate phase ownership and
releases on process death. An abandoned active record becomes `interrupted` when
read after its lease is free without changing stored files. Status exposes
`recoverable_phases`. Restart can resume execution from planned/executing
checkpoints, validating retained inputs and full outputs before reuse. Failed
and cancelled tasks retry; completed tasks are retained. Synthesis can recover
an existing synthesized checkpoint after failed/interrupted cleanup, checking
publication hashes and making no further model or learning calls. Recovery does
not independently establish termination of historical descendants from a failed
process. Interrupted planning requires a new run. Failed invocations never
present artifacts as successful final results.

Disconnect closes the MCP manager and cancels its owned work. The process does
not continue autonomously after host shutdown. Run evidence remains available
for recovery. Retention/deletion is intentionally an explicit filesystem operation;
the MCP tools do not delete user history or old reports.

Stdout carries MCP protocol only. Structured engine progress is captured directly
into the journal; the hosting assistant still turns selected events into chat
updates. No sampling, experimental MCP Tasks or host-native delegation is used.

## Execution policy, evidence and diagnostics

`mode="single"` builds a deterministic one-worker graph and publishes that answer
without a reflection call. Default `review` builds two specialists followed by a
dependent critic, then one final reflective synthesis. `swarm` opts into a model
plan bounded by `max_tasks` (default four, maximum sixteen). Model decomposition
cannot add an executive/synthesis worker. Task count is separate from concurrency;
JEV is off by default. Its protected/exempt status is explicit rather than a
misleading comparative score. The scheduler dispatches each newly eligible task
within the concurrency limit, without waiting for unrelated tier siblings.

Worker schemas contain `answer`, `sources`, `claims` and `gaps`. Sources retain
locators, retrieval times/types and supporting excerpts; claims link source IDs
and label reported support/inference/conflict. Sidecars aggregate task-scoped
records, gaps and a final locator-string-presence audit. Record coverage uses
`unknown`, `partial` or `reported`; none means complete research or independently
verified facts. Missing source locators remain explicit and the full registry
is preserved in Markdown. Entailment and source-read authenticity need independent
review. Legacy unstructured worker output remains coverage-unknown.

Task planning precedes retrieval. The old unconditional scout search was removed;
the original raw objective stays in the checkpoint and is never submitted by the
planning stage to a public search service. `task_brief` supplies a host
interpretation (outcome, constraints, components, evidence needs, missing
information), validated against bounded fields and frozen for resume. Without
it, single/review templates instruct workers to interpret before tools and record
`worker_pending`. Swarm's existing planner returns the brief and tasks; Codex
uses text-only planning. Other adapters receive a no-retrieval instruction without
the same runtime guarantee. Query/domain arguments are optional retrieval hints.
The legacy scout remains available for diagnostics, outside the normal pipeline.

`get_diagnostics` and CLI `--diagnostics` expose runtime/installed identity,
interpreter/dependencies, workspace/run root, memory paths and configured native
credential presence. No model request, remote login or credential value is
returned. Static native configuration inspection is limited; the runtime owns
final resolution. For native Codex on Windows, required provider variables absent
from the Process scope may be supplied from User then Machine scope privately
through SDK child-environment overrides. An explicitly empty Process value
suppresses inheritance. Global environment/configuration and login state stay
untouched. Native preflight names missing prerequisites before planning.

CLI `--doctor` adds bounded public search checks, also available through
`get_diagnostics(check_search=true)`. Ordinary diagnostics remain offline.
The doctor uses the native scout's HTTP client plus system curl against
DuckDuckGo, Bing and Google, in parallel, with a fixed `Neapolitan pizza recipe`
query. It distinguishes certificate errors, proxy blocks, other HTTP failures,
and HTTP 200 pages without recognizable result links. Curl requests have an
8-second deadline and 1 MiB response limit. Worker readiness is separate from
search usability. If the default scout fails it recommends testing Firecrawl MCP;
it does not configure a connection, change the search provider or call a model.

Memory defaults to `read`, using project `.mimir/LEARNINGS.md` curated guidance.
Default legacy fallback reads standing guidance only, omitting historical dated
run takeaways; an explicitly chosen bank may include those notes. `off` omits
learning context. Explicit `write` appends source-linked, unvalidated candidates
under `.mimir/learning-candidates.jsonl`, without automatic promotion or consumption.
Candidate writes use an OS lease and identity deduplication. Read/off create no
learning file; reinstall preserves old package notes.

Per-worker input characters, durations and available token usage are persisted.
Codex fresh-thread total counts all model completions including tool continuations.
Unknown usage and billed costs stay explicit. `max_context_chars` (default120000)
rejects oversized input before worker dispatch, retaining evidence without silent
truncation. This is character admission, not a model-token or dollar budget.
[Evaluation](EVALUATION.md) compares policies with fixed cases and disclosed metrics.

## Runtime limits

The SDKs still launch local runtimes. Codex startup wraps synchronous work; a
cancelled startup must settle before final close, so shutdown can exceed the
worker deadline. Its upstream close does not explicitly close stdout/stderr
handles and does not independently prove arbitrary descendants terminated.
Claude also escalates native shutdown, which can take additional seconds.

Public scouting uses blocking source requests. Cancellation joins these bounded
requests before releasing ownership. The old direct HTTP adapters retain their
blocking-thread limitation. None of these waiting periods represent new findings.

The Python scout honors configured CA files in this order: `REQUESTS_CA_BUNDLE`,
`CURL_CA_BUNDLE`, `SSL_CERT_FILE`, then `NODE_EXTRA_CA_CERTS`. This supports the
shared enterprise/Zscaler bundle without disabling HTTPS verification. urllib
adds the selected certificates to its default trust; curl uses the selected CA
file. Missing or invalid files fail retrieval. Certificate trust does not grant
access through a proxy policy block. On 2026-10-22, the pizza search passed TLS
with the configured SKF ZIA bundle but returned HTTP 403 from `Zscaler/6.2`.

Codex filesystem read-only policy does not enforce a remote MCP query-only
catalog. Claude applies a deny hook; OpenCode combines query permissions with
native restrictions. A model's output schema, source assertions and evidence
hashes still require validation; hashes establish output identity.

Cross-host stdio configuration is documented; local runtime tests qualify only
the versions and account paths actually exercised. The complete publication and
learning files remain individually atomic, rather than one cross-file transaction.

## Verification on 2026-10-22

The improved implementation passed 223 tests with one POSIX-only skip and
106 subtests. Real stdio MCP probes completed planning, execution and synthesis
with native Codex/direct Azure in both single and review modes. Single used one
worker invocation, recorded 63.79 seconds of engine time and 64,688 native tokens;
review used three graph workers plus synthesis, recorded 78.14 seconds and
253,479 native tokens. These were focused dependency-file smoke checks, not an
answer-quality benchmark or a controlled speed comparison. Tokens include fresh
thread context and tool continuations; they do not establish billed dollar cost.
Both checked the exact SDK pin, read complete report/sidecar results and preserved
learning-file hashes. The single report correctly retained a missing full-locator
qualification; final factual validation remained false.

Regression cases include completed-task persistence/reuse, mutated prompt/profile/
dependency/output rejection, dependent admission before unrelated slow siblings,
joined repeated cancellation, cleanup failure without success, same-ID publication
recovery without another model/learning call, stale completion rejection, read-only
status behavior, safe actionable configuration errors and context rejection without
truncation. The installed package matches the runtime identity and old notes were
preserved with a package backup. Reconnect hosts to load the new diagnostic tool.

The observations below predate these improvements and describe earlier probes.

The live Codex SDK probe used direct Azure, gpt-6.1-sol and low effort. It read
requirements-workers.txt through a read-only local tool and returned the exact
pinned dependency under the requested schema. A real MCP client launched the
server, started a planning phase, polled structured progress and observed
completed planning through the Codex SDK. Full three-phase engine orchestration
was exercised through the managed interface with deterministic workers.

The actual Claude SDK/runtime reached its provider and returned HTTP 401. The
adapter now reports authentication as the prerequisite with elapsed time; no
login/provider settings were changed. The installed OpenCode 1.19.3 server
passed health, owned session creation/deletion and Windows process/storage
cleanup without inference. Its current native configuration resolver timed out;
that path fails after a bounded discovery deadline rather than claiming success.
Authenticated Claude/OpenCode full-swarm runs remain unverified.

Interface regressions include actual MCP stdio initialization/tools/errors,
real Codex SDK wire serialization against a local protocol simulator, full
managed three-phase execution, journal crash-tail recovery, cursor continuity,
repeated cancellation, ownership across managers and actual OS lease release
after killing its owning process. The final suite count is recorded in tasks/history.md.
