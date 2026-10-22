# DSPy/RLM investigator operation

Mimir supports native research, typed DSPy prediction, and DSPy RLM over explicitly
captured evidence. Task topology remains `single`, `review`, or `swarm`. Critics
and final synthesis retain Mimir's native workflow. Upstream GEPA training is a
separate job; the existing reflective synthesis stage is not that optimizer.

## Install

The qualified environment is Python 3.14.2 on Windows, DSPy 3.4.1, GEPA 0.1.4,
Deno 2.9.8, pywin32 312, and native openai-codex 0.163.0. Install the optional
dependencies separately to preserve the normal worker environment:

```powershell
python -m venv .venv-research
.\.venv-research\Scripts\python.exe -m pip install -r requirements-research.txt
.\.venv\Scripts\python.exe scripts/mimir.py --diagnostics --backend codex
```

The engine selects the workspace `.venv-research` or explicit
`MIMIR_RESEARCH_PYTHON`, then its own interpreter. The installer `--research`
(PowerShell `-Research`) installs the optional dependencies into its interpreter.
The DSPy child receives no credential environment variables. Native SDK clients
remain in the parent event loop and inherit the existing provider/login route.
No API billing fallback is configured. Other native adapters remain supported
for ordinary research; DSPy/RLM currently reject unqualified adapters.

Deno/Pyodide may download its runtime on first use. Prewarm in the research
environment before offline operation:

```powershell
.\.venv-research\Scripts\python.exe -c "import dspy; p=dspy.PythonInterpreter(); print(p.execute('42')); p.shutdown()"
```

## Captured sources and research

Create a JSON source manifest. Local files must be UTF-8. HTTPS capture needs an
explicit domain allowlist, permits GET only, and rejects redirects. Raw retrieved
content is evidence; parsing a page does not establish its authority or entailment.

```json
{
  "allowed_domains": ["raw.githubusercontent.com"],
  "sources": [
    {"id": "architecture", "path": "architecture.md"},
    {"id": "upstream", "url": "https://raw.githubusercontent.com/stanfordnlp/dspy/3.4.1/dspy/predict/rlm.py"}
  ]
}
```

Capture records retain original locator, actual retrieval time/type, content
digest of normalized UTF-8 text and text. The digest is not the original file's
raw-byte hash when encoding/newlines differ. Each source is bounded at 20 MB; initialization is bounded by
a 4 MB IPC frame. RLM handles corpora larger than root prompt admission within
that initialization limit. Its approved callbacks list metadata, read spans up
to 16000 characters and search literal matches. Generated code cannot choose
arbitrary paths, network access, environment variables or processes. For internal
M365 research, use the native investigator's approved tools or first capture
explicitly authorized source artifacts; captured-corpus mode has no Work IQ bridge.

```powershell
.\.venv\Scripts\python.exe scripts/mimir.py "Investigate the supplied architecture and retain source-linked claims and gaps" --backend codex --model gpt-6.1-sol --effort low --mode review --research-program rlm --source-manifest sources.json --skip-web --state-file artifacts/rlm-state.json --output artifacts/rlm-report.md
```

MCP `start_run` accepts the same `research_program`, `source_manifest`,
`research_budget`, and `program_manifest` controls. Reconnect an existing MCP
session to load the revised tool schema. Phases reuse those settings.

Default RLM limits: 64 native attempts for the whole run, 1800 wall-clock seconds
from planning, nested depth 1, 6 iterations, 8 subcalls per RLM, 4 simultaneous
interpreters across investigators, and 16000 output characters. `research_budget`
is a JSON object using `max_attempts`, `max_seconds`, `max_depth`, `max_iters`,
`max_subcalls`, `max_interpreters`, `max_output_chars`, `max_reported_tokens`.
Review reserves calls for critique/synthesis; swarm reserves synthesis. Model
and effort are fixed. Reported token stopping can overshoot by a native turn;
token breakdown and billed cost remain unavailable.

Nested `dspy.Predict` and `dspy.RLM` accept a signature without constructor
overrides. The trusted facade injects runtime policy. Attempts and interpreter
leases are checked by the parent broker, including parallel subqueries.
Windows kill-on-close jobs own the child and its Deno descendants with 512 MB
per-process limits. POSIX uses process groups; equivalent memory-limit qualification
has not been performed. Denied policies, failed required subcalls, cancellation
and invalid citations cannot become a successful report through extraction.

DSPy system/signature instructions become native developer instructions. Native
shell, MCP, apps, delegation and discovery capabilities are disabled per process.
Any observed native tool item rejects the completion. Read-only sandbox denies
filesystem writes. Basic native utility tools may remain advertised by the native
model catalog; the bridge does not claim an empty tool catalog.

Completed task results are reused only after input/output identity checks. Sources,
instructions, implementation and dependency policy are frozen at planning. Local
source drift rejects resume; remote snapshots are reused without invisible refetch.
Interrupted analysis restarts from frozen sources, charging repeated calls.
Attempts admitted before dispatch survive crashes as interrupted entries. The
deadline includes time between phases. Interpreter memory is not resumed.
Failed and successful traces remain beneath the checkpoint's research directory.
These private source/code traces are local artifacts, not chat progress.

Citation checks establish captured membership, retrieval record identity and exact
excerpt presence. They do not verify claim entailment, completeness or truth.

## Explicit GEPA training and evaluation

Datasets have nonempty `train`, `dev`, `held_out` arrays. Each example contains
string `group`, `objective`, `evidence`, and `expected`; source/topic groups must
be disjoint between splits. The provided generator creates 12/6/6 **synthetic**
engineering cases for revisions, distractors, missing facts, conflicts, injection
and scattered records. Production evaluation needs representative reviewed data.

```powershell
.\.venv-research\Scripts\python.exe scripts/build_research_fixtures.py --output artifacts/dataset.json
.\.venv-research\Scripts\python.exe scripts/optimize_program.py --program rlm --dataset artifacts/dataset.json --output artifacts/candidate.json --model gpt-6.1-sol --max-metric-calls 24
.\.venv-research\Scripts\python.exe scripts/evaluate_research.py --dataset artifacts/dataset.json --candidate artifacts/candidate.json --output artifacts/comparison.json --model gpt-6.1-sol
```

GEPA optimizes typed investigator or RLM action/extraction instructions through
the same native engine. Executable code evolution, tracking and automatic
promotion are disabled. Training sends only train/dev to the child; sealed
evaluation sends no expected answers. Both meter native calls and preserve
failure traces and dataset identities. GEPA metric-call limits differ from native
attempt limits and can finish an in-progress scoring batch beyond the estimate.

The exact-answer metric is an engineering check. Human review of source support,
failure/injection behavior, relevance and budgets remains necessary. A candidate
can equal the original; optimization does not guarantee better quality or speed.
After reviewing a successful non-regressing sealed comparison, explicitly create
a reviewed manifest:

```powershell
.\.venv-research\Scripts\python.exe scripts/review_program.py --candidate artifacts/candidate.json --evaluation artifacts/comparison.json --output artifacts/reviewed.json --review-note "Record the actual review and intended scope here"
```

Select that manifest with `program_manifest` in a **new** research run. Unreviewed
or altered manifests fail admission. Omit it in a new run to roll back to locked
default instructions. Manifests contain data only; no pickle, credentials, import
paths or budget/tool overrides. Learning candidates remain separate from both
optimization artifacts and curated `.mimir/LEARNINGS.md`.
