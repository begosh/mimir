# M Í M I R // The Omniscient Oracle & Autonomous Swarm

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Bilingual: SV/EN](https://img.shields.io/badge/Bilingual-SV%20%2F%20EN-gold.svg)](#)

> *"Drick ur Mimers brunn. Sanningen är silad ur kosmos brus."*  
> *"Drink from the Well. Truth distilled from the noise of the cosmos."*

**M Í M I R** är en autonom multi-agent- och orakelsvärm för djup forskning, arkitekturdesign och komplex problemlösning. Mímir kombinerar dynamisk omvärldsspaning, Kahn-validerade acykliska uppgiftsgrafer (DAG), Joint Expected Value (JEV) System-1-beslutsgrindar, kryptografiska EvidenceContracts och genetisk Pareto-reflektion (GEPA).

---

## 🌟 Kärnfunktioner & Innovationer

1. **Dynamisk Omni-Channel Världsspaning ([research_scout.py](file://./scripts/research_scout.py)):**
   Identifierar och söker automatiskt i relevanta primärkällor beroende på domän: GitHub (källkod), arXiv (forskning/matematik), HackerNews (post-mortems och erfarenhet), samt öppna webben utan API-nycklar.
2. **Kahn-Validerad Rekursiv RLM DAG ([task_graph.py](file://./scripts/task_graph.py)):**
   Dekomponerar komplexa mål till atomära, icke-överlappande deluppgifter med strikt acyklisk validering och automatisk felkaskadering för att förhindra schemaläggnings-deadlocks.
3. **JEV System-1 Beslutsgrind ([jev_gate.py](file://./scripts/jev_gate.py)):**
   Matematisk grenbeskärning och snabb typad beslutsfattning baserad på Joint Expected Value ($JEV = P(\text{impact}) \times \text{gain} - \text{cost}$). Beskär bort onödiga noder för att minimera latens och kostnad.
4. **Anti-Hallucination via EvidenceContracts:**
   Varje levererat delresultat förankras med kryptografiska SHA-256-hashar mot en delad **Blackboard**.
5. **Adversariell Red-Team Prövning & GEPA ([gepa_optimizer.py](file://./scripts/gepa_optimizer.py)):**
   Stresstestar lösningen mot en dedikerad motståndarkritiker (Red-Team) och muterar lösningen längs Pareto-fronten (härdighet vs. enkelhet).
6. **Kumulativt Långtidsminne ([LEARNINGS.md](file://./LEARNINGS.md)):**
   Sparar och läser in beprövade mönster, undvikna fallgropar och kärnheuristiker mellan körningar.
7. **Modulärt Multi-Backend Stöd ([backend.py](file://./scripts/backend.py)):**
   Körs sömlöst med:
   - **Antigravity CLI (`agy`)** – Noll externa API-nycklar, ärver befintlig lokal autentisering och sandlåde-isolerar sessioner.
   - **OpenAI API & Kompatibla endpoints** (`gpt-4o-mini`, `gpt-4o`, samt Ollama, LMStudio, vLLM, OpenRouter).
   - **Anthropic Claude API** (`claude-3-5-haiku-20241022`, `claude-3-7-sonnet-20250219`).

---

## 🚀 Snabbstart & Installation

### 1. Klona eller ladda ned paketet
```bash
git clone https://github.com/your-username/mimir.git
cd mimir
```

### 2. Installera beroenden
```bash
pip install -r requirements.txt
```
*(Kräver endast `rich`, `curl_cffi` och `beautifulsoup4`. Standardbiblioteket hanterar alla API-anrop utan tunga SDK:er).*

### 3. Kör Mímir

#### Alternativ A: Antigravity CLI (Standard om `agy` finns installerat)
```bash
python scripts/mimir.py "Designa en härdad distribuerad cache med Redis och konsistent hashing"
```

#### Alternativ B: OpenAI API
```bash
export OPENAI_API_KEY="sk-..."
python scripts/mimir.py "Optimal arkitektur för asynkrona bakgrundsjobb" --backend openai --model gpt-4o-mini
```

#### Alternativ C: Anthropic Claude
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python scripts/mimir.py "Stresstesta protokollimplementering mot race conditions" --backend anthropic --model claude-3-5-haiku-20241022
```

#### Alternativ D: Lokal Ollama / Offline
```bash
export OPENAI_BASE_URL="http://localhost:11434/v1"
python scripts/mimir.py "Analysera mönster för idempotenta API:er" --backend openai --model qwen2.5:7b
```

---

## 🛠 CLI-Parametrar

| Flagga | Typ | Standard | Beskrivning |
| :--- | :--- | :--- | :--- |
| `goal` | `str` | *(obligatorisk)* | Målet, frågan eller optimeringsuppgiften |
| `--backend` / `-b` | `str` | `auto` | Backend: `auto`, `agy`, `openai`, `anthropic`, `ollama` |
| `--model` / `-m` | `str` | Auto | Mikromodellnamn anpassat efter backend |
| `--output` / `-o` | `str` | `artifacts/mimir_solution.md` | Sökväg för genererad markdown-rapport |
| `--skip-web` | flagga | `false` | Hoppa över extern omvärldsspaning |
| `--depth` | `int` | `2` | Maximalt dekompositionsdjup i uppgiftsgrafen |
| `--sources` / `-s` | `str` | `None` | Kommaseparerad lista över prioriterade källdomäner |
| `--no-jev` | flagga | `false` | Inaktivera JEV System-1 grenbeskärning |

---

## 📁 Projektstruktur

```text
mimir/
├── SKILL.md                          # Antigravity & Agentic Assistant Skill-definition
├── LEARNINGS.md                      # Beständigt långtidsminne & kärnheuristiker
├── README.md                         # Denna dokumentation
├── requirements.txt                  # Minimala Python-beroenden
├── prompts/
│   ├── MIMIR_SYSTEM_PROMPT.md        # Klar systemprompt för Claude, ChatGPT, Codex, Cursor
│   └── MIMIR_PORTING_PROMPT.md       # Meta-prompt för att bygga/anpassa Mímir i andra AI-miljöer
└── scripts/
    ├── mimir.py                      # Huvudorkestrator & Rich Console UI
    ├── backend.py                    # Universell multi-backend motor (AGY, OpenAI, Claude, Ollama)
    ├── agy_swarm.py                  # Portabel wrapper för agy CLI
    ├── task_graph.py                 # Kahn DAG, Blackboard, EvidenceContract
    ├── jev_gate.py                   # System-1 JEV-besluts- och screeningsmotor
    ├── research_scout.py             # Omni-channel källspaning (arXiv, GitHub, m.fl.)
    ├── jarvis_memory.py              # Kumulativ minnesmotor
    ├── gepa_optimizer.py             # Genetic-Pareto reflektions- och mutationsmotor
    ├── swarm_runner.py               # Enkel CLI forwarder
    └── clean_backend_sessions.py     # Städverktyg för efemära backend-sessioner
```

---

## 📜 Licens

MIT License. Fri att använda, anpassa och distribuera.
