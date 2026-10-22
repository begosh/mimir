# Mycroft

A portable evidence-led research team driven by the AI harness you are already
using. The host plans and schedules native subagents, admits their evidence,
challenges their conclusions and publishes one answer. There is no Python
engine, SDK launcher, MCP service, API key setup or background daemon.

## Try it on another computer

Unzip the distribution and install into the project you want to investigate:

```powershell
./Install-Mycroft.ps1 -Harness codex -ProjectRoot 'C:/work/my-project'
# Alternatives: -Harness claude or -Harness opencode
```

PowerShell 7 works on Windows, macOS and Linux. Windows PowerShell 5.1 is also
supported. Installation copies files only, refuses existing destination files,
and does not edit provider, model, permissions, MCP or global configuration.
Restart your harness if the skills or agents do not appear. These adapters use
documented file formats; see [support and manual installation](docs/HARNESSES.md).
For an arbitrary harness, copy `skills/` into its skill discovery directory and
use the canonical role prompts through its native delegation tools.

Start with:

```text
Use $mycroft to review this project's architecture. Use native subagents,
local evidence only, review mode, and write the report under .mycroft/runs/.
```

```text
Use $mycroft-corpus to investigate the supplied documents. Index all files,
delegate bounded slices, preserve conflicting revisions, and cite exact spans.
```

```text
Use $mycroft-optimize to evaluate and improve the investigator instructions
against my source-grouped train/dev/held-out examples. Keep tools and model fixed.
```

The primary skill explicitly requests delegation. Custom agent registrations are
a convenience: a harness that supports native subagents can use role prompts
even when it cannot load custom agent files. If native delegation is unavailable,
Mycroft reports the limitation; it does not launch another AI CLI. A user can
choose a clearly labeled serial adaptation.

## What carries over from Mimir

| Mimir capability | Mycroft implementation | Practical difference |
| --- | --- | --- |
| single / review / swarm | Host-scheduled task graph; specialists and dependent critic | Model follows a scheduling protocol rather than a Python engine |
| DSPy typed prediction | Fixed input/output contracts and validated JSON evidence records | No DSPy compilation or library-level structured output guarantee |
| RLM corpus investigation | Corpus index, bounded reads, delegated slices, recursive question reduction | No generated Python, interpreter state or executable RLM |
| JEV pruning | Optional importance/overlap score with protected evidence dependency closure | Heuristic estimates, off by default |
| Reflective synthesis | Critic issues, source-linked revisions, final claim reconciliation | One bounded revision pass; no optimizer implied |
| Upstream GEPA | Separate trace-driven instruction proposals, evaluation and Pareto selection | GEPA-inspired search; upstream GEPA is not executed |
| Recovery and blackboard | Host-owned run ledger and admitted immutable worker attempts | Durable when files are available; weaker than engine-enforced recovery |
| Learning | Read curated guidance; explicit candidate capture and selection | No automatic promotion |

Read [the design and capability mapping](docs/DESIGN.md) for invariants and limits.
The three skills disclose detailed procedures only when needed. Seven role
prompts serve both generic spawning and the supplied harness adapters.

## Validate and test

```powershell
./Test-Package.ps1
./Build-Adapters.ps1 -Check
./tests/Test-Tooling.ps1
```

Run the [behavioral acceptance prompts](tests/ACCEPTANCE.md) in a fresh session.
The fixtures contain revision conflicts, missing evidence and instruction
injection. Live test evidence for this build is recorded in
[VALIDATION.md](docs/VALIDATION.md). Other harnesses and another computer need
their own native smoke test; a valid package is not proof of retrieval or quality.

`plugin.json` also exposes the skills through the portable Agent Plugins layout.
Plugin discovery does not install harness-specific custom agents; use the installer
for those, or let the skill spawn generic agents with the role prompt included.
No connector or remote messaging capability is bundled.
