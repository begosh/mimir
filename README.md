# M Í M I R // The Omniscient Oracle & Autonomous Swarm

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Bilingual: EN / SV](https://img.shields.io/badge/Bilingual-EN%20%2F%20SV-gold.svg)](#)
[![Backends: AGY | Codex | OpenAI | Claude | Ollama](https://img.shields.io/badge/Backends-AGY%20%7C%20Codex%20%7C%20OpenAI%20%7C%20Claude%20%7C%20Ollama-green.svg)](#)

> [English](#-english) | [Svenska](#-svenska)

---

## 🇬🇧 English

> *"Drink from the Well. Truth distilled from the noise of the cosmos."*  
> *"Drick ur Mimers brunn. Sanningen är silad ur kosmos brus."*

**M Í M I R** is an autonomous multi-agent epistemic research and problem-solving swarm engine, named after the wisest being in Norse mythology. Mímir unites ancient wisdom with modern agentic AI engineering to autonomously solve complex engineering, architectural, scientific, and strategic challenges.

It combines real-time omni-channel research scouting, Kahn-validated acyclic task DAGs, Joint Expected Value (JEV) System-1 decision gating, cryptographic EvidenceContracts, adversarial Red-Team critique with Genetic-Pareto Evolutionary Algorithm (GEPA) reflection, and persistent cumulative memory.

---

### 🌟 Core Innovations & Architecture

```text
[User Objective / Research Goal]
         │
         ├────────► [Load Cumulative Wisdom from LEARNINGS.md]
         ▼
[Phase 1: Mímir's Scryer] ──────► Dynamic Omni-Channel Scouting (GitHub, arXiv, Docs, Web)
         │
         ▼
[Phase 2: Mimisbrunn's DAG] ────► Recursive Decomposition + JEV System-1 Pruning
         │
         ▼
[Phase 3: The Rune Swarm] ──────► Parallel Micro-Agents + EvidenceContracts (SHA-256)
         │
         ▼
[Phase 4: Mímir's Counsel] ─────► Adversarial Red-Team Critique & GEPA Pareto Mutation
         │
         ▼
[Phase 5: The Word of Mímir] ───► Deliver Hardened Truth + Update LEARNINGS.md
```

1. **Dynamic Omni-Channel Research Scouting ([research_scout.py](file://./scripts/research_scout.py)):**
   Dynamically identifies ground-truth authority sources for any given problem:
   - **GitHub**: Reference implementations and source code.
   - **arXiv**: Academic preprints and mathematics.
   - **HackerNews**: Field engineering post-mortems and production battle scars.
   - **Open Web**: Broad domain specifications without external API keys.
2. **Kahn-Validated Recursive Task DAG ([task_graph.py](file://./scripts/task_graph.py)):**
   Decomposes objectives into atomic, non-overlapping subtasks executed in topological tiers. Strict acyclicity checks and automated failure cascading prevent scheduling deadlocks.
3. **JEV System-1 Decision Gate ([jev_gate.py](file://./scripts/jev_gate.py)):**
   High-speed mathematical branch screening based on Joint Expected Value:
   $$JEV = P(\text{impact}) \times \text{gain} - \text{cost}$$
   Prunes low-value branches before execution to minimize latency and token usage.
4. **Anti-Hallucination via EvidenceContracts:**
   Every delivered subtask must provide verifiable citations and code, sealed with cryptographic SHA-256 hashes against a shared **Blackboard**.
5. **Adversarial Red-Team & GEPA ([gepa_optimizer.py](file://./scripts/gepa_optimizer.py)):**
   Stress-tests draft solutions against dedicated adversarial critics (Red-Team) and mutates the architecture along the Pareto front (resilience vs. simplicity).
6. **Cumulative Long-Term Memory ([LEARNINGS.md](file://./LEARNINGS.md)):**
   Saves and re-indexes proven patterns, edge-case hazards, and core heuristics across runs.
7. **Modular Multi-Backend Engine ([backend.py](file://./scripts/backend.py)):**
   Runs seamlessly across local and cloud backends:
   - **OpenAI Codex CLI (`codex`)** – Zero API keys required; executes via `codex exec` inheriting your local authenticated Codex CLI session and proxy settings.
   - **Antigravity CLI (`agy`)** – Zero API keys required; inherits existing local AGY authentication with sandboxed session isolation.
   - **OpenAI API & Compatible Endpoints** (`gpt-4o-mini`, `gpt-4o`, Ollama, LMStudio, vLLM, OpenRouter).
   - **Anthropic Claude API** (`claude-3-5-haiku-20241022`, `claude-3-7-sonnet-20250219`).

---

### 🚀 Quickstart & Installation

#### 1. Clone the repository
```bash
git clone https://github.com/begosh/mimir.git
cd mimir
```

#### 2. Install dependencies
```bash
pip install -r requirements.txt
```
*(Requires only `rich`, `curl_cffi`, and `beautifulsoup4`. Standard Python handles all HTTP/process calls with zero heavy SDK bloat).*

#### 3. Run Mímir

##### Option A: OpenAI Codex CLI (Zero API keys, uses local Codex login)
```bash
python scripts/mimir.py "Design a fault-tolerant distributed cache with Redis and consistent hashing" --backend codex
```

##### Option B: Antigravity CLI (Zero API keys, default if `agy` is present)
```bash
python scripts/mimir.py "Design a fault-tolerant distributed cache with Redis and consistent hashing" --backend agy
```

##### Option C: OpenAI API
```bash
export OPENAI_API_KEY="sk-..."
python scripts/mimir.py "Optimal architecture for asynchronous background task workers" --backend openai --model gpt-4o-mini
```

##### Option D: Anthropic Claude API
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python scripts/mimir.py "Audit and stress-test custom consensus protocol against split-brain" --backend anthropic --model claude-3-5-haiku-20241022
```

##### Option E: Local Ollama / Offline
```bash
export OPENAI_BASE_URL="http://localhost:11434/v1"
python scripts/mimir.py "Analyze patterns for idempotent APIs" --backend openai --model qwen2.5:7b
```

---

### 🛠 CLI Parameters

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `goal` | `str` | *(required)* | Target objective, research query, or design challenge |
| `--backend` / `-b` | `str` | `auto` | Backend engine: `auto`, `codex`, `agy`, `openai`, `anthropic`, `ollama` |
| `--model` / `-m` | `str` | Auto | Model name tailored to the selected backend |
| `--output` / `-o` | `str` | `artifacts/mimir_solution.md` | Path for the generated markdown report |
| `--skip-web` | flag | `false` | Skip external omni-channel web scouting |
| `--depth` | `int` | `2` | Maximum decomposition depth for the task graph |
| `--sources` / `-s` | `str` | `None` | Comma-separated domain filter (e.g. `github.com,arxiv.org`) |
| `--no-jev` | flag | `false` | Disable JEV System-1 branch screening |

---

### 📁 Project Structure

```text
mimir/
├── SKILL.md                          # Antigravity & Agentic Assistant Skill definition
├── LEARNINGS.md                      # Persistent long-term memory bank & core heuristics
├── README.md                         # Bilingual documentation (English / Swedish)
├── requirements.txt                  # Minimal Python dependencies
├── prompts/
│   ├── MIMIR_SYSTEM_PROMPT.md        # System prompt for Claude, ChatGPT, Codex, Cursor
│   └── MIMIR_PORTING_PROMPT.md       # Meta-prompt for porting Mímir to other environments
└── scripts/
    ├── mimir.py                      # Main orchestrator & Rich terminal HUD
    ├── backend.py                    # Multi-backend engine (Codex, AGY, OpenAI, Claude, Ollama)
    ├── agy_swarm.py                  # Portable wrapper for agy CLI
    ├── task_graph.py                 # Kahn DAG, Blackboard, and EvidenceContract
    ├── jev_gate.py                   # System-1 JEV decision and screening gate
    ├── research_scout.py             # Omni-channel research scout (arXiv, GitHub, HackerNews)
    ├── jarvis_memory.py              # Cumulative memory management engine
    ├── gepa_optimizer.py             # Genetic-Pareto evolutionary reflection engine
    ├── swarm_runner.py               # Lightweight CLI task forwarder
    └── clean_backend_sessions.py     # Session cleanup utility
```

---

## 🇸🇪 Svenska

> *"Drick ur Mimers brunn. Sanningen är silad ur kosmos brus."*  
> *"Drink from the Well. Truth distilled from the noise of the cosmos."*

**M Í M I R** är en autonom multi-agent- och orakelsvärm för djup forskning, arkitekturdesign och komplex problemlösning, uppkallad efter asatrons visaste varelse. Mímir kombinerar uråldrig visdom med modern AI-ingenjörskonst för att självständigt reda ut och lösa svåra tekniska och strategiska utmaningar.

Systemet förenar dynamisk omvärldsspaning i realtid, Kahn-validerade acykliska uppgiftsgrafer (DAG), Joint Expected Value (JEV) System-1-beslutsgrindar, kryptografiska EvidenceContracts, adversariell Red-Team-granskning med genetisk Pareto-reflektion (GEPA) och ett beständigt kumulativt minne.

---

### 🌟 Kärnfunktioner & Innovationer

1. **Dynamisk Omni-Channel Världsspaning ([research_scout.py](file://./scripts/research_scout.py)):**
   Identifierar och söker automatiskt i relevanta primärkällor beroende på domän: GitHub (källkod), arXiv (forskning och matematik), HackerNews (post-mortems och produktionserfarenhet), samt öppna webben utan API-nycklar.
2. **Kahn-Validerad Rekursiv RLM DAG ([task_graph.py](file://./scripts/task_graph.py)):**
   Dekomponerar komplexa mål till atomära, icke-överlappande deluppgifter med strikt acyklisk validering och automatisk felkaskadering för att förhindra schemaläggnings-deadlocks.
3. **JEV System-1 Beslutsgrind ([jev_gate.py](file://./scripts/jev_gate.py)):**
   Matematisk grenbeskärning och snabb typad beslutsfattning baserad på Joint Expected Value:
   $$JEV = P(\text{impact}) \times \text{gain} - \text{cost}$$
   Beskär bort onödiga noder för att minimera latens och resursåtgång.
4. **Anti-Hallucination via EvidenceContracts:**
   Varje levererat delresultat förankras med kryptografiska SHA-256-hashar mot en delad **Blackboard**.
5. **Adversariell Red-Team Prövning & GEPA ([gepa_optimizer.py](file://./scripts/gepa_optimizer.py)):**
   Stresstestar lösningen mot en dedikerad motståndarkritiker (Red-Team) och muterar lösningen längs Pareto-fronten (härdighet kontra enkelhet).
6. **Kumulativt Långtidsminne ([LEARNINGS.md](file://./LEARNINGS.md)):**
   Sparar och läser in beprövade mönster, undvikna fallgropar och kärnheuristiker mellan körningar.
7. **Modulärt Multi-Backend Stöd ([backend.py](file://./scripts/backend.py)):**
   Körs sömlöst med:
   - **OpenAI Codex CLI (`codex`)** – Noll externa API-nycklar; körs via `codex exec` och ärver befintlig lokal Codex-autentisering och proxykonfiguration.
   - **Antigravity CLI (`agy`)** – Noll externa API-nycklar; ärver befintlig lokal autentisering och sandlåde-isolerar sessioner.
   - **OpenAI API & Kompatibla endpoints** (`gpt-4o-mini`, `gpt-4o`, samt Ollama, LMStudio, vLLM, OpenRouter).
   - **Anthropic Claude API** (`claude-3-5-haiku-20241022`, `claude-3-7-sonnet-20250219`).

---

### 🚀 Snabbstart & Installation

#### 1. Klona projektet
```bash
git clone https://github.com/begosh/mimir.git
cd mimir
```

#### 2. Installera beroenden
```bash
pip install -r requirements.txt
```
*(Kräver endast `rich`, `curl_cffi` och `beautifulsoup4`. Standardbiblioteket hanterar alla API- och processanrop utan tunga SDK-beroenden).*

#### 3. Kör Mímir

##### Alternativ A: OpenAI Codex CLI (Noll API-nycklar via lokal Codex-session)
```bash
python scripts/mimir.py "Designa en härdad distribuerad cache med Redis och konsistent hashing" --backend codex
```

##### Alternativ B: Antigravity CLI (Noll API-nycklar, standard om `agy` finns installerat)
```bash
python scripts/mimir.py "Designa en härdad distribuerad cache med Redis och konsistent hashing" --backend agy
```

##### Alternativ C: OpenAI API
```bash
export OPENAI_API_KEY="sk-..."
python scripts/mimir.py "Optimal arkitektur för asynkrona bakgrundsjobb" --backend openai --model gpt-4o-mini
```

##### Alternativ D: Anthropic Claude
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python scripts/mimir.py "Stresstesta protokollimplementering mot race conditions" --backend anthropic --model claude-3-5-haiku-20241022
```

##### Alternativ E: Lokal Ollama / Offline
```bash
export OPENAI_BASE_URL="http://localhost:11434/v1"
python scripts/mimir.py "Analysera mönster för idempotenta API:er" --backend openai --model qwen2.5:7b
```

---

### 🛠 CLI-Parametrar

| Flagga | Typ | Standard | Beskrivning |
| :--- | :--- | :--- | :--- |
| `goal` | `str` | *(obligatorisk)* | Målet, frågan eller optimeringsuppgiften |
| `--backend` / `-b` | `str` | `auto` | Backend: `auto`, `codex`, `agy`, `openai`, `anthropic`, `ollama` |
| `--model` / `-m` | `str` | Auto | Mikromodellnamn anpassat efter vald backend |
| `--output` / `-o` | `str` | `artifacts/mimir_solution.md` | Sökväg för genererad markdown-rapport |
| `--skip-web` | flagga | `false` | Hoppa över extern omvärldsspaning |
| `--depth` | `int` | `2` | Maximalt dekompositionsdjup i uppgiftsgrafen |
| `--sources` / `-s` | `str` | `None` | Kommaseparerad lista över prioriterade källdomäner |
| `--no-jev` | flagga | `false` | Inaktivera JEV System-1 grenbeskärning |

---

## 📜 Licens / License

MIT License. Fri att använda, anpassa och distribuera / Free to use, modify, and distribute.
