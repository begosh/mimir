# Optional JEV gating

Off by default. Use only when requested and optional branches create meaningful
cost. Score potential optional tasks *before* starting them; a separate scorer
agent is unnecessary unless explicitly budgeted.

Use the current Mimir formula:

```text
JEV = criticality * (1 - 0.5 * redundancy_penalty)
```

Each input is a finite number in [0,1], a model-estimated heuristic. Record
inputs, rationale, full-precision score and one threshold (default 0.30) in the
ledger. Never label them calibrated probabilities, measured expected utility or
measured information gain. Invalid scoring keeps the task unscored, not pruned.

Protect required evidence tasks **and all their dependency ancestors**. Exempt
roots, critics, mandatory verification and final synthesis. Protected/exempt
tasks receive no comparative score. Prune only optional tasks strictly below the
threshold. A user-requested deliverable is required even if the model considers
it redundant. Preserve the optional task and decision in the journal.

Rebuild and validate the prospective graph before applying pruning. If a removed
task's downstream consumer expected its *output*, the consumer cannot run as
though that output exists: mark it blocked or explicitly revise it to accept the
reduced scope, recording a gap. Rewiring to the removed task's prerequisites
preserves reachability but does not replace missing semantics. Apply all accepted
pruning decisions together after graph validation.

JEV never approves a factual claim or excuses a retrieval failure. A quick
coherence screen can mark a record for repair/review but cannot skip required
critique on model confidence.
