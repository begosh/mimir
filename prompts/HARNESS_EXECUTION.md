# CLI worker compatibility

The skill invokes the Python engine through the host's shell tool. The engine
uses `BaseSwarmBackend.spawn` / `parallel` / `execute_graph` across adapters.
The objective and blackboard carry context; the host conversation is not resumed.

| Backend | Worker call | Session policy | Model / effort |
| --- | --- | --- | --- |
| Codex | `codex exec`, stdin prompt, last-message file | Native `--ephemeral`, read-only sandbox | Explicit economical model; reasoning effort defaults to low |
| AGY | `agy -p`, JSON output, sandbox, skill expansion disabled | Disposable home/XDG/temp directories per call; selected login files copied | Default `gemini-3.8-flash-low`, low effort |
| Claude Code | `claude --print`, stdin prompt, JSON result | Native `--no-session-persistence`, read/search tools, no inherited MCP | Default `haiku`; no adjustable effort on Haiku; other models need `--effort` support |
| OpenCode | `opencode run`, stdin prompt, JSON events | Disposable home/XDG/temp directories; no attach/resume; sharing disabled | Explicit `provider/model`; effort maps to variant, or none to omit it |

`--check` validates installed CLI help and settings without a model call. It
does not establish login, availability, pricing, or actual persistence behavior.
Models and variants belong to the installed CLI/provider: no silent model upgrades
or HTTP fallback are performed.

## Authentication and persistence limits

Codex/Claude retain normal login configuration. Non-persistence does not disable
account-side usage records or imply empty configuration.

AGY has no native ephemeral switch in locally inspected help. The adapter copies
only `.gemini/oauth_creds.json`, `google_accounts.json`, and `installation_id` to
each disposable home. No history or skills are copied. Other credential stores
may require adapter updates. Temporary conversations can exist during execution;
normal cleanup removes them. Forced termination of the entire engine can leave
temporary files; this must not be described as native zero-persistence.

OpenCode copies only `auth.json` from the normal XDG OpenCode data directory.
It never copies `opencode.db`, which can contain conversations. DB-only logins
and providers requiring additional authentication plugins are not yet supported.
Global configuration is not copied. Project configuration can still be discovered;
inline worker permissions deny tools except read/glob/grep/webfetch and disable
sharing. Choose a supported economical variant instead of assuming low works
on every model. OpenCode 1.19.3 has been checked locally as described below.
Its `--no-replay` option disables mini-interface history rendering on resume/resize;
it does not prevent persistence and is not an `opencode run` flag.

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

Events include `run_started`, `worker_settings`, `phase_started`,
`research_completed` / `research_skipped`, `tasks_pruned`, `graph_ready`,
`task_submitted`, `task_completed` / `task_failed`, `graph_incomplete`,
`critique_collected`, `reflection_completed`, and `run_completed` / `run_failed` /
`run_cancelled`. Every event has schema_version, a monotonic sequence, and elapsed
seconds. Completion includes artifact paths; successful task/critique/reflection
events include bounded excerpts from returned outputs. No private model reasoning
or raw objective/task prompts are requested or streamed.

`task_submitted` means a DAG task was queued before awaiting the tier, not that a
model request is already active. A quiet period means no event has arrived, not
proof of continued progress. Host assistants should summarize selected events,
avoid duplicates by sequence, poll their process tool, and state failures truthfully.
Delivery timing depends on the host's shell-output/polling support. This is engine
progress streaming, not token-by-token streaming from child CLI processes.

## Configuration

The host checks `--config-status --host <known-host>` before the first project
investigation; `--host-model <known-model>` supplies a model suggestion without
choosing or saving it. For Codex, propose the known host model at low worker
effort. Name the host model/effort and proposed worker model/effort in the setup
question, with another model or HTTP access as alternatives. An existing
explicit choice in the conversation counts as agreement. Discovery itself
never saves or starts a run.

After agreement, `--configure --backend <choice> --model <model> --effort <effort>`
saves `.mimir/config.json` at the nearest Git root (current directory outside
Git). Every installed skill copy uses that project profile. It stores no keys,
login files or conversation history. A saved choice is reused even when another
harness hosts the next run. A one-run override does not rewrite it. Ask again
when the choice is unclear or the selected path fails preflight/authentication;
never switch providers silently.

Execution precedence is explicit arguments, environment, then the matching
saved backend profile. Environment overrides include:

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
