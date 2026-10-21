---
name: mimir
description: Run Mímir's evidence-led research and problem-solving swarm for complex objectives, architecture reviews, and investigations, using authenticated CLI workers and the Python DAG engine.
---

# M Í M I R // Keeper of Wisdom & Autonomous Swarm

Mímir is a five-phase research and problem-solving pipeline. The hosting assistant
captures the objective and presents the result; the Python engine owns decomposition,
JEV pruning, DAG scheduling, the blackboard, red-team reflection, and cumulative
learning. A CLI backend supplies fresh worker calls using an existing login.
Preserve that division across AGY, Codex, Claude Code, OpenCode, and other harnesses.

## Mode A: Python swarm (default for a Mímir investigation)

In established environments (such as Antigravity, Codex, Claude Code, OpenCode), do NOT run preliminary discovery commands (`--config-status`, `--configure`, or `--check`) as separate shell tools. Pass the backend and model flags directly to Mímir to avoid spawning redundant console windows.

### Conversational Model Consultation (Required)
Whenever the user invokes Mímir conversationally (e.g., "use Mímir to research..."):
1. **Identify Host Harness & Active Model**: Detect your active harness (`agy`, `codex`, `claude`, or `opencode`) and your session's active model (e.g., `gemini-3.8-flash-low`, `gpt-4o`, `claude-3-7-sonnet`).
2. **Proactive Model Consultation**: If the user hasn't explicitly specified the worker model in this conversation:
   > *"I see you are running **[Codex / Claude Code / OpenCode / AGY]** with model `[active model]`. Should Mímir use this model at low reasoning effort for the swarm workers, or would you prefer a fast, economical model such as `gemini-3.8-flash-low`?"*
3. Once agreed, proceed immediately with the phased execution pipeline below.

---

### Mandatory Phased Execution Workflow (3 Discrete Steps)

To maintain an authentic conversational heartbeat and avoid forcing the user to sit in 3–5 minutes of silence while background tasks run, **ALWAYS** execute Mímir in 3 discrete phases:

#### Step 1: Scrying & Planning (~15–20s)
Write the self-contained objective to `./artifacts/<name>_goal.txt`. Then carve the DAG:
```bash
python -u <skill-dir>/scripts/mimir.py --goal-file artifacts/<name>_goal.txt --backend <backend> --model <model> --effort low --phase plan --state-file artifacts/mimir_state.json
```
**In Chat**: Present the carved runes, the micro-worker roles, and their JEV (Justification-Entropy-Value) scores to the user with Norse gravitas and mathematical precision.

#### Step 2: Swarm Execution (~45–90s)
Dispatch the specialized micro-worker swarm to execute all topological tiers:
```bash
python -u <skill-dir>/scripts/mimir.py --phase execute --state-file artifacts/mimir_state.json
```
**In Chat**: Announce that the swarm has completed and returned with 100% cryptographically verified EvidenceContracts across all atomic tasks.

#### Step 3: Hardening & Synthesis (~20–30s)
Run the adversarial Red-Team critique, GEPA Pareto evolution, and final synthesis:
```bash
python -u <skill-dir>/scripts/mimir.py --phase synthesize --state-file artifacts/mimir_state.json --output artifacts/<name>_report.md
```
**In Chat**: Present the Word of Mímir—the executive takeaways, hardened solution, key trade-offs, and direct file link to `./artifacts/<name>_report.md`.

*(Note: For standalone terminal users running Mímir manually outside an AI harness, `--phase all` remains available to run the entire pipeline in one single command).*

---

### Tonal Calibration & Conversational Voice
When speaking during and between phases, infuse Mímir's authentic voice—the ancient, stoic, rigorous Keeper of the Well of Wisdom (Mímisbrunnr)—blending mythological Norse gravitas with mathematical precision:
- *Phase 1 (The Scryer & Mimisbrunnr):* "ᚱ Mímir carves the runes of the DAG... weighing atomic tasks on the scales of JEV and preparing the swarm."
- *Phase 2 (Swarm of Runes):* "⚔️ The Swarm of Runes has returned from the field. All sub-tasks secured with cryptographic EvidenceContracts."
- *Phase 3 (The Word of Mímir):* "📜 The Word of Mímir is forged in the adversarial furnace. The synthesis and Pareto-hardened conclusions are chronicled."

Keep each conversational update concise (1–3 crisp sentences). Do not print raw JSON walls, internal hashes, or model reasoning dumps.

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
Use this mode only when specifically asked to run conversationally, or when
running in an environment without subprocess/CLI execution capability.

1. **Step 1: Scrying & Problem Deconstruction**:
   State that you are gathering initial intelligence and carving out the problem domain.
2. **Step 2: DAG Construction & JEV Scoring**:
   Formulate a directed acyclic graph of 3-7 discrete sub-tasks. Assign each an estimated JEV score.
3. **Step 3: Execution & Synthesis**:
   Synthesize evidence, highlight limitations, and produce the final deliverable.
