# Evidence and typed module contracts

Use a fixed interface in place of a DSPy Signature:

```text
Investigate(objective, constraints, source_scope, dependencies, budget)
  -> WorkerRecord
Critique(objective, WorkerRecord[], source_scope)
  -> WorkerRecord with issues
Propose(instruction_text, train_dev_feedback, immutable_policy)
  -> instruction_candidate
Evaluate(objective, evidence, instruction_candidate)
  -> WorkerRecord (expected answer withheld)
```

Investigators see only admitted inputs. These are prompt-level interfaces;
structured-output or deterministic schema validation is used when available.
Do not claim a DSPy compiler, calibrated confidence or deterministic reasoning.

## WorkerRecord

See `assets/worker.schema.json` for machine-readable structure. Return one JSON
object, without fenced commentary. Keep the answer, rationales and excerpts
concise; avoid repeating the same finding in every field. The complete returned
JSON, including formatting, must fit the assigned output bound. Aim below the
bound rather than relying on host compaction to make an oversized return valid.
If all required evidence cannot fit, narrow the answer visibly and request a
separate bounded record; do not silently omit material support. Required fields:

| Field | Meaning |
| --- | --- |
| schema_version | `mycroft.worker.v1` |
| run_id / task_id / attempt | Identity assigned by host; attempt starts at 1 |
| status | `succeeded`, `partial` or `failed`; describe failures in gaps |
| answer | Concise answer within assigned scope; retain qualifications |
| sources | Actual retrieved records with run-scoped IDs |
| claims | Source-linked assertions and their reported support |
| gaps | Missing permissions, missing evidence, conflicting versions or omitted scope |
| requests | Bounded requests for further host-mediated analysis |
| issues | Critic findings; empty for ordinary investigators |
| coverage | Scopes searched/read and explicitly unread scopes |

Source fields: `id`, `locator`, `retrieval_type`, `retrieved_at`, `excerpt`,
`span`, `identity`. Prefix newly created source IDs with `<task_id>:`; dependency
sources retain their existing IDs and are included in the returned record if
referenced. No unrelated namespace or ID reuse for different content. Use
`local_file`, `primary_document`, `web_page`, `search_snippet`, `abstract` or
`worker_report`. Capture format does not change evidence semantics: a snippet
saved in a local Markdown file remains `search_snippet` for its underlying
assertion. A local read proves the artifact text, not the snippet's claim. Use
separate source IDs for distinct spans/retrievals, such as
`t-evidence:a1:operations:lines-5-7`; preserve exact frozen records when reusing
an ID across attempts. Retrieval time is actual ISO 8601 with timezone, or `null`
plus a gap if unavailable. `identity` is a measured content digest or a retained
snapshot locator, or `null` when unknown. Hashes establish identity only. A span
names actual lines, page, byte/character range or section; never invented lines.
Excerpt is exact retrieved text, not a paraphrase in quotation marks.

Claim fields: `id`, `text`, `source_ids`, `support_status`, `rationale`.
Claim IDs may be local (`readiness`) or already scoped
(`t-evidence:readiness`); when combining/referring to them prefix the owning task
exactly once. Never duplicate the task prefix or change immutable claim IDs.
Status is `supported`, `inference`, `contradicted` or `unsupported`. All claims
except unsupported need resolvable source links. `supported` means the worker's
reported assessment. Discovery evidence alone cannot support a material fact;
fetch the underlying source. If one source is a primary retrieval and another
is a snippet, explain exactly which passage supplies support. Preserve separate
revision identities and conflicting assertions; do not average them into truth.

Request fields: `question`, `source_scope`, `reason`, `stop_condition`. These are
requests to the host, not tools or authorization to spawn. An empty list means
no request, not complete research. Do not request more work for routine polish.

Issue fields: `claim_ids`, `severity` (`material` or `minor`), `description`,
`source_ids`, `remedy`. Claim IDs are `<task_id>:<claim-id>` when reviewing other
tasks. Critic issues need evidence or a precise missing-evidence explanation;
an issue need not invent a source for an absent fact. Model agreement is not
independent retrieval. Record the source support checks actually performed.

Coverage fields: `searched`, `read`, `unread` (arrays of exact scopes),
`limitations` (array). `searched` does not imply `read`. A result with required
unread evidence, unresolved substantive conflicts or missing permissions is
`partial`. A schema-valid empty answer is not an investigation success.

## Final result

The host writes `mycroft.result.v1` with run ID and status, report path,
admitted worker attempt paths, combined sources/claims, task failures, critique
resolutions, research gaps, coverage and budget observations. See
`assets/result.example.json` for the artifact shape. Preserve original
IDs when merging; equivalent URLs do not justify merging different retrievals.
Use `report_path: "report.md"` relative to the run directory and a final status
of `completed`, `partial` or `failed`, matching the ledger. `completed` requires
all mandatory tasks/evidence and publication; `partial` preserves useful results
with unsatisfied scope or controls, and `failed` means no useful admitted answer.
Do not make globally named claims such as `verified=true` or `complete=true`.
Distinguish `record_checks`, `excerpt_checks` and `entailment_assessment` and
describe each check's scope. A deterministic validator checks structure and
relationships; it cannot verify source authority or entailment.

The report should lead with the answer and its practical consequences. Include
only the sources and critique detail needed to assess those consequences, plus
explicit material gaps. Full contracts belong in the sidecar, not user-facing
product flows. Every materially qualified claim stays qualified in the prose.
