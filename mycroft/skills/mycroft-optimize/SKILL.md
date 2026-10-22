---
name: mycroft-optimize
description: Run an explicitly requested, bounded instruction optimization experiment using native evaluator and evolver agents, source-grouped train/dev/held-out splits, trace feedback and reviewed candidate selection.
metadata:
  package-version: "0.1.0"
---

# Mycroft instruction optimization

Apply only when the user requests instruction training, evaluation or selection.
An ordinary research request does not authorize optimization or activation.
This workflow adapts GEPA's reflective proposal and Pareto selection ideas; it
does not invoke upstream GEPA or DSPy.

Read the installed sibling `mycroft` skill and its
`references/OPTIMIZATION.md`, `references/ORCHESTRATION.md` and
`references/CONTRACTS.md`. Report an incomplete installation if unavailable.
Use native subagents, keeping tools, provider, model, permissions and budgets
fixed. Proposal agents see train/dev failures only. Held-out expected answers
never enter investigator or evolver inputs. Outputs and rubric judgments are
separate artifacts. Model judgments stay labeled estimates.

Default experimental cap: one proposal generation, baseline plus one candidate,
eight logical tasks, 12 dispatches total, two concurrent workers, with evaluation/critique reserved
before proposals. Run the complete affordable comparison or narrow the dataset
explicitly before starting; never call an unfinished comparison an improvement.
Selection requires completed comparable evaluation and explicit reviewed
activation. Training itself writes candidates only.
