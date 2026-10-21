# M Í M I R // Porting & Re-Creation Meta-Prompt

> **English:** Use this prompt in **Claude Code**, **OpenAI Codex CLI**, **Cursor**, **Aider**, or any AI coding agent to instruct the model to build or port an instance of Mímir to your environment.  
> **Svenska:** Använd denna prompt i **Claude Code**, **OpenAI Codex**, **Cursor**, **Aider** eller valfri AI-utvecklare för att instruera modellen att bygga eller anpassa en egen instans av Mímir i en ny miljö.

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
- `agy --model <model> -p "<prompt>"`
- Zero external API keys needed; inherits local AGY credentials.

### Option C: Direct API (OpenAI / Anthropic / Ollama)
Standard async HTTP caller using Python standard library (`urllib.request` or `httpx`):
- **OpenAI / Ollama:** Send POST to `https://api.openai.com/v1/chat/completions` (or `http://localhost:11434/v1/chat/completions`) with low temperature (0.1–0.2) and `response_format: {"type": "json_object"}`.
- **Anthropic Claude:** Send POST to `https://api.anthropic.com/v1/messages` with `claude-3-5-haiku-20241022` or `claude-3-7-sonnet-20250219`.

---

## REQUIRED CODE COMPONENTS TO REPRODUCE

When implementing in Python, ensure the following modules are present:
1. `backend.py`: Base class `BaseSwarmBackend`, `SwarmTask`, `SwarmResult`, and concrete implementations (`CodexSwarmBackend`, `AgySwarmBackend`, `OpenAISwarmBackend`, `AnthropicSwarmBackend`).
2. `task_graph.py`: `TaskNode`, `TaskGraph` (with Kahn's topological sort), `Blackboard`, and `EvidenceContract` with SHA256 hashing.
3. `jev_gate.py`: `JevDecisionGate` for fast System-1 scoring and DAG pruning.
4. `research_scout.py`: `ResearchScout` with arXiv API query and DuckDuckGo search.
5. `gepa_optimizer.py`: `GepaOptimizer` for reflective Pareto evolution against Red-Team critique.
6. `jarvis_memory.py` / `mimir_memory.py`: Cumulative memory reader and appender targeting `LEARNINGS.md`.
7. `mimir.py`: Main entrypoint with CLI argument parsing and rich console HUD.

## INSTRUCTIONS FOR THE AI ASSISTANT

Inspect the current project structure, generate the required scripts adhering to the specifications above, and verify that the system can run a sample goal end-to-end.
```
