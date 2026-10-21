---
name: mimir
description: Run Mímir's evidence-led research and problem-solving swarm for complex objectives, architecture reviews, and investigations, using authenticated CLI workers and the Python DAG engine. Respond in English or Swedish to match the user.
---

# M Í M I R // Keeper of Wisdom & Autonomous Swarm

Mímir is a five-phase research and problem-solving pipeline. The hosting assistant
captures the objective and presents the result; the Python engine owns decomposition,
JEV pruning, DAG scheduling, the blackboard, red-team reflection, and cumulative
learning. A CLI backend supplies fresh worker calls using an existing login.
Preserve that division across AGY, Codex, Claude Code, OpenCode, and other harnesses.

## Mode A: Python swarm (default for a Mímir investigation)

Before the first investigation in a project, inspect setup without invoking a
model: `python <skill-dir>/scripts/mimir.py --config-status --host <known-host>`.
Include `--host-model <known-model>` when the host model is available in the
session. Omit unknown host/model values rather than guessing. The saved profile is
`.mimir/config.json` at the nearest Git root (current directory outside Git),
shared across installed skill copies. It contains backend, model, and effort;
credentials remain in CLI login stores or environment variables.

If no profile exists, ask an early setup question even when the host is obvious:
"Your Codex harness uses gpt-6.1-sol at high effort. Should Mímir reuse your CLI
login with gpt-6.1-sol at low effort for swarm workers and remember this for the
project, or would you prefer another worker model or API backend?"
Adapt the CLI name to the host. If unclear, present the available CLIs and the
HTTP option. Resolve the worker model and effort before saving. An existing
explicit choice in this conversation counts as the answer; do not ask twice.
Do not start dependent work while that choice is pending.

After agreement, save with
`python <skill-dir>/scripts/mimir.py --configure --backend <choice> --model <model> --effort <effort>`.
AGY/Claude defaults may omit model. API choices use `openai`, `anthropic`, or
`ollama`; keys/endpoints are configured outside this file. This command saves
preferences, not proof of authentication or a successful run.

On subsequent uses, reuse the profile across hosting harnesses. A user-requested
one-run override should not rewrite it unless they ask to remember the change.
If setup is corrupt, the host is unclear with no profile, or the selected path
fails preflight/authentication, explain the problem and ask whether to repair it
or choose another path. Never silently switch from a saved CLI to an API backend.
Setup questions are explicitly part of Mímir's workflow, not repeated permission
requests for every run.

1. Resolve the directory containing **this loaded SKILL.md**. Its engine is
   `scripts/mimir.py` relative to that directory. Do not guess a global path or
   switch to another installed copy. Keep the working directory on the user's
   project so workers can inspect relevant files.
2. Capture a self-contained objective including the user's constraints, relevant
   paths, and established facts. CLI workers do not inherit this conversation.
   For multiline context, write a UTF-8 objective file and use `--goal-file`;
   do not interpolate conversation text into a shell command.
3. Reuse the saved backend or an explicit user/environment override: `agy`,
   `codex`, `claude` (Claude Code), `opencode`, or a chosen HTTP backend. For
   first setup, suggest the known host; do not silently select it. `auto` cannot
   choose an execution path for an unconfigured investigation.
   HTTP backends (`openai`, `anthropic`, `ollama`) require explicit selection;
   do not switch to them because a CLI fails.
4. Select economical settings independently of the hosting assistant:
   - AGY: default `gemini-3.8-flash-low`, effort `low`. Check `agy models` if unavailable.
   - Claude Code: default `haiku`. Haiku has no adjustable effort; do not upgrade
     to an expensive model merely to obtain effort controls.
   - Codex: when the host model is known, propose that model at `low` effort as
     the first-use worker default, naming both host and worker settings. Offer a
     smaller available model when cost matters. If the host model is unknown,
     ask for an available worker model. Save the agreed explicit model; do not
     inherit the host's model or effort silently on later runs.
   - OpenCode: explicitly select a configured `provider/model` with `--model` or
     `MIMIR_OPENCODE_MODEL`. Effort maps to `--variant`; choose a supported
     economical variant, or `--effort none` for models without variants.
   Run `python <skill-dir>/scripts/mimir.py --backend <backend> --check` with
   the selected model/effort arguments. This checks CLI flags and settings without
   a model call. It does not validate login, model availability, pricing, or actual
   session persistence. Read [harness compatibility](prompts/HARNESS_EXECUTION.md)
   for the selected backend's limits. Resolve failures before starting the swarm.
5. Start the engine through the harness's shell tool, then poll its process/session
   until it exits. Tool names vary; native sub-agent tools are not required.
   Example with resolved and safely quoted paths:

   ```text
   python -u <skill-dir>/scripts/mimir.py --goal-file <objective-file> --backend <backend> --model <worker-model> --effort low --progress jsonl --output <report.md>
   ```

   Omit backend/model/effort arguments when reusing saved setup. Default concurrency is 4 and timeout is
   180 seconds per CLI call; override with `--concurrency` / `--worker-timeout`.
   Use `--skip-web` only when external scouting is intentionally excluded.
   Relay selected JSONL progress events as short commentary updates while polling:
   phase changes, sources found, the task graph, queued/completed/failed tasks,
   JEV pruning, and critique/reflection excerpts. Track `sequence` to avoid
   repeating events. Group busy bursts into one update rather than printing raw
   JSON, hashes, or every worker message. `task_submitted` means queued for execution,
   not proof that a CLI/model call has started. During a quiet long-running call,
   state the last known phase and that no new progress arrived; do not invent work.
   Use recorded task results and brief rationale summaries, not private model
   reasoning. The terminal default keeps the Rich display for direct Python runs.
6. On success, read the Markdown report and JSON sidecar, then present synthesis,
   sources, critique, and limitations. A hash records output identity; it does not
   prove factual correctness. Do not call unsupported claims verified merely
   because they carry an EvidenceContract.
7. On failure, report the failed call/phase and missing prerequisite. Do not
   present stale output as this run's result, claim completion, or silently
   substitute native delegation or a conversational answer.

Worker conversations are disposable; results remain on Mímir's blackboard and
in its report. Codex/Claude use native persistence controls. AGY/OpenCode use
per-call temporary storage, removed after the call. Temporary isolation is not
native zero-persistence; see the compatibility reference. Login reuse consumes
the account's allowance or configured provider charges.

The engine reads/appends `LEARNINGS.md` in its own skill directory. Separate
copied installations have separate memories. Do not change global CLI configuration
or purge user sessions as part of an investigation.

## Mode B: Native conversational protocol

For a user-requested direct response without the engine, follow
[MIMIR_SYSTEM_PROMPT.md](prompts/MIMIR_SYSTEM_PROMPT.md): research, decompose and
prioritize, resolve with evidence, challenge assumptions, synthesize. Explain
that this is conversational mode: it does not execute the Python DAG, blackboard,
hashing, or persistence machinery. Do not imply that a swarm ran.

## Design and controls

[MIMIR_PORTING_PROMPT.md](prompts/MIMIR_PORTING_PROMPT.md) specifies the pipeline.
Porting changes the backend adapter while preserving that pipeline. Native
sub-agents are not an automatic replacement for the engine.

Run `python <skill-dir>/scripts/mimir.py --help` for flags including `--sources`,
`--depth`, and `--no-jev`. Precedence is explicit command arguments, then
`MIMIR_BACKEND` / `MIMIR_<BACKEND>_MODEL` / `MIMIR_MODEL` / `MIMIR_EFFORT`, then
the saved project profile. A different backend never inherits another backend's
saved model or effort.

## Svenska

Använd Python-svärmen för en Mímir-utredning: hitta motorn relativt den laddade
skill-filen, skicka ett självständigt mål med alla begränsningar och välj en
inloggad CLI-backend uttryckligen. Kontrollera modell, låg ansträngningsnivå och
sessionshantering med `--check`. Låt motorn hantera DAG, JEV, Blackboard och
motståndargranskning. Läs rapporten och JSON-resultatet efter lyckad körning.
Ett hashvärde styrker resultatets identitet, inte dess sanningshalt. Vid fel ska
bristerna redovisas; byt inte tyst till en annan motor eller ett direkt chatsvar.
