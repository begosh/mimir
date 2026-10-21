# M Í M I R // The Omniscient Oracle & Autonomous Swarm

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Bilingual: EN / SV](https://img.shields.io/badge/Bilingual-EN%20%2F%20SV-gold.svg)](#svenska)
[![skills.sh](https://img.shields.io/badge/skills.sh-compliant-purple.svg)](https://skills.sh)

> *Drink from the Well. Truth distilled from the noise of the cosmos.*

**Mímir is a research and problem-solving skill for your coding assistant**, backed
by a Python swarm engine. Ask it to investigate a difficult question, review an
architecture, or challenge a proposed solution. It researches sources, builds a
task graph, runs specialist workers, applies adversarial critique, and returns
a report with cumulative learning. Responses can be in English or Swedish.

Use it inside your CLI harness with its existing login, or run the same engine
directly from Python with a CLI or HTTP backend. CLI login reuse avoids separate
API-key setup; it still consumes your account allowance or provider charges.

[Skill usage](#use-mímir-as-a-skill) · [Supported harnesses](#supported-cli-harnesses) ·
[Python usage](#run-the-python-engine-directly) · [Architecture](#how-the-swarm-works) ·
[Svenska](#svenska)

## Use Mímir as a skill

Install into your current project, then start a new harness session so it can
discover the skill:

```bash
npx skills add begosh/mimir --skill mimir
```

Add `-g` for a global installation. Python 3.10+ and the dependencies in
[requirements.txt](requirements.txt) are needed to run the swarm. The repository
installer below also installs those dependencies.

Ask your assistant naturally:

```text
Use Mímir to review our background-job architecture. Inspect this repository,
compare retry and idempotency strategies, and challenge the failure modes.
Keep the design suitable for a small team.
```

On first use in a project, Mímir asks which backend, worker model and effort you
want. When the host is known, it suggests reusing that CLI login. It names the
proposed worker settings before saving them in `.mimir/config.json`. Keys and
conversation history are kept outside that file. Later runs reuse the agreed
settings across hosting harnesses; Mímir asks again if the choice is unclear or
the selected path fails its checks.

The **hosting assistant** and **swarm workers** have separate model settings.
For example, a Codex host using `gpt-6.1-sol` at high effort can propose
`gpt-6.1-sol` at low effort for workers. You can choose another available model.
The choice is saved explicitly; workers do not silently inherit later changes
to the host model. Lower effort does not guarantee a particular cost saving.

### Example: AGY

**Illustrative conversation, not a recorded run.** Start `agy` in your project:

```text
You: Use Mímir to review our retry and idempotency design.

Assistant: Use your AGY CLI login for Mímir's swarm workers with
gemini-3.8-flash-low at low effort, and remember this for the project?
You can also choose another worker model or an API backend.

You: Yes, remember those settings.

Assistant: Mímir workers: AGY · gemini-3.8-flash-low · low effort.
Research started; I'll relay sources and task progress as they arrive.
```

### Example: Codex

**Illustrative conversation, assuming the named model is available.** Start
`codex`; invoke `$mimir` or ask it to use Mímir:

```text
You: $mimir Review our background-job architecture and its failure modes.

Assistant: Your Codex harness uses gpt-6.1-sol at high effort.
Use your Codex CLI login with gpt-6.1-sol at low effort for Mímir's
swarm workers, and remember this? You can choose another model or API access.

You: Yes, use that model at low effort for the swarm.

Assistant: Mímir workers: Codex · gpt-6.1-sol · low effort · ephemeral calls.
The Python engine will run the task graph and red-team review.
```

### Example: OpenCode

**Illustrative conversation, assuming the provider/model is available.** Start
`opencode` in your project:

```text
You: Use Mímir to investigate the safest retry strategy for our workers.

Assistant: Use OpenCode for Mímir's swarm workers with
opencode/minimax-m3.1-flash-free, no effort variant, and remember this?
Workers use disposable storage. You can choose another provider/model or API.

You: Yes, remember it.

Assistant: Mímir workers: OpenCode · opencode/minimax-m3.1-flash-free · variant none.
I'll relay the engine's research, task completion and critique updates.
```

### Example: progress inside a harness

**Illustrative updates after a successful setup.** Exact wording, task counts,
sources and timings depend on the objective and actual engine events:

```text
Research: found documentation and reference implementations for review.
Planning: the task graph is ready; low-value branches were screened by JEV.
Swarm: independent analysis tasks are queued; dependent tasks wait for results.
Swarm: the domain analysis completed; its findings are available to the critic.
Critique: the red-team identified a retry/idempotency gap.
Reflection: the revised proposal addresses the recorded critique.
Complete: report and JSON results saved; synthesis and limitations follow.
```

The skill relays flushed engine activity and excerpts from returned results.
These updates show work and findings; they do not expose private model reasoning.
Delivery depends on the host's shell polling. The Python engine owns the DAG,
JEV gate and shared blackboard throughout the run.

## Supported CLI harnesses

These four CLIs have implemented **worker adapters** and skill installer targets.
The conversations above are examples, not an exhaustive list of supported hosts.
A different host can load the skill and use a supported worker CLI through its
shell tools; it needs a new adapter to become a worker backend itself.

| Harness / worker CLI | Backend | Worker model and effort | Session handling | Validation in this checkout |
| --- | --- | --- | --- | --- |
| Antigravity (`agy`) | `agy` | Default `gemini-3.8-flash-low`, low | Per-call disposable home/XDG/temp storage | Live one-call probe succeeded |
| OpenAI Codex CLI | `codex` | Agreed explicit model; propose known host model at low effort | Native `--ephemeral`, read-only sandbox | Preflight passed; live probe timed out |
| Claude Code | `claude` | Default `haiku`; Haiku has no adjustable effort | Native `--no-session-persistence`, read/search tools | Preflight passed; live probe failed local authentication |
| OpenCode | `opencode` | Explicit `provider/model`; supported variant or `none` | Per-call disposable home/XDG/temp storage, sharing disabled | Live one-call probe succeeded; normal session IDs unchanged |

Offline tests cover adapter behavior and orchestration. These probes do not
certify every model, CLI version or full live swarm. AGY/OpenCode may create
temporary conversations during execution; normal cleanup removes that storage.
OpenCode currently reuses `auth.json` credentials and does not support DB-only
login. Its `--no-replay` option controls history rendering, not persistence.

See [harness compatibility and validation](prompts/HARNESS_EXECUTION.md) for
controls, authentication limits and sources. Direct HTTP backends are also
available: `openai`, `anthropic`, and `ollama`. Mímir never silently switches a
failed CLI run to HTTP access.

## Install from the repository

```bash
git clone https://github.com/begosh/mimir.git
cd mimir

# Install dependencies and copy the skill to supported global directories.
python scripts/install.py --global

# Or install into a chosen project.
python scripts/install.py --project /path/to/project
```

The installer packages the skill, scripts and prompts for Codex, AGY, Claude
Code, OpenCode and the shared `.agents/skills` directory. It creates supported
targets; it does not establish CLI login or certify installed model access.
Run `python scripts/install.py --help` for target filtering and other options.

Shell installers are also available:

```bash
# Linux / macOS / WSL
curl -fsSL https://raw.githubusercontent.com/begosh/mimir/main/install.sh | bash -s -- --global
```

```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/begosh/mimir/main/install.ps1 | iex
```

## Run the Python engine directly

From a cloned repository:

```bash
python -m pip install -r requirements.txt

# Inspect project settings and available CLIs without invoking a model.
python scripts/mimir.py --config-status

# Save your chosen worker backend, model and effort.
python scripts/mimir.py --configure --backend agy --model gemini-3.8-flash-low --effort low

# Validate the selected CLI's flags and settings without a model call.
python scripts/mimir.py --check

# Run with the saved settings and the Rich terminal display.
python scripts/mimir.py "Review our background-job architecture and retry strategy"
```

The Python entrypoint expects you to configure a backend or pass one explicitly.
It stops before model calls if neither exists. The interactive first-use
question is handled by the hosting skill; `--configure` saves your explicit
selection for direct Python use.

### One-run CLI examples

Replace placeholder models/variants with values available to your login:

```bash
python scripts/mimir.py "Review our retry design" --backend agy
python scripts/mimir.py "Review our retry design" --backend claude
python scripts/mimir.py "Review our retry design" --backend codex --model <available-worker-model> --effort low
python scripts/mimir.py "Review our retry design" --backend opencode --model <provider/model> --effort <variant-or-none>
```

These overrides do not rewrite the saved profile. For a longer objective, put
the question, relevant paths and constraints in a UTF-8 file:

```bash
python -u scripts/mimir.py --goal-file objective.txt --progress jsonl --output artifacts/review.md
```

`terminal` is the default progress format; `jsonl` emits flushed activity for a
hosting assistant or other consumer. A successful run writes a Markdown report
and JSON sidecar, then appends learning to `LEARNINGS.md` beside the installed
engine. Separate copied installations have separate learning files.

### HTTP and local-model examples

Configure credentials in your environment before using a hosted HTTP provider:
`OPENAI_API_KEY` for OpenAI-compatible access, or `ANTHROPIC_API_KEY` for Anthropic.
Use `OPENAI_BASE_URL` for an OpenAI-compatible endpoint such as LM Studio or vLLM.
Keep credentials outside the saved Mímir profile.

```bash
python scripts/mimir.py "Compare background-job designs" --backend openai --model gpt-4o-mini
python scripts/mimir.py "Challenge our retry assumptions" --backend anthropic --model <available-anthropic-model>
python scripts/mimir.py "Analyze idempotent APIs" --backend ollama --model <installed-local-model> --skip-web
```

The Ollama backend defaults to `http://localhost:11434/v1`; an installed model
and running Ollama service are required. `--skip-web` excludes external scouting.
HTTP adapters currently do not send reasoning-effort parameters.

### Useful options

| Option | Behavior |
| --- | --- |
| `--config-status`, `--configure` | Inspect or save project backend/model/effort |
| `--host`, `--host-model` | Supply known host information for a setup suggestion; never save automatically |
| `--backend`, `--model`, `--effort` | Override worker settings for this run |
| `--check` | Validate CLI flags/settings; does not verify login or model access |
| `--goal-file` | Load a UTF-8 objective with context and constraints |
| `--progress terminal\|jsonl` | Rich display or flushed activity events |
| `--concurrency` | Maximum concurrent workers; default 4 |
| `--worker-timeout` | Timeout per CLI call; default 180 seconds |
| `--output` | Report path; default `artifacts/mimir_solution.md` |
| `--skip-web`, `--sources` | Disable scouting or add comma-separated source domains |
| `--depth`, `--no-jev` | Set decomposition depth or disable JEV screening |

Settings resolve from explicit arguments, then `MIMIR_BACKEND`,
`MIMIR_<BACKEND>_MODEL` / `MIMIR_MODEL`, and `MIMIR_EFFORT`, then the saved
matching backend profile. A different backend never inherits another backend's
saved model or effort. Run `python scripts/mimir.py --help` for the full CLI.

## How the swarm works

The [skill](SKILL.md) captures the objective, agrees on execution settings, starts
the Python engine through the host's shell, and presents the results. The
engine preserves Mímir's five-phase design across all worker backends:

```text
Objective + cumulative learning
              ↓
1. Research scouting → source context
              ↓
2. Recursive task decomposition → acyclic DAG + JEV screening
              ↓
3. Parallel specialist workers → EvidenceContracts + shared blackboard
              ↓
4. Red-team critique → GEPA reflection and revised solution
              ↓
5. Synthesis → report + cumulative learning
```

The DAG carries dependency results to later workers and cascades failures.
Worker calls are fresh and receive self-contained context; they do not resume
the host conversation. Native host sub-agents are not an automatic substitute
for this engine. EvidenceContract hashes record output identity; source quality
and factual correctness still require assessment.

Implementation: [orchestrator](scripts/mimir.py), [worker adapters](scripts/backend.py),
[project configuration](scripts/mimir_config.py), [DAG and blackboard](scripts/task_graph.py),
[JEV gate](scripts/jev_gate.py), [research scout](scripts/research_scout.py),
[GEPA reflection](scripts/gepa_optimizer.py), [learning](scripts/jarvis_memory.py).
The [porting specification](prompts/MIMIR_PORTING_PROMPT.md) describes the design
to preserve when adding another adapter.

## Svenska

> *Drick ur Mimers brunn. Sanningen är silad ur kosmos brus.*

**Mímir är en skill för forskning, arkitekturgranskning och komplex
problemlösning**, med en Python-motor som kör svärmen. Installera med
`npx skills add begosh/mimir --skill mimir` och be din kodassistent:

```text
Använd Mímir för att granska vår arkitektur för bakgrundsjobb.
Jämför återförsök och idempotens, och utmana antagandena.
```

Vid första användningen föreslår Mímir CLI-inloggning eller API och frågar vilken
modell och ansträngningsnivå svärmens arbetare ska använda. Värdens modell och
arbetarnas inställningar visas separat. Exempel: Codex med `gpt-6.1-sol high`
kan föreslå `gpt-6.1-sol low` för svärmen. Valet sparas i projektets
`.mimir/config.json`, utan nycklar eller konversationshistorik, och återanvänds.

Implementerade CLI-adaptrar är **AGY, Codex, Claude Code och OpenCode**.
Samtalen ovan är illustrativa exempel; valideringsstatus och begränsningar finns
i tabellen och [kompatibilitetsguiden](prompts/HARNESS_EXECUTION.md). CLI-inloggning
undviker separat API-nyckelhantering men förbrukar kontots tilldelning eller
leverantörens debitering. OpenCode använder tillfällig lagring; `--no-replay`
styr visning av historik och gör inte en session flyktig.

Samma motor kan köras direkt från Python:

```bash
python -m pip install -r requirements.txt
python scripts/mimir.py --configure --backend agy --model gemini-3.8-flash-low --effort low
python scripts/mimir.py --check
python scripts/mimir.py "Granska vår strategi för återförsök och idempotens"
```

Motorn hanterar forskning, DAG/JEV, parallella arbetare och Blackboard,
motståndargranskning/GEPA och slutrapport med lärdomar. Skillen visar verkliga
statushändelser och sammanfattningar från resultaten. Ett hashvärde styrker
resultatets identitet; det garanterar inte att uppgifterna är sanna.

## License

[MIT](LICENSE). Fri att använda, anpassa och distribuera.
