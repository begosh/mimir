# Mimir self-hardening assessment — 2026-10-23

Mimir has a functioning, bounded orchestration and recovery engine. It has demonstrated useful model consistency checks and cheaper text dispatch. It has not demonstrated elimination of hallucinations, reliable interpretation of ambiguous intent, proportional decomposition, or an effective failure-to-improved-prompt feedback loop.

This assessment uses the current working tree, including pre-existing uncommitted changes. No code or configuration was changed. No public search was used. Workers used the connected Mimir engine, Codex/hybrid, gpt-6.1-sol and low effort, default 180-second worker timeout; no effort or limits were increased. Run artifacts are analysis outputs. Some dated documentation describes older code; current definitions take precedence. Historical measurement packets were not inspected; the optional-research qualification document explicitly says its raw artifacts were removed.

## Capability map

| Area | Implemented and demonstrated | Implemented but insufficiently tested | Planned or missing |
| --- | --- | --- | --- |
| Intent | Original goal and host brief persist; no automatic raw-question search; single/review avoid model planning | Semantic fidelity, clarification materiality and defaults are prompt judgments, not schema guarantees | Evaluated distinction between answer-blocking ambiguity and uncertainty that permits progress |
| Decomposition | Opt-in recursive contracts, model simplicity/coverage review, bounded planning repair; code enforces call/time/node/depth/leaf limits and inherited dependencies | Live gates sometimes reject useful copied procedures and disagree; a repaired saved plan worked, fresh ordinary recipe planning failed | Automatic smallest sufficient plan and benefit-based stopping |
| Scheduling/blackboard | Kahn cycle/reference validation; dependency-ready dispatch; bounded concurrency; persist before release; task-owned direct-dependency context; identity-checked resume | Evidence sufficiency and semantic conflicts depend on assignments and model records | Dynamic retrieval-to-frozen-source binding and selective spans for ordinary atomic tasks |
| Checks/repair | Atomic result gate, conservative extraction-record checks, batched model verdicts; two repair cycles; non-single final gate; reject malformed verdicts | Same-model checking, limited error families, ordinary worker bypasses; completeness of source meaning not independently verified | Common material-claim gate across policies; checked corrections in published appendices; bounded assembly repair |
| Routing/recovery | Stateless Responses text requests; lazy native tools; fixed broker model/effort; schema validation; usage, retained-output and publication identities | Live qualification chiefly Azure/Codex/gpt-6.1-sol/low; hybrid crash recovery not independently demonstrated here | Always-durable ordinary-run attempt journal and default cumulative execution budget |
| Research programs | Actual DSPy Predict, interpreter-backed RLM, upstream GEPA training, optional JEV pruning | Synthetic qualification is small; no accepted changed-prompt improvement or demonstrated JEV net savings | Governed ordinary-run failure ingestion, representative held-out evaluation and measured selection |

### 1. User intent

[task_brief.py](../scripts/task_brief.py) validates structure and limits. [recursive_planner.py](../scripts/recursive_planner.py) keeps the original request and instructs material clarification and labelled assumptions. These mechanisms preserve wording and a reviewable plan; they do not establish that interpreted constraints are genuinely supplied by the user.

The recorded fresh direct recipe plan stopped after seven calls, 51.718 seconds and 13,321 tokens because retrieval depended on an unanswered criterion for “best.” The native run exhausted eight calls after 84.599 seconds. Different trees prevent a matched transport comparison. Relevant evidence: docs/EXECUTION_CONCLUSIONS_2026-10-23.md:70 and scripts/recursive_planner.py:163.

Keep a genuine missing required input blocked. For ordinary ambiguity, gather relevant evidence and qualify the recommendation, or state a reversible assumption. A missing preference should not automatically become a prerequisite for source retrieval.

### 2. Decomposition and calls

Recursive planning defaults to eight calls, 120 seconds and 32 nodes. Leaves, depth, child counts, named input/output bounds and two planning repair attempts add deterministic limits. Review and repair share those caps; unfinished branches cannot be relabelled atomic to fit the budget. This is bounded termination, not evidence that splitting stops at the cheapest adequate task.

The simplicity prompt rejects whole copied multi-stage procedures. Recorded integration repaired a saved five-leaf plan into seven leaves, adding five live calls and 41.594 seconds. That demonstrates the repair mechanism while leaving its usefulness open.

Recorded same-fixture execution used 18,728 tokens with six direct workers and checks, versus 5,154 for one extraction, synthesis and final check. The simpler topology has fewer acceptance boundaries; adopt it only if held-out completeness and unsupported-claim scores remain acceptable. The native/direct same-six-task comparison, 212,517 versus 18,728 tokens, better isolates transport.

Planning limits are not an ordinary default whole-run spending ceiling. prepare_research returns budget=None for native unless explicitly supplied; InvocationBroker enforces cumulative attempts/deadline/reported-token threshold only when configured. A reported-token threshold can overshoot after an in-flight request. Named retrieval/tool limits are prompt contracts, not native tool-count enforcement.

### 3. Scheduling and evidence handoff

scripts/task_graph.py:214 implements Kahn validation. scripts/scheduler.py:113 executes ready work without a whole-tier barrier; tests/test_scheduler.py checks early dependent starts, concurrency and cancellation/recovery. Kahn supplies graph integrity and ordering; it verifies no finding.

The blackboard stores engine-owned task results with raw-output identity and provenance. A new worker receives every direct dependency result, without unrelated outputs or silent truncation. Contract verification_passed remains false for ordinary accepted worker assertions. The store name verified_evidence_store describes identity, not factual verification. Missing context fails admission.

Captured sources bind exact named IDs and frozen text/type/time/status to atomic inputs (scripts/source_binding.py:7). Whole small sources up to 16,000 characters are supported. Large sources require caller-prepared bounded evidence; RLM has operational source-span queries, but ordinary atomic handoff lacks automatic slicing.

Retrieve-worker outputs can carry claimed sources/excerpts through dependency results, but the engine does not yet automatically freeze their retrieved pages and bind them as independently captured dependent inputs. Source records and separate findings preserve disagreement; there is no deterministic semantic conflict resolver. Checker batching retains per-candidate references, but puts evidence and multiple candidates in one model request: model attention and cross-candidate independence are not hard isolation guarantees.

### 4. Detection, repair and publication

scripts/engine.py:502 installs acceptance/repair policy only on atomic_v1 nodes. Ordinary single/review workers bypass this atomic result gate. Extract tasks first get conservative ID/line/number/unit membership checks; clean records return REVIEW, never factual PASS (scripts/extraction_checks.py:5). Matching numbers somewhere in a source does not prove field association, step order or completeness. Calculations still use a model; a small explicit formula registry could verify supported arithmetic deterministically.

A valid FAIL permits two objective rephrasings/reruns under the unchanged original contract: three worker attempts maximum. Each retry must pass before dependents run. Missing evidence produces BLOCKED; work needing splitting produces STOP. Execution does not dynamically repair the DAG. Invalid checker output, schema/worker failure and exhausted budgets do not trigger that result repair. One repair cycle adds rephrase, worker and check calls. Attempt versions persist; an interrupted repair consumes its reserved slot, without exact prompt replay.

Non-single synthesis requires final PASS and preserves rejected synthesis on failure. Single publishes its normalized worker answer without a separate final checker. Final checking evaluates the assembled answer plus limitations against supplied findings, not independent source truth. Honest explicitly incomplete coverage can pass.

Current phased execution rejects incomplete graphs (engine.py:575); loading a synthesis checkpoint requires results for every planned task (engine.py:318). A direct smoke check during this assessment returned “Synthesis requires results for every planned task.” This must not be confused with semantic completeness: all tasks can finish while omitting an essential definition or fact.

The final gate checks synthesis, while the Markdown report also reprints original worker and critic outputs (engine.py:750). This assessment's real review preserved an overreaching worker claim in that appendix even after the critic softened it. Corrected or rejected assertions need explicit version status if included in the publication.

### 5. Direct API and native tools

TextResponsesBackend sends explicit model/effort, one request input, tools=[], store=false and strict output schema (scripts/text_api_backend.py:73). It rejects a returned model mismatch when a model ID is present, incomplete responses and schema-invalid results. The broker prevents per-call model/effort changes (scripts/invocation_broker.py:109); the bare adapter's override parameters are not that guarantee. Requested effort does not independently prove provider reasoning behaviour.

Both routes retain attempt/output identity and known usage. Completed-result reuse checks dependencies, inputs, results and acceptance policy. Publication recovery checks report/sidecar hashes and avoids repeating successful synthesis. This is identity-bound reuse, not exactly-once remote billing or authenticated evidence. Ordinary-run durable journaling is conditional on a configured budget; hard-crash usage can remain unknown.

Repeated identical blinded batches recorded zero false PASS among 15 negatives and zero false FAIL among 30 positives per transport. These repeat six positives and three recipe error types, not 45 independent general cases. Reported usage is not billing. OpenCode text dispatch worked, but tool readiness remains unresolved; other hybrid runtime/model combinations have narrower qualification.

Native tools are justified for actual filesystem retrieval, approved connected sources, or operations unavailable to a text request. Frozen text extraction, arithmetic, comparison, supplied-input critique and assembly should use direct requests. The fresh review still routed its supplied-input critic through native_tools; narrowing dispatch by an explicit needs_tools contract would remove an avoidable runtime path without a reusable conversational pool.

### 6. Named mechanisms

| Mechanism | Actual operation | Measurable purpose and evidence limit |
| --- | --- | --- |
| Kahn-DAG | In-degree/queue cycle and reference validation; runtime dependency-ready scheduling | Correct ordering, early dependent release, cancellation and recovery tests; no factual-quality claim |
| DSPy | Typed Predict over captured evidence via qualified native bridge | Historical six held-out synthetic cases: 6/6, six attempts, 25.42 seconds; native 5/6, six attempts, 69.13 seconds. Too small for general superiority |
| RLM | Generated programmatic inspection in guarded Deno/Pyodide, source queries/spans and bounded recursive subcalls | Demonstrated larger-than-context corpus and depth-0/1 calls; 6/6 synthetic cases, 14 attempts, 87.62 seconds. Use where selective programmatic access is necessary, not by default |
| GEPA | Upstream dspy.GEPA compiles train/dev data, proposes changed investigator/action/extraction instructions, emits unreviewed candidates | Selected instructions stayed equal to baseline; proposals exist, but prompt-improvement benefit is unestablished. No online self-hardening |
| JEV | Optional model criticality/redundancy score and protected-node pruning | Off by default; no calibrated probability, measured information gain, or qualified net savings/omission rate. Choice/screen helpers are not the current engine's admission gate |

The older scripts/gepa_optimizer.py reflective helper still exists in probes/tests; normal engine synthesis uses post_worker, not that helper. A name or dormant helper must not count as an operational learning loop. DSPy/RLM require explicit native Codex transport and captured manifests; hybrid compatibility remains unqualified.

## Ranked improvements

### 1. Bind material claims to engine-owned evidence before release and publication

**Expected benefit:** Most direct reduction in unsupported factual assertions and evidence laundering across worker, critic and answer boundaries.

**Evidence:** Atomic-only admission; dynamic retrieved-page handoff missing; numeric membership cannot establish meaning; fresh review final PASS despite incomplete relevant evidence, invalid worker timestamps and an uncorrected appendix assertion. Record/reference audits currently qualify coverage rather than block every defect.

**Proposed change:** Use a small shared material-finding contract for all policies, with engine-generated source IDs/capture times and exact spans. Freeze retrieved evidence once, bind only needed spans to dependents, preserve conflicting versions, and reject unknown or changed references. Add deterministic validation where possible, then a narrow semantic check against original evidence. Single can check its existing answer without adding synthesis. Keep final PASS a model assessment; require independent source/test checks for consequential conclusions. Allow at most one targeted assembly correction followed by recheck; keep failed assertions quarantined or explicitly marked corrected in appendices.

**Acceptance criteria:** No required rejected finding releases a dependent or becomes an unqualified published claim. Source/claim conflicts and missing coverage survive assembly. Unsupported values, wrong source/version, omitted required facts and changed snapshots fail the relevant gate. A correction does not alter objective, evidence or checker policy. No claim of independent verification is produced from model agreement.

**Smallest meaningful test:** One real code question, one cited source span, one dependent and one final answer, parameterized for single/review. Replace a supported claim with a wrong field association using values that both occur in the source; verify rejection, no dependent release, no unqualified appendix publication, and acceptance of the source-supported correction. Use deterministic known source facts and a fresh blinded low-effort check separately.

### 2. Start with the cheapest sufficient task and split only for a demonstrated need

**Expected benefit:** Higher completion rate on ordinary requests, fewer unnecessary clarifications and substantially less avoidable orchestration.

**Evidence:** Fresh ambiguous recipe planning blocked or exhausted; saved planning repair added five calls; simpler direct fixture pipeline used 72.5% fewer tokens than the direct six-task pipeline. Ordinary cumulative budgets/journals are opt-in; the real review used native tools for a supplied-input critic.

**Proposed change:** Retain original intent and classify uncertainty as required-input blocker or qualified assumption. Start with one bounded retrieval/extraction; split only when input/output bounds or distinct decisions demand it. Permit short contiguous procedures. Choose deterministic computation for explicit formulas. Dispatch text/tool work from needs_tools, rather than a broad role name. Apply one persisted attempt/deadline budget across planning, worker/check/repair and assembly calls, with review reservations and journaling; avoid another model “cost estimator.”

**Acceptance criteria:** Ambiguous recommendations retrieve evidence without inventing preferences or blocking on unnecessary criteria; genuine missing required choices still block. Simple captured-source tasks use one worker, one result gate and publication, without recursive planning calls. On a frozen real-source case set, fewer calls/tokens do not increase critical omissions or unsupported claims. All failures and reservations remain counted after resume; exhaustion cannot silently widen limits.

**Smallest meaningful test:** Paired requests over the same real captured source: a useful recommendation with an unspecified “best” criterion, and a request whose answer truly depends on a missing target. The first proceeds with qualification; the second blocks only the dependent decision. Add one contiguous-procedure case and assert no redundant split. Repeat fresh model planning at unchanged settings; scripted wiring alone cannot establish semantic improvement.

### 3. Build a governed offline failure-to-regression loop before expanding evolution

**Expected benefit:** Repeatable improvement across runs without encoding failed assumptions as standing guidance or teaching the model to game its checker.

**Evidence:** Failure/accounting artifacts and unvalidated learning candidates exist, but no ordinary failed-run ingestion into training/regression was established. Upstream GEPA operates over a bounded synthetic dataset; all selected instructions remained baseline. Existing exact-answer and reference-presence metrics do not assess material source entailment.

**Proposed change:** Deduplicate failure packets containing original intent, source snapshot/spans, attempt, feedback and independently adjudicated defect. Turn them into versioned regressions first. Use reviewed training/dev cases for prompt proposals, with fresh held-out families separated by source/topic and failure lineage. Compare the existing prompt with one candidate at fixed model/effort/tools/budgets. Freeze checker rules and intent contracts outside the trainable prompt; score unsupported material claims, omissions, unnecessary blockers, conflicts and usage. Explicit manifest selection and rollback remain mandatory; rejected candidates are not guidance. Start with manual prompt edits; use GEPA only if it beats that simpler process.

**Acceptance criteria:** No candidate sees held-out answers or modifies checker/intent policy. A candidate needs a predeclared useful benefit with no critical source-support regression, independently reviewed, before activation. Duplicate failures do not leak across splits. Losing or unchanged candidates leave runtime behaviour unchanged. Selection history and rollback are reproducible.

**Smallest meaningful test:** One independently confirmed repository failure and one disjoint held-out repository question, with original versus edited prompt. Reject a candidate that fixes training by inventing a constraint or weakening checks. This verifies governance, not broad quality improvement; subsequent adoption requires a larger representative set.

## Representative end-to-end evaluation conducted now

Run: 7eacc84b92a44c51b92bffa8a4e71cdd, real current repository, not synthetic fixture. Bounded objective: determine atomic admission, single/review publication and incomplete-graph behaviour. Two narrow specialists, one supplied-report critic, direct synthesis and final checker; memory off, no web, gpt-6.1-sol/low throughout.

- Completed plan/execute/synthesize, report and sidecar; 94.116 seconds accumulated engine time.
- Five adapter invocations; native workers/critic can contain additional provider continuations.
- 240,752 reported total tokens, including 155,317 cached input tokens; no billed-cost claim.
- Final checker PASS, report evidence coverage partial.
- Useful critique: softened the evidence worker's unsupported claim that incomplete legacy state could publish.
- Unresolved quality: omitted _load_state completeness enforcement because the narrow assignment excluded it; final PASS could not discover that missing evidence. The host independently inspected engine.py:318 and ran a tiny incomplete-checkpoint rejection check. The engine rejects the checkpoint before synthesis.
- Audit defects: worker timestamps used an invalid format; literal full-locator presence audit failed despite abbreviated citations. These must be separated from semantic citation correctness. The source excerpts are model summaries, not engine-extracted exact quotes.
- Publication defect: the original overreaching worker claim remains in the task-results appendix; final gating covers the assembled answer.

This is one operational review smoke test, not a comparative quality estimate or recursive-plan evaluation. It does not qualify web retrieval, interruption recovery, optional RLM or learned prompts. It supplies real evidence that isolation/critique/publication operate, and that evidence incompleteness can survive a final PASS.

## Validation and assessment boundary

Focused checks during this analysis: 24 admission/source/repair/batching/final/scheduler tests plus seven subtests; 55 planning/routing/policy/evaluation tests plus 14 subtests; 17 optional research-program tests in .venv-research. Total: 96 tests and 21 subtests passed. Optional tests use controlled/native-fake completions for engineering mechanisms; they do not establish live model accuracy. No full suite or broad rerun was needed.

Deterministic guarantees: graph integrity, configured caps, schema/admission identities, bounded accepted-attempt release, checked checkpoint reuse and publication rejection on valid FAIL.

Model consistency: interpretation, simplicity, completeness, source meaning, repair rephrasing, critique and final PASS.

Independent verification in this assessment: host inspection of the actual guarded code and tests, focused test execution, and incomplete-checkpoint rejection. Historical recipe/optional measurements remain document-reported; model claims about real-world truth remain unverified.

The next step is stronger evidence boundaries and cheaper sufficient execution, followed by measured offline learning. More agents, recursion or evolutionary machinery should earn their place by beating the simplest checked baseline.
