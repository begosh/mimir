# Mímir Qualification: Multi-Dimensional Candidate Scoring & Predeclared Adoption Thresholds (P3.4)

**Date**: 2026-10-25  
**Component**: `scripts/candidate_scoring.py`, `tests/test_candidate_scoring.py`, `scripts/prompt_comparison.py`  
**Execution Profile**: `codex` / `gpt-6.1-sol / low`  
**Related Requirements**: Priority 3.4 (`tasks/todo.md`)

---

## 1. Executive Summary

Backlog requirement **P3.4** mandates:
> *Score unsupported material claims, omissions, unnecessary blockers, conflict retention and usage; predeclare adoption thresholds and independently review source support before explicit manifest selection.*

Model self-reported "PASS" verdicts cannot be accepted as independent factual verification. To guarantee that prompt modifications genuinely improve reasoning without silently introducing hallucinations, omissions, or unverified consensus, Mímir implements **Multi-Dimensional Candidate Scoring** and an **Adoption Gate** (`scripts/candidate_scoring.py`).

Before any candidate can be adopted or activated in the manifest, it must satisfy strict, predeclared adoption thresholds audited by an independent source support review directly against bound source texts.

---

## 2. Multi-Dimensional Metric Vector

Candidate evaluations record a standardized, multi-dimensional metric vector (`CandidateScoreVector`):

| Dimension | Description | Target Direction |
|---|---|:---:|
| `unsupported_claims` | Material numbers, quantities, or claims absent from bound source texts. | Minimize ($\to 0$) |
| `critical_omissions` | Mandatory procedural steps, ingredients, or pinned versions omitted from the solution. | Minimize ($\to 0$) |
| `unnecessary_blockers`| Requests blocked due to unspecified preferences (e.g. "best") rather than genuine missing inputs. | Zero ($0$) |
| `conflict_retention_rate` | Ratio of opposing source assertions explicitly preserved rather than flattened by consensus. | Maximize ($1.0 = 100\%$) |
| `defect_resolutions` | Number of confirmed training regression defects successfully repaired. | Maximize ($\ge 1$) |
| `usage_calls` | Total model adapter invocations / worker calls. | Cap at $\le 1.15\times$ baseline |
| `usage_tokens` | Total known tokens consumed. | Bounded |
| `wall_seconds` | Total end-to-end execution duration. | Bounded |

---

## 3. Independent Source Support Review

The `IndependentSourceReviewer` conducts an autonomous audit of every generated answer against bound sources:

1. **Material Value Grounding**: Scans for percentages (e.g., `60.0%`), quantities with units (e.g., `1000g`, `600ml`), and semantic versions (e.g., `0.163.0`). Any material value absent from the bound source texts is flagged as an `unsupported_claim`.
2. **Mandatory Elements Audit**: Checks for mandatory procedural steps and ingredients. Any missing item is flagged as an `omission`.
3. **Conflict Preservation Audit**: When sources present conflicting evidence (e.g., Source A specifies 600ml water vs. Source B specifying 650ml water), verifies that both assertions are retained with their respective citations. Flattening conflicts into unverified consensus is flagged as a violation.

---

## 4. Predeclared Adoption Thresholds

`evaluate_candidate_adoption()` applies non-negotiable thresholds (`AdoptionThresholds`) to certify candidates:

$$\text{Decision} = \begin{cases} \text{ADOPT} & \text{if all checks pass} \\ \text{REJECT} & \text{otherwise} \end{cases}$$

| Threshold | Limit | Rational / Purpose |
|---|:---:|---|
| **Held-Out Unsupported Increase** | $\le 0$ | Zero tolerance for new hallucinations or ungrounded claims on held-out cases. |
| **Held-Out Omissions Increase** | $\le 0$ | Zero tolerance for critical omissions on held-out cases. |
| **Unnecessary Blockers** | $= 0$ | Qualified requests must not be blocked due to preference ambiguity. |
| **Conflict Retention Rate** | $100\%$ ($1.0$) | Conflicting evidence must be preserved, not resolved by majority rule. |
| **Train Defect Reduction** | $\ge 1$ | Must demonstrate measurable repair on confirmed repository failures. |
| **Usage Increase Ratio** | $\le 1.15\times$ | Invocations cannot inflate by more than $15\%$ over baseline. |
| **Independent Source Audit** | $100\%$ Clean | Must pass independent source support review with zero ungrounded claims. |

---

## 5. Cryptographic Selection Records

Adoption decisions generate an immutable, content-addressable `SelectionRecord`:

- `selection_id`: Unique deterministic identifier.
- `candidate_id` & `manifest_target`: Target prompt file.
- `decision`: `ADOPT` or `REJECT`.
- `threshold_checks`: Detailed dictionary showing required vs. actual values for each threshold.
- `reasons`: Explicit human-readable decision reasons.
- `sha256`: Cryptographic digest securing the audit trail before manifest activation (P3.5).

---

## 6. Verification & Test Evidence

Validated by `tests/test_candidate_scoring.py` (11 tests, 100% passing in 0.07s):

- `test_score_vector_aggregation_and_conflict_rate`: Confirms score vector metrics and conflict rate arithmetic.
- `test_independent_source_reviewer_verifies_grounded_material_claims`: Confirms grounded material claim verification.
- `test_independent_source_reviewer_flags_unsupported_hallucinations`: Confirms detection of ungrounded quantities and entities.
- `test_independent_source_reviewer_detects_critical_omissions`: Confirms detection of omitted mandatory ingredients.
- `test_independent_source_reviewer_enforces_conflict_retention`: Confirms rejection of consensus-flattened conflicts.
- `test_adoption_gate_adopts_candidate_satisfying_all_thresholds`: Confirms `ADOPT` certification for compliant candidates.
- `test_adoption_gate_rejects_on_held_out_unsupported_claims_increase`: Confirms rejection on held-out hallucinations.
- `test_adoption_gate_rejects_on_unnecessary_blockers`: Confirms rejection on unnecessary blockers.
- `test_adoption_gate_rejects_on_conflict_flattening`: Confirms rejection on conflict flattening.
- `test_adoption_gate_rejects_on_excessive_usage_inflation`: Confirms rejection on $>1.15\times$ usage inflation.
- `test_adoption_gate_rejects_on_independent_review_failure`: Confirms rejection when independent review fails despite model self-reported PASS.

---

## 7. Artifacts & Code References

- **Implementation**: [`scripts/candidate_scoring.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/candidate_scoring.py)
- **Test Suite**: [`tests/test_candidate_scoring.py`](file:///C:/Users/jonas/code/skills.sh/mimir/tests/test_candidate_scoring.py)
- **Workspace Report**: [`artifacts/multi_dimensional_scoring_2026-10-25.md`](file:///C:/Users/jonas/code/skills.sh/mimir/artifacts/multi_dimensional_scoring_2026-10-25.md)
