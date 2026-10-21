---
name: mimir
description: "M Í M I R // The Omniscient Oracle & Autonomous Swarm. Deep knowledge retrieval, recursive DAG reasoning, JEV decision gating, and cumulative memory across all domains (Bilingual EN/SV)."
---

# M Í M I R // Keeper of Wisdom & Autonomous Swarm

> [English](#english) | [Svenska](#svenska)

---

## English

> *"Drink from the Well. Truth distilled from the noise of the cosmos."*  
> *"Drick ur Mimers brunn. Sanningen är silad ur kosmos brus."*

This skill equips your AI assistant with **M Í M I R** — the omniscient oracle swarm named after the wisest being in Norse mythology. Mímir unites ancient wisdom with modern AI engineering to autonomously deconstruct, investigate, and solve complex problems:

1. **Omni-Channel Sensor Array ([research_scout.py](file://./scripts/research_scout.py)):** Dynamically searches authoritative venues (arXiv, GitHub, RFCs, HackerNews, or the open web) without external API keys.
2. **Kahn-Validated Recursive RLM DAG ([task_graph.py](file://./scripts/task_graph.py)):** Decomposes targets into atomic subtasks with guaranteed topological acyclicity and deadlock elimination.
3. **JEV System-1 Decision Gate ([jev_gate.py](file://./scripts/jev_gate.py)):** Rapid typed decision-making and mathematical branch pruning via Joint Expected Value ($JEV = P(\text{impact}) \times \text{gain} - \text{cost}$).
4. **Anti-Hallucination via EvidenceContracts:** Grounded conclusions anchored by SHA-256 hashes against a shared **Blackboard**.
5. **Adversarial Red-Team & GEPA ([gepa_optimizer.py](file://./scripts/gepa_optimizer.py)):** Stress-tests solutions against adversarial critiques and mutates along the Pareto frontier (robustness vs. simplicity).
6. **Cumulative Long-Term Memory ([LEARNINGS.md](file://./LEARNINGS.md)):** Persistent knowledge repository loaded at startup and augmented with every run.
7. **Modular Multi-Backend Support ([backend.py](file://./scripts/backend.py)):** Seamless execution across **OpenAI Codex CLI (`codex`)**, **Antigravity CLI (`agy`)**, **OpenAI API** (`gpt-4o-mini`, etc.), **Anthropic Claude API** (`claude-3-5-haiku`, `claude-3-7-sonnet`), and local **Ollama** / vLLM. No API keys needed when using `codex` or `agy`.
8. **Bilingual Persona (EN / SV):** Operates with stoic, authoritative precision in both English and Swedish.

---

### Terminal Quickstart

```bash
# Auto-detect best available backend (Codex, AGY, OpenAI, Claude):
python scripts/mimir.py "Any complex engineering, research, or architecture query"

# Run via OpenAI Codex CLI (zero API keys, local session):
python scripts/mimir.py "Design a fault-tolerant distributed queue" --backend codex

# Run via Antigravity CLI:
python scripts/mimir.py "Design a fault-tolerant distributed queue" --backend agy

# Run via OpenAI API:
export OPENAI_API_KEY="sk-..."
python scripts/mimir.py "Optimize hybrid vector-keyword search" --backend openai --model gpt-4o-mini

# Run via Anthropic Claude:
export ANTHROPIC_API_KEY="sk-ant-..."
python scripts/mimir.py "Audit consensus protocol security" --backend anthropic --model claude-3-5-haiku-20241022

# Run via Local Ollama:
export OPENAI_BASE_URL="http://localhost:11434/v1"
python scripts/mimir.py "Analyze local logs" --backend openai --model qwen2.5:7b
```

---

## Svenska

# M Í M I R // Vishetens Väktare & Autonom Svärm

> *"Drick ur Mimers brunn. Sanningen är silad ur kosmos brus."*  
> *"Drink from the Well. Truth distilled from the noise of the cosmos."*

Denna skill förvandlar din AI-assistent till **M Í M I R** – den allvetande orakelsvärmen uppkallad efter den nordiska mytologins visaste varelse. Mímir kombinerar uråldrig visdom med modern AI-ingenjörskonst för att autonomt reda ut och lösa vilken komplex fråga som helst:

1. **Mímirs Världsspaning (Omni-Channel Sensor Array):** Söker dynamiskt genom forskningsarkiv (arXiv), källkods-repos (GitHub), officiella specifikationer, branschforum (HackerNews) eller öppna nätet via TLS-säkrade förfrågningar utan externa API-nycklar.
2. **Kahn-Validerad Rekursiv RLM DAG:** Bryter ned målet till atomära uppgifter med garanterad referensintegritet och automatisk deadlock-eliminering.
3. **JEV System-1 Beslutsgrind:** Blixtsnabba, hårt typade beslut och matematisk grenbeskärning via Joint Expected Value (JEV) som minimerar onödig exekveringstid och kostnad.
4. **Anti-Hallucination via EvidenceContracts:** Alla slutsatser förankras med kryptografiska SHA256-hashar mot en delad **Blackboard**.
5. **Adversariell Red-Team Prövning & GEPA:** Stresstestar och härdar visdomen mot motståndarkritik, kantfall och race conditions via Genetic-Pareto Reflektion.
6. **Långtidsminne ([LEARNINGS.md](file://./LEARNINGS.md)):** Bygger en kumulativ minnesbank som läses in vid start och växer för varje uppdrag.
7. **Multi-Backend Stöd:** Körs sömlöst med OpenAI Codex CLI (`codex`), Antigravity CLI (`agy`), OpenAI API (`gpt-4o-mini`, m.fl.), Anthropic Claude API (`claude-3-5-haiku`, `claude-3-7-sonnet`) eller lokala modeller via Ollama/vLLM. Inga API-nycklar behövs vid användning av `codex` eller `agy`.
8. **Tvåspråkig Persona (SV / EN):** Talar med lugn, auktoritär skärpa på både svenska och engelska.

---

### Snabbstart i Terminalen

```bash
# Kör via automatisk motoridentifiering:
python scripts/mimir.py "Vilken fråga som helst på svenska eller engelska"

# Kör med OpenAI Codex CLI (noll API-nycklar, använder lokal Codex-inloggning):
python scripts/mimir.py "Designa ett feltolerant distribuerat kösystem" --backend codex

# Kör med Antigravity (standard om agy är installerat):
python scripts/mimir.py "Designa ett feltolerant distribuerat kösystem" --backend agy

# Kör med OpenAI API (eller kompatibel endpoint):
export OPENAI_API_KEY="sk-..."
python scripts/mimir.py "Optimera en hybrid sökalgoritm" --backend openai --model gpt-4o-mini

# Kör med Anthropic Claude:
export ANTHROPIC_API_KEY="sk-ant-..."
python scripts/mimir.py "Granska protokollsäkerhet" --backend anthropic --model claude-3-5-haiku-20241022

# Kör med lokal Ollama:
export OPENAI_BASE_URL="http://localhost:11434/v1"
python scripts/mimir.py "Analysera lokal data" --backend openai --model qwen2.5:7b
```

---

### Flaggor & Anpassning
- `--output / -o`: Sökväg för rapporten (sparar både `.md` och `.json`). Standard: `artifacts/<namn>.md` i aktuell arbetskatalog.
- `--backend / -b`: Val av motor (`auto`, `codex`, `agy`, `openai`, `anthropic`, `ollama`).
- `--model / -m`: Val av mikromodell (t.ex. `gpt-4o-mini`, `gemini-3.8-flash-low`, `claude-3-5-haiku-20241022`).
- `--sources / -s`: Styr sökningen mot specifika källor (t.ex. `--sources github.com,news.ycombinator.com`).
- `--skip-web`: Hoppar över omvärldsbevakning om du vill köra offline.
- `--no-jev`: Inaktiverar JEV-beskärning och System 1-screening.
- `--depth`: Maximalt rekursionsdjup för dekomponering (standard: `2`).

---

## Filöversikt / File Index

- [LEARNINGS.md](file://./LEARNINGS.md) – Mimers beständiga minnesbank över alla körningar / Persistent memory bank across all runs.
- [scripts/mimir.py](file://./scripts/mimir.py) – Huvudorkestrator med terminal-HUD och Mímir-persona / Main orchestrator and terminal HUD.
- [scripts/backend.py](file://./scripts/backend.py) – Universell LLM-backend (Codex, AGY, OpenAI, Anthropic, Ollama).
- [scripts/jev_gate.py](file://./scripts/jev_gate.py) – System 1 Decision Gate, kalibrerad evidensgranskning och JEV-pruning.
- [scripts/task_graph.py](file://./scripts/task_graph.py) – Kahn DAG-dekomposition, Blackboard och `EvidenceContract`.
- [scripts/research_scout.py](file://./scripts/research_scout.py) – Käll-agnostisk omni-channel omvärldsspaning / Omni-channel research scout.
- [scripts/jarvis_memory.py](file://./scripts/jarvis_memory.py) – Minneshanterare för inläsning och konsolidering / Memory manager.
- [scripts/gepa_optimizer.py](file://./scripts/gepa_optimizer.py) – GEPA Pareto-reflektionsmotor / Pareto reflection engine.
- [prompts/MIMIR_SYSTEM_PROMPT.md](file://./prompts/MIMIR_SYSTEM_PROMPT.md) – Portabel systemprompt för Claude, ChatGPT, Codex och Cursor.
- [prompts/MIMIR_PORTING_PROMPT.md](file://./prompts/MIMIR_PORTING_PROMPT.md) – Meta-prompt för att bygga en egen Mímir i andra miljöer.
