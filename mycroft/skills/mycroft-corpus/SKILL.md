---
name: mycroft-corpus
description: Analyze a large supplied document corpus with indexed source spans, bounded native subagent slices and recursive question reduction while preserving revisions, conflicts and retrieval gaps.
metadata:
  package-version: "0.1.0"
---

# Mycroft corpus investigator

Use native subagents and the Mycroft coordinator protocol for bounded analysis
of explicitly supplied or authorized captured evidence. This is an RLM-inspired
delegation workflow; no Python interpreter, executable RLM or model API bridge.

Read the installed `mycroft` skill and its `references/CORPUS.md`,
`references/ORCHESTRATION.md` and `references/CONTRACTS.md`. These three skills
are distributed together. Resolve `mycroft` as the sibling skill directory;
if missing, report an incomplete installation instead of inventing its policy.

Index the corpus before analysis. Record exact source identities and read/search
coverage. Delegate source-bounded questions to `mycroft-corpus-worker` or a
generic native agent given that role prompt. The host grants every recursion
request against the same task/dispatch/depth budget; default children never spawn
grandchildren. Search hits guide bounded reads, and untouched spans remain
untouched in the coverage record. Merge claim/source graphs rather than stripping
provenance into summaries. Reopen evidence needed for consequential conclusions.
