# Mímir — project guidance

Standing project guidance only. Generated development-run notes were removed
during workspace cleanup. Check applicability against current code and evidence;
these guidelines are not independent validation. New run candidates remain
separate from curated guidance and require explicit review before promotion.

## 1. Core heuristics
- **Evidence Contracts:** Preserve source and test provenance. Hashes identify outputs; they do not establish truth or citation entailment.
- **Kahn DAG Integrity:** Validate acyclic structure at runtime using Kahn's algorithm to guarantee dynamic subtasks never deadlock the scheduler.
- **Prompt-as-a-Variable:** Never flood raw context between models; use versioned Blackboard deltas.
- **Source-Agnostic Scouting:** Select information channels dynamically based on domain (GitHub/RFCs for code, arXiv/PubMed for scientific research, official specs for protocols).
- **JEV Branch Pruning:** Optional and off by default. Protect required evidence and dependencies when explicitly enabled.
- **Critique and GEPA:** Use a critic for consequential reviews. Upstream GEPA instruction training is a separate, explicitly requested evaluation job; critique is not equivalent to optimization.

## 2. Red-Team Pitfalls & Mitigations (Anti-Patterns)
- **Overconfidence Trap:** Micro-models often report high confidence despite logical flaws. Never trust self-assessed confidence without independent contract verification.
- **Deadlock via Unhandled Errors:** If an upstream node crashes, dependent subtasks must cascade to `CANCELLED` immediately to prevent thread locking.
- **Context Pollution:** Never pipe entire conversation histories to micro-workers. Isolate execution to strictly typed input variables.
- **TTL Drift & Race Conditions:** In asynchronous distributed execution, locks and leases must be renewed actively to prevent split-brain.
