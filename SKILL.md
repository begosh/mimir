---
name: mimir
description: "M Í M I R // The Omniscient Oracle & Autonomous Swarm. Deep knowledge retrieval, recursive DAG reasoning, JEV decision gating, and cumulative memory across all domains (Bilingual SV/EN)."
---

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
7. **Multi-Backend Stöd:** Körs sömlöst med Antigravity CLI (`agy`), OpenAI API (`gpt-4o-mini`, m.fl.), Anthropic Claude API (`claude-3-5-haiku`, `claude-3-7-sonnet`) eller lokala modeller via Ollama/vLLM.
8. **Tvåspråkig Persona (SV / EN):** Talar med lugn, auktoritär skärpa på både svenska och engelska.

---

## Arkitektur & Flöde

```text
[Mål / Användarfråga]
         │
         ├────────► [Laddar tidigare visdom från LEARNINGS.md]
         ▼
[Fas 1: Mímir's Scryer] ──────► Dynamisk källspaning (GitHub, Docs, ArXiv, m.m.)
         │
         ▼
[Fas 2: Mimisbrunns DAG] ─────► Rekursiv nedbrytning + JEV-beskärning
         │
         ▼
[Fas 3: Runornas Svärm] ──────► Parallella mikroagenter + EvidenceContracts
         │
         ▼
[Fas 4: Mimers Råd] ──────────► Red-team motståndarkritik & GEPA Pareto-mutation
         │
         ▼
[Fas 5: Mimers Ord] ──────────► Sparar härdad sanning + Uppdaterar LEARNINGS.md
```

---

## Snabbstart i Terminalen

### 1. Kör med Mímir CLI
```bash
# Kör via automatisk motoridentifiering:
python scripts/mimir.py "Vilken fråga som helst på svenska eller engelska"
```

### 2. Val av Backend & Modell
```bash
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

### 3. Flaggor & Anpassning
- `--output / -o`: Sökväg för rapporten (sparar både `.md` och `.json`). Standard: `artifacts/<namn>.md` i aktuell arbetskatalog.
- `--backend / -b`: Val av motor (`auto`, `agy`, `openai`, `anthropic`, `ollama`).
- `--model / -m`: Val av mikromodell (t.ex. `gemini-3.8-flash-low`, `gpt-4o-mini`, `claude-3-5-haiku-20241022`).
- `--sources / -s`: Styr sökningen mot specifika källor (t.ex. `--sources github.com,news.ycombinator.com`).
- `--skip-web`: Hoppar över omvärldsbevakning om du vill köra offline.
- `--no-jev`: Inaktiverar JEV-beskärning och System 1-screening.
- `--depth`: Maximalt rekursionsdjup för dekomponering (standard: `2`).

---

## Filöversikt

- [LEARNINGS.md](file://./LEARNINGS.md) – Mimers beständiga minnesbank över alla körningar.
- [scripts/mimir.py](file://./scripts/mimir.py) – Huvudorkestrator med terminal-HUD och Mímir-persona.
- [scripts/backend.py](file://./scripts/backend.py) – Universell LLM-backend (AGY, OpenAI, Anthropic, Ollama).
- [scripts/jev_gate.py](file://./scripts/jev_gate.py) – System 1 Decision Gate, kalibrerad evidensgranskning och JEV-pruning.
- [scripts/task_graph.py](file://./scripts/task_graph.py) – Kahn DAG-dekomposition, Blackboard och `EvidenceContract`.
- [scripts/research_scout.py](file://./scripts/research_scout.py) – Käll-agnostisk omni-channel omvärldsspaning.
- [scripts/jarvis_memory.py](file://./scripts/jarvis_memory.py) – Minneshanterare för inläsning och konsolidering.
- [scripts/gepa_optimizer.py](file://./scripts/gepa_optimizer.py) – GEPA Pareto-reflektionsmotor.
- [prompts/MIMIR_SYSTEM_PROMPT.md](file://./prompts/MIMIR_SYSTEM_PROMPT.md) – Portabel systemprompt för Claude, ChatGPT, Codex och Cursor.
- [prompts/MIMIR_PORTING_PROMPT.md](file://./prompts/MIMIR_PORTING_PROMPT.md) – Meta-prompt för att bygga en egen Mímir i andra miljöer.
