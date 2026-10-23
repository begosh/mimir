# Measured performance investigation, 2026-10-22

The latest archived native review was explicitly dispatched with
`model="gpt-6.1-sol"`, `effort="high"`, `worker_timeout=1200`,
`max_concurrency=2`, `max_context_chars=240000`, `mode="review"` and
`research_program="native"`. This was a host invocation choice, not an SDK
failure to apply low effort. No DSPy/RLM investigator or upstream GEPA training
ran in this review. Routine reflection is one synthesis call.

Run `c3198c9a4e9342649b6e0bce120750cd` retained these adapter records:

| Stage | Seconds | Supplied characters | Cumulative reported tokens |
| --- | ---: | ---: | ---: |
| Evidence specialist | 697.5 | 6,347 | 2,796,166 |
| Alternatives specialist | 557.4 | 6,461 | 1,629,097 |
| Dependent critic | 469.1 | 90,627 | 1,214,685 |
| Synthesis | 309.3 | 157,975 | 619,892 |

The specialists ran concurrently. The critical path was approximately
697.5 + 469.1 + 309.3 = 1475.9 seconds; recorded total was 1476.2 seconds
(24.6 minutes), with planning taking 0.17 seconds. This points to model/tool
work, rather than Python planning, as the main duration. Old records do not
separate runtime startup from model/tool activity.

The reported 6,259,840 tokens are cumulative native usage, including repeated
and potentially cached context across tool continuations. They are not unique
prompt tokens or a billing measurement. Old records lack input/cache/reasoning
breakdowns. Native provider configuration currently selects Azure; model effort
is explicitly supplied to Codex `thread.turn`, independent of host defaults.

Archived low-effort runs took 63.8 and 98.0 seconds in single mode, and 78.1,
249.8 and 352.1 seconds in review mode. Their goals differ, so these are historical
observations, not a controlled speedup comparison. Recent host-created development
subagents also recorded high effort; those are distinct from engine workers.

Compared with initial Git revisions, native workers can now retrieve primary
evidence through configured tools, rather than only produce a text completion.
Every Codex invocation starts a new SDK app-server runtime and ephemeral thread.
The first synthesis also truncated the draft to 4000 characters and critique to
2500; current evidence-preserving synthesis retains full findings. Reintroducing
that silent evidence loss is not an acceptable optimization. The current review
has two parallel specialists, then critic, then synthesis; only the specialists
run in parallel. Native low effort limits reasoning, not tool loops or context
growth. The default 180-second worker timeout was overridden to 1200 in the slow
review, and ordinary native runs have no default whole-run token ceiling.

Changes made in this investigation:

- Codex synthesis uses the existing restricted text-completion transport,
  disabling research tools, MCP servers and delegation. Other adapters receive
  an explicit evidence-only synthesis instruction; no unsupported runtime
  restriction is claimed.
- Critique is included once in synthesis. Previously it appeared both among all
  worker results and in the separate critique block. The archived input would
  lose 31,462 duplicated characters, approximately 20%, retaining all evidence.
- Adapter records include requested model/effort, tool policy, timeout, output
  size, input/cache/output/reasoning token breakdowns when available, and Codex
  startup/thread/turn/cleanup timings. Totals identify breakdown availability;
  unknown usage remains unknown. Turn time includes native tool continuations.
- Worker instructions require targeted work and compact results. The skill
  distinguishes worker effort from host effort and requires an explicit worker
  choice before increasing effort or deadlines. It selects single mode for
  focused questions rather than applying a review to every request.

Validation: 77 focused tests and 33 subtests passed, with 9 explicit skips.
The complete suite then passed: 241 tests and 112 subtests, 9 explicit skips.
A live restricted Codex call using `gpt-6.1-sol` / `low` returned the requested
structured answer in 7.033 seconds: startup 2.944s, thread ready 3.049s from start,
turn 3.970s, cleanup 0.014s. Usage was 13,843 input tokens, 15 output tokens,
0 cached input tokens and 0 reasoning-output tokens. The native runtime still
has a substantial instruction prefix even for a tiny completion. This smoke
test verifies operation and accounting; it does not establish full-review
latency or quality gains. A same-goal, same-source before/after review benchmark
remains necessary for a measured overall speedup.

Evidence: archived `checkpoint.json` and `report.json` from the named run,
historical host invocation records, local Codex thread metadata, current source,
initial Git revisions and the live restricted call. Archived artifacts were read
from the temporary workspace-cleanup recovery archive without restoring or
modifying them. These token records do not establish billed cost.

## Compact assignment follow-up

The same two-file timeout/cleanup review was repeated after separating explicitly
labelled role assignments and enforcing output admission. The shared objective
text and settings were identical: native Codex, gpt-6.1-sol / low, concurrency 2,
180-second worker timeout, review, memory/scout/JEV off, no research budget.
The updated test used a fresh terminal engine process because the connected MCP
had imported the prior code. Both routes use the same engine and worker adapter.

| Measurement | Previous run | Updated run |
| --- | ---: | ---: |
| Recorded engine duration | 94.1s | 84.2s |
| Cumulative native tokens | 250,488 | 225,137 |
| Output tokens | 5,902 | 3,257 |
| Critic supplied characters | 16,671 | 9,364 |
| Synthesis supplied characters | 23,122 | 14,412 |
| Specialist answer words | 292 / 267 | 151 / 181 |
| Critic answer words | 165 | 152 |
| Final answer words | 256 | 238 |

Observed reduction: duration 10.5%, cumulative tokens 10.1%, output tokens 44.8%,
critic input characters 43.8%, synthesis input characters 37.7%. This is one
before/after pair, not a statistical latency guarantee. The source under review
contains the changes being tested, so input source bytes and line numbers differ.
The critic took 39.1s versus 30.3s previously; native turn variation remains.

Explicit role-labelled instruction paragraphs are separated without an extra
model planner. Shared unlabelled question and constraints are preserved, and the
original complete goal remains in the checkpoint. Each specialist receives only
its own assignment; synthesis receives the shared goal and synthesis assignment.

Review admission enforces 250 answer words per specialist, 180 per critic, 300
for final synthesis and 120 for reflection. Source/claim/gap arrays and excerpts
are bounded in the native schema and checked before dependency admission.
Rejected results and known usage are retained in checkpoints; they do not cause
automatic retry, hidden truncation or successful publication. Single/swarm and
historical checkpoints retain their existing admission behavior. Native tool
read counts and provider token generation are not bounded by these checks.

All four live calls used the agreed model and low effort; synthesis used the
restricted text-only transport. All size checks passed, with no rejected result
or extra worker invocation. The final answer retained the central code-backed
distinctions: startup/model timeout is not a total invocation deadline; the
broker has no deadline without a research budget; cancellation cleanup retains
ownership and can wait for late startup. Runtime stall/leak outcomes were not
tested. The complete regression suite passed: 246 tests, 112 subtests, 9 skips.

Baseline: `15ce521b84fe4d778e8964932d2d24ba`.
Updated run: `e78e92a739d94e20850d25bb0fee0a9b`.
The updated run directory includes the exact goal, comparison configuration,
checkpoint, report, sidecar and acceptance assessment.
