# M Í M I R // Porting & Re-Creation Meta-Prompt

> Use this prompt in **Claude Code**, **OpenAI Codex CLI**, **Cursor**, **Aider**, or any AI coding agent to instruct the model to build or port an instance of Mímir to your environment.

---

```markdown
# TASK: Build / Port "M Í M I R" Autonomous Epistemic Swarm Engine

You are tasked with building or adapting **M Í M I R** – an autonomous multi-agent epistemic research and problem-solving swarm engine originally developed for Antigravity (AGY) and OpenAI Codex CLI, now being ported or configured in your current environment (e.g. OpenAI Codex CLI, OpenAI API, Anthropic Claude API, Claude Code, or local Ollama).

## CORE ARCHITECTURAL SPECIFICATION

Mímir is not a single prompt; it is a five-phase recursive multi-agent pipeline designed to eliminate hallucinations, enforce formal rigor, and iteratively harden solutions against adversarial attacks.

### 1. THE 5-PHASE PIPELINE

1. **Phase 1: Omni-Channel Scryer (Research Scout)**
   - Dynamically determines the ground-truth authority venues for any arbitrary question:
     * Software/Algorithms -> GitHub code & HackerNews post-mortems
     * Science/Math/AI -> arXiv preprints & academic papers
     * Systems/Protocols -> Official RFCs & documentation
     * Open Web -> Broad contextual background
   - Uses zero-API-key open query mechanisms (e.g. arXiv Export API, TLS-impersonated DuckDuckGo HTML parsing via curl_cffi/BeautifulSoup, or native web search tools).

2. **Phase 2: Kahn-Validated Recursive Task DAG & JEV Gating**
   - Decomposes the user's objective into 4–6 atomic sub-tasks with strict roles:
     * `Domain-Analyst`: Core mechanics and invariances.
     * `Formal-Modeler` / `Code-Architect`: Exact algorithms, data models, or code.
     * `Red-Team-Critic`: Attacks assumptions, finds race conditions, deadlock, edge cases.
     * `Executive-Synthesizer`: Combines all findings into a unified solution.
   - Computes topological execution tiers using Kahn's algorithm to ensure acyclicity.
   - **JEV Gate (Joint Expected Value):** Uses a fast System-1 evaluator to compute $JEV = P(\text{critical}) \times \text{gain} - \text{cost}$ for each candidate branch and prunes branches below threshold (default 0.30) to eliminate wasted compute.

3. **Phase 3: Parallel Swarm Execution & EvidenceContracts**
   - Executes the DAG tiers concurrently using worker agents.
   - Each completed task produces an **EvidenceContract**:
     * Grounding reference (source URL, tool call ID, code snippet).
     * Cryptographic SHA-256 hash of raw output.
   - Verified data is committed to a shared **Blackboard** and delta-synced to dependent nodes.
   - Failures automatically cascade downwards to mark dependent nodes `CANCELLED`, preventing deadlocks.

4. **Phase 4: Mímir's Counsel & GEPA Pareto-Hardening**
   - Collects all draft solutions and Red-Team critiques.
   - Runs a Genetic-Pareto Evolutionary Algorithm (GEPA) reflection:
     * Analyzes failure modes highlighted by the Red-Team.
     * Performs an evolutionary mutation that seals vulnerabilities without inflating code complexity.

5. **Phase 5: The Word of Mímir & Cumulative Long-Term Memory**
   - Formulates the final response in Mímir's stoic Nordic persona.
   - Appends distilled architectural patterns, anti-patterns, and core heuristics to a persistent `LEARNINGS.md` file so future runs inherit past wisdom.

---

## HOW TO ADAPT THE LLM BACKEND

Mímir supports headless CLI execution (inheriting authenticated local sessions without API keys) as well as direct HTTP API providers:

### Option A: OpenAI Codex CLI (`codex exec`)
Spawns headless `codex` subprocesses:
- `codex exec --ephemeral --skip-git-repo-check -s read-only -o <out_file> "<system_instruction>\n\n<prompt>"`
- Zero external API keys needed; inherits existing local Codex login and environment proxy.

### Option B: Antigravity CLI (`agy`)
Spawns headless `agy` subprocesses:
- `agy --model <model> --effort low --output-format json --sandbox --disable-slash-commands -p "<prompt>"`
- Zero external API keys needed; inherits local AGY credentials.
- Each worker uses disposable home/XDG/temp storage containing selected login
  files. Do not copy user conversations or rely on print mode being ephemeral.

### Option C: Claude Code (`claude --print`)
- `claude --print --no-session-persistence --output-format json --model haiku`
- Reuses the CLI login; defaults to economical Haiku, which has no adjustable
  effort. Retain native MCP configuration; permit built-in read/search and
  the Work IQ `ask_work_iq` operation under configured server names. Use
  `--permission-mode dontAsk` and preserve existing deny rules. Do not enable
  blanket permission bypass or remove research tools to isolate conversations.

### Option D: OpenCode (`opencode run`)
- `opencode run --format json --model <provider/model> --variant <supported-low-cost-variant>`
- Use per-worker disposable XDG/home/temp storage; reuse only supported login
  material. Never copy a session database, attach to the host, resume, or share.
- Omit variant only for models without variants. DB-only authentication requires
  a future adapter extension and must fail clearly rather than copy sessions.

See [HARNESS_EXECUTION.md](HARNESS_EXECUTION.md) for verified controls and limits.
CLI workers preserve the five-phase engine and blackboard; native sub-agents
are not an automatic substitute. On first project use, the skill suggests the
known host's CLI login or offers available CLI/HTTP choices, asks for agreement,
and saves backend/model/effort through `mimir_config.py` in `.mimir/config.json`.
For Codex, propose the known host model at low worker effort and name both
host and worker settings. Existing explicit user choices count as agreement.
Reuse the saved profile across hosts; ask again when the choice is unclear or
unavailable, and never silently fall back to HTTP. Supply conversation
constraints in a self-contained objective and preflight the selected settings.
Relay real engine JSONL activity when the host supports polling.

### Option E: Direct API (OpenAI / Anthropic / Ollama)
Standard async HTTP caller using Python standard library (`urllib.request` or `httpx`):
- **OpenAI / Ollama:** Send POST to `https://api.openai.com/v1/chat/completions` (or `http://localhost:11434/v1/chat/completions`) with low temperature (0.1–0.2) and `response_format: {"type": "json_object"}`.
- **Anthropic Claude:** Send POST to `https://api.anthropic.com/v1/messages` with `claude-3-5-haiku-20241022` or `claude-3-7-sonnet-20250219`.

---

## REQUIRED CODE COMPONENTS TO REPRODUCE

When implementing in Python, ensure the following modules are present:
1. `backend.py`: Base class `BaseSwarmBackend`, `SwarmTask`, `SwarmResult`, and concrete implementations (`CodexSwarmBackend`, `AgySwarmBackend`, `ClaudeCodeSwarmBackend`, `OpenCodeSwarmBackend`, `OpenAISwarmBackend`, `AnthropicSwarmBackend`).
2. `task_graph.py`: `TaskNode`, `TaskGraph` (with Kahn's topological sort), `Blackboard`, and `EvidenceContract` with SHA256 hashing.
3. `jev_gate.py`: `JevDecisionGate` for fast System-1 scoring and DAG pruning.
4. `research_scout.py`: `ResearchScout` with arXiv API query and DuckDuckGo search.
5. `gepa_optimizer.py`: `GepaOptimizer` for reflective Pareto evolution against Red-Team critique.
6. `jarvis_memory.py` / `mimir_memory.py`: Cumulative memory reader and appender targeting `LEARNINGS.md`.
7. `mimir.py`: Main entrypoint with CLI argument parsing and rich console HUD.
8. `mimir_config.py`: Project setup, credential-free preferences and explicit/environment/saved resolution.

## INSTRUCTIONS FOR THE AI ASSISTANT

Inspect the current project structure, generate the required scripts adhering to the specifications above, and verify that the system can run a sample goal end-to-end.
```
