# Shared engine and supported transports

The connected Mímir MCP is the skill's execution route. It exposes start/status/
cancel/result/diagnostics over the same `scripts/engine.py` used by the terminal adapter.
New worker runs use Codex/Claude SDKs and a private OpenCode HTTP server; AGY
retains its cached-login CLI. See [current integration contract](../docs/INTEGRATION.md)
and [primary-source research](../docs/INTEGRATION_RESEARCH_2026-10-22.md).

The CLI contracts and dated observations below describe the explicit legacy
`--worker-transport cli` path. They do not certify the new SDK/server adapters.
Old checkpoints retain CLI transport unless explicitly overridden. OS leases
now release on process death; never remove an active lock file. SDK/native worker
permissions and authentication are separate from inbound host MCP permissions.

# CLI worker compatibility

The skill invokes the Python engine through the host's shell tool. The engine
uses `BaseSwarmBackend.spawn` / `parallel` / `execute_graph` across adapters.
The objective and blackboard carry context; the host conversation is not resumed.
The current checkout rejects invalid graphs, failed screening results,
empty/truncated worker output and invalid reflection envelopes. Completion events
are emitted per worker. These are regression-tested contracts; local live
observations below identify the versions and paths actually exercised.

| Backend | Worker call | Session policy | Model / effort |
| --- | --- | --- | --- |
| Codex | `codex exec`, stdin prompt, last-message file | Native `--ephemeral`, read-only sandbox | Explicit economical model; reasoning effort defaults to low |
| AGY | `agy -p`, JSON output, sandbox, skill expansion disabled | Disposable home/XDG/temp directories per call; selected login files copied | Default `gemini-3.8-flash-low`, low effort |
| Claude Code | `claude --print`, stdin prompt, JSON result | Native `--no-session-persistence`, native MCP configuration, read/search and Work IQ queries | Default `haiku`; no adjustable effort on Haiku; other models need `--effort` support |
| OpenCode | `opencode run`, stdin prompt, JSON events | Disposable home/XDG/temp directories; no attach/resume; sharing disabled | Explicit `provider/model`; effort maps to variant, or none to omit it |

`--check` validates installed CLI help and settings without a model call. It
does not establish login, availability, pricing, or actual persistence behavior.
Models and variants belong to the installed CLI/provider: no silent model upgrades
or HTTP fallback are performed.

## Authentication and persistence limits

Codex/Claude retain normal login configuration. Non-persistence does not disable
account-side usage records or imply empty configuration.

AGY has no native ephemeral switch in locally inspected help. The adapter copies
`.gemini/oauth_creds.json`, `google_accounts.json`, and `installation_id`, plus
MCP definitions from `.gemini/config/mcp_config.json`,
`.gemini/antigravity/mcp_config.json`, and the `mcpServers` section of
`.gemini/settings.json` to each disposable home. No history, hooks or skills are
copied. Workers use `--mode plan` and sandboxing, without permission bypass.
Other credential stores
may require adapter updates. Temporary conversations can exist during execution;
normal cleanup removes them. Forced termination of the entire engine can leave
temporary files; this must not be described as native zero-persistence.

OpenCode copies `auth.json` and `mcp-auth.json` from the normal XDG data directory.
It never copies `opencode.db`, which can contain conversations. DB-only logins
and providers requiring additional authentication plugins are not yet supported.
The native config directory, explicit `OPENCODE_CONFIG`, and inline
`OPENCODE_CONFIG_CONTENT` are preserved while session data/cache/state remain
temporary. OpenCode resolves native JSON/JSONC and project configuration itself;
plugins remain subject to their own compatibility with disposable storage.
Inline worker permissions default to deny and permit read/glob/grep/webfetch,
websearch and `*_ask_work_iq`. Preflight resolves native permissions through
`opencode debug config`; restrictive native rules follow the query allowlist
so exact denies retain precedence. Inline read/search restrictions are retained;
mutation tools remain denied even when native or inline configuration allows them.
Sharing and auto-update are disabled. Choose a supported economical variant instead of assuming low works
on every model. OpenCode 1.19.3 has been checked locally as described below.
Its `--no-replay` option disables mini-interface history rendering on resume/resize;
it does not prevent persistence and is not an `opencode run` flag.

## Research tool access

Each worker uses its selected CLI's configuration, not a copy of the host chat's
tool set. Work IQ configured only in Codex does not become available to a Claude
worker. Codex retains native MCP configuration and permissions. Claude retains
native MCP configuration (no `--strict-mcp-config`) and allows the specific
`ask_work_iq` operation under configured server names, alongside built-in
read/search tools; existing deny rules still apply under `dontAsk` mode.
Other configured MCP tools require appropriate native permissions.

Codex's filesystem read-only sandbox does not impose an MCP mutation allowlist;
native MCP permissions still apply. The worker's read/query instruction is
guidance and does not independently enforce remote-operation restrictions.

All four CLI workers receive guidance to use Work IQ for internal M365 evidence,
prefer primary sources for public questions, and preserve source URLs, dates and
retrieval limits. Absent tools, authentication failures and permission denials
are evidence gaps, never proof that no records exist. Tool discovery is not a
guarantee that a server connects or that a model calls it. Direct HTTP backends
have no MCP adapter. The Python scout remains public-web/arXiv only; worker
retrieval results enter the blackboard and final synthesis.

Temporary storage avoids normal session history only if the CLI honors those
roots. Adapter tests verify Mímir's commands and storage ownership; repeat live
probes when upgrading a harness. Never purge user sessions to simulate ephemeral
execution. Authentication reuse still consumes allowance or provider charges.

## Sources checked

- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive)
- Installed `claude --help`, `agy --help`, and `agy models`.
- [OpenCode CLI documentation](https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/cli.mdx)
- [OpenCode XDG roots](https://github.com/anomalyco/opencode/blob/dev/packages/util/src/global-roots.ts)
- [OpenCode run implementation](https://github.com/anomalyco/opencode/blob/dev/packages/cli/src/run/run.ts)

## Validation in this checkout

- Offline contract/regression tests cover disposable storage,
  native persistence flags, failed result envelopes, timeout cleanup, dependency
  context and cancellation, skill packaging, and five-phase report generation
  through a mocked CLI. External web scouting and JEV were disabled in that
  orchestration fixture; it is not a live full-swarm certification.
  Progress tests verify flushed JSONL, event order, queued work before replies,
  source metadata, successful/failed runs, and actual CLI failure output.
- AGY Flash/low completed a live one-call JSON probe. A read-only check found
  no matching probe in its normal conversation summaries.
- Claude Code preflight passed; its live Haiku probe failed authentication.
  Fix the local CLI login before using that backend.
- Codex preflight passed with an explicitly selected mini model; the live probe
  hit its 45-second timeout. Successful live execution remains unverified.
- **2026-10-22 update:** Codex CLI 0.163.0 with `azure_headroom`,
  `gpt-6.1-sol` and low effort completed planning, six-task execution and
  schema-constrained reflection/report generation in three phase commands.
  The host's environment snapshot initially lacked the configured provider key;
  importing the existing Windows user environment into child invocations fixed
  that prerequisite. The original 180-second execution deadline timed out;
  the successful retry used 600 seconds. One worker was rerun after embedded
  JSON extraction discarded its prose; parsing now preserves mixed prose.
  An invalid reflection structure failed visibly before a schema-constrained
  retry succeeded. These findings qualify this account/provider/run only.
- OpenCode 1.19.3 preflight now passes. `debug paths` confirms all home/XDG/temp
  paths resolve inside disposable storage. A live `opencode/minimax-m3.1-flash-free`
  worker with effort `none` returned the expected JSON in 32.7 seconds; a read-only
  before/after comparison found no new entries in the normal session database.
  This probe verifies that worker/storage path, not all providers or DB-only auth.

These are local observations, not guarantees for other accounts or CLI releases.

## Live progress in a hosting harness

Use `--progress jsonl` to emit one flushed JSON object per execution event on
stdout. The default terminal mode retains Rich panels and tables. Both modes run
the same Python pipeline; no extra model calls are made for progress summaries.

Events include `run_started`, `worker_research_tools`, `phase_started`,
`scout_querying`, `dag_decomposing`, `run_waiting`,
`research_completed` / `research_skipped`, `tasks_pruned`, `graph_ready`,
`task_submitted`, `task_completed` / `task_failed`, `graph_incomplete`,
`plan_completed`, `execute_completed`, `critique_collected`, `reflection_started`,
`reflection_completed`, `synthesis_started`, and `run_completed` / `run_failed` /
`run_cancelled`. Every event has schema_version, a monotonic sequence, and elapsed
seconds. Sequence restarts at 1 for each discrete phase process, so deduplicate
by phase invocation and sequence. Completion includes artifact paths; successful task/critique/reflection
events include bounded excerpts from returned outputs. No private model reasoning
or raw objective/task prompts are requested or streamed.

`task_submitted` means a DAG task was queued before awaiting the tier, not that a
model request is already active. A quiet period means no event has arrived, not
proof of continued progress. Host assistants should summarize selected events,
avoid duplicates by sequence, poll their process tool, and state failures truthfully.
`run_waiting` is emitted about every 15 seconds while the event loop is alive.
It names the current phase and cumulative submitted/completed/failed task counts.
It proves process liveness and waiting, not new findings or worker token activity.
Scouting runs in a thread so synchronous source requests do not block this signal.
Task results and finish events are recorded as each worker returns. The
dependency tier barrier remains in place; queued tasks can wait for a concurrency
slot. An unchanged completion count means no new result has been recorded.

For Codex, launch with `exec_command` and a short yield, then poll the returned
process session with `write_stdin` every 10–20 seconds. If these tools are wrapped
in `functions.exec`, yield promptly and resume the exec cell with `functions.wait`
when needed; keep its cell ID distinct from the process session ID. After reading
events, send a concise **commentary** message to the user: tool stdout by itself
does not fulfill the chat update requirement. Group worker events, relay each
phase transition, and give a truthful waiting update during long phases. Use
Mímir's restrained Norse voice as defined in `SKILL.md`.

Delivery timing depends on the host's shell-output/polling support. This is engine
progress streaming, not token-by-token streaming from child CLI processes. Output
hashes establish identity, not factual verification. Await the phase's completion
event and successful process exit before launching the next discrete phase.

## Configuration

In established harnesses, the host passes agreed backend/model/effort flags
directly to each phase. CLI checks happen inside the engine; no separate setup
command is required. Use `--config-status` for manual setup or troubleshooting.
Propose the known host model at low worker effort when supported; if the exact
host model is unavailable, disclose that instead of inventing it. A conversation
choice or saved profile counts as agreement and is reused. Do not switch
providers silently when a worker fails.

If the user asks to remember the choice, `--configure --backend <choice> --model <model> --effort <effort>`
saves `.mimir/config.json` at the nearest Git root (current directory outside
Git). Every installed skill copy uses that project profile. It stores no keys,
login files or conversation history. A saved choice is reused even when another
harness hosts the next run. A one-run override does not rewrite it. Ask again
when the choice is unclear or the selected path fails preflight/authentication;
never switch providers silently.

Execution precedence is explicit arguments, environment, then the matching
phase checkpoint when resuming, then the saved backend profile. A resume keeps
the planned output path, timeout and concurrency unless explicitly overridden.
Execute requires a planned checkpoint; synthesis requires all planned results.
Environment overrides include:

```text
MIMIR_AGY_MODEL=gemini-3.8-flash-low
MIMIR_CLAUDE_MODEL=haiku
MIMIR_CODEX_MODEL=<available economical model>
MIMIR_OPENCODE_MODEL=<configured provider/model>
MIMIR_EFFORT=low
```

Without a saved profile or explicit backend choice, the entrypoint stops with
`configuration_required` before model calls or memory writes. `auto` at the
entrypoint means resolve environment/saved settings; the factory's internal
CLI discovery is not first-use consent. A different backend never inherits
another backend's saved model/effort. `claude` means Claude Code; `anthropic`
selects HTTP. HTTP adapters currently do not send reasoning-effort parameters.
