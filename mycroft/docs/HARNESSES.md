# Installation and harness support

The installer is project-scoped and copies three skill folders plus seven native
agent definitions. It does not launch a harness or change its configuration.
`-WhatIf` previews writes. Existing files cause preflight failure before copying;
choose another project or deliberately handle a previous installation yourself.

| Harness | Skill destination | Agent destination | Status |
| --- | --- | --- | --- |
| Codex | `.agents/skills/` | `.codex/agents/*.toml` | Current official format fetched; native generic-team smoke tested in this host; custom-file discovery needs target test |
| Claude Code | `.claude/skills/` | `.claude/agents/*.md` | Conventional adapter supplied; official page blocked by local network policy; unqualified here |
| OpenCode | `.agents/skills/` | `.opencode/agents/*.md` | Current agent directory/mode/permission docs fetched; runtime unqualified here |
| Other native harness | Its skill discovery location | Canonical role prompts through native spawn | Capability mapping needed; no universal support claim |

## Codex

```powershell
./Install-Mycroft.ps1 -Harness codex -ProjectRoot 'C:/work/project'
```

Current Codex standalone custom agent TOML requires `name`, `description` and
`developer_instructions`. All supplied agents omit model/effort settings to
inherit the parent. Permissions, provider and MCP catalogs come from the parent;
the adapter does not claim it can override them. Ask the coordinator to use
registered `mycroft-investigator`, `mycroft-alternatives` and `mycroft-critic`,
or generic spawning with the complete role prompt when named roles are absent.

Use the actual native collaboration tools provided by the host. This environment
has `spawn_agent`, `followup_task`, `send_message`, `wait_agent`,
`interrupt_agent` and `list_agents`; another client may expose different tools.
Do not call collaboration through a shell or assume its tools exist inside a
code orchestration tool. Native close/release is separate from interrupt.

Project discovery follows the harness's trust rules. Restart if needed and run
the local acceptance prompt. Current docs support project `.agents/skills` and
`.codex/agents`; older clients may need a different adapter. Resolve against
their actual documentation rather than silently writing legacy config tables.

Sources fetched 2026-10-22:

- [Codex subagents and custom agent schema](https://developers.openai.com/codex/multi-agent)
- [Codex Agent Skills discovery](https://developers.openai.com/codex/skills)
- [Portable plugin manifest](https://developers.openai.com/plugins/build/plugins)

## Claude Code

```powershell
./Install-Mycroft.ps1 -Harness claude -ProjectRoot 'C:/work/project'
```

Markdown subagent definitions contain `name`, `description`, `model: inherit`
and the canonical role body. The coordinator owns recursion and shared writes.
Tool availability and read-only behavior must be verified in the target harness;
the package imposes no presumed remote MCP enforcement. Do not assume Claude
subagents can themselves spawn. Generic root-mediated spawning is sufficient.

The official [subagents documentation](https://code.claude.com/docs/en/sub-agents)
could not be retrieved here because of the organization's network policy. This
adapter is a candidate to test, not a verified live integration. Inspect the
target client `/agents` and skill discovery before accepting a result as a team
run. Adjust its registration wrapper if its version requires different fields;
the canonical role prompt remains portable.

## OpenCode

```powershell
./Install-Mycroft.ps1 -Harness opencode -ProjectRoot 'C:/work/project'
```

Markdown agents declare `mode: subagent`, deny `edit` and deny child `task`
delegation. The root orchestrates all tasks. No model override is included.
Inherited read/search tools remain subject to the target project's permissions;
these declarations are not a universal remote tool policy. Confirm the client
can discover skills from `.agents/skills`, or copy the skill folders to its
documented native location.

Agent location and mode/permission guidance fetched 2026-10-22 from the
[official OpenCode agent documentation](https://opencode.ai/docs/agents/).
Shared `.agents/skills` discovery was also confirmed in the
[official skill documentation](https://opencode.ai/docs/skills/).
No OpenCode login, inference, tool access or runtime run was tested here.

## Manual installation without PowerShell

Copy `skills/mycroft`, `skills/mycroft-corpus` and `skills/mycroft-optimize` into
the harness's discovery directory, preserving each entire folder. Copy the seven
matching adapter files into its native agent directory. Do not overwrite unrelated
files or move only SKILL.md: linked references/assets/roles are required.

Generic native delegation can use `skills/mycroft/references/roles/*.md` directly
with the evidence contract and a bounded task packet. An accessible prompt path
must be explicitly read by the worker, or include its content in the spawn.
All three skills should be discoverable together. Plugin installations can
namespace invocation; use the displayed skill name when the harness requires it.

## Transfer integrity

`Build-Package.ps1` creates an allowlisted archive and SHA-256 sidecar. Compare
the archive digest on the destination. The package contains no workspace sources,
credentials, private run outputs, Python environments or existing Mimir artifacts.
`Test-Package.ps1` checks local resources; `Build-Adapters.ps1 -Check` detects
registration drift. Behavioral acceptance remains a separate native run.
