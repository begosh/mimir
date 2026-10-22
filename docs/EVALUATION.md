# Evaluate policy value

Use scripts/evaluate.py to run the same explicit local primary-source cases
through single/review policies. It saves each report/sidecar/checkpoint, per-call
usage and end-to-end time. Memory and public scouting are disabled; model,
context admission and per-worker deadlines match. All calls consume the selected
native provider allowance. Total token/dollar ceilings are not yet enforced.

Prepare a JSON list; preserve source snapshots separately:

```json
[{"id":"dependency-pin","goal":"Read /absolute/path/requirements-workers.txt and report its exact Codex SDK pin using primary evidence.","required_locators":["/absolute/path/requirements-workers.txt:3"],"required_answer_markers":["0.163.0"]}]
```

```powershell
.venv/Scripts/python.exe scripts/evaluate.py --cases artifacts/eval-cases.json --output artifacts/eval-new-run --backend codex --model <agreed-model> --effort low --repeats 3
```

The output directory must be new. Mode order alternates across repetitions.
Failed runs remain in results; report locator/answer-marker presence is a bounded
mechanical check, not citation entailment or independent factual verification.
Tool access may differ at runtime despite equal configuration; inspect gaps.

Use held-out cases with known architectural defects, conflicting evidence,
stale sources and unavailable required retrieval. Have reviewers score anonymized
answers for source entailment, unsupported material claims, omissions, defect
severity and actionable recommendations. Keep those scores separate from model
support labels. Predeclare useful quality/cost thresholds before adopting added
orchestration. Small pilots cannot prove universal superiority or precise p95.

Compare reflection with its input and inspect newly introduced claims. Test JEV
only on graphs with truly optional dependent work; score net savings and omissions.
Test uneven scheduling and process/cancellation failures separately from quality.
Keep runtime reuse, recursive planning and larger swarms conditional on measured
benefits while preserving evidence and cleanup contracts.
