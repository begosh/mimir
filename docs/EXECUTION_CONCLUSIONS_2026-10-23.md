# Mimir execution conclusions, 2026-10-23

Direct model calls are now the default for text-only work. Python owns task
contracts, scheduling, the blackboard, evidence, bounded retries and publication.
Codex, AGY, Claude and OpenCode are tool runtimes, initialized only when needed.
The swarm does not require a separate agent session for every task.

## What we discovered

Small text-only tasks incurred substantial agent-runtime input overhead despite
having tools disabled. Replaying an identical nine-candidate checker prompt
reported 18,522 native input tokens versus 4,683 direct input tokens: a difference
of 13,839 tokens. This measures the transport difference; it does not reveal the
contents of hidden context. Cached input tokens were zero in these tests.

| Captured inputs and execution | Calls | Total reported tokens | Seconds |
| --- | ---: | ---: | ---: |
| Synthetic fixture, six native workers and checks | 14 | 212,517 | 65.9 |
| Same fixture and six tasks, direct requests | 14 | 18,728 | 43.7 |
| Same fixture, one extraction plus synthesis and final check | 3 | 5,154 | 21.4 |
| Two real recipe records, native workers after code-checker fix | 6 | 107,229 | 62.7 |
| Two real recipe records, direct workers | 5 | 23,101 | 48.8 |
| Two real recipe records, minimal direct baseline | 3 | 14,649 | 62.1 |

All listed final consistency checks passed. The same six synthetic tasks used
91.2% fewer tokens through direct requests and finished 33.7% faster in this run.
The minimal direct pipeline used another 72.5% fewer tokens than the direct swarm.
These are measured cases, not general quality, cost or latency guarantees.

Five identical blinded checker batches each contained six correct findings and
three corrupted findings, with shuffled order. Both transports recorded zero
false PASS among 15 negative cases and zero false FAIL among 30 positive cases.
Native used 93,665 tokens/35.375 seconds; direct used 24,558 tokens/21.733 seconds.
Controls omitted kneading, omitted the rolling-pin restriction, and swapped time
and temperature. Correct neighboring answers and claims did not repair failures.
These repeat one fixture and three error types, so do not estimate general error
rates or independently verify factual claims.

Real inputs came from published Recipe JSON-LD on
[Vincenzo's Plate](https://www.vincenzosplate.com/neapolitan-pizza-dough/) and
[King Arthur](https://www.kingarthurbaking.com/recipes/neapolitan-style-pizza-crust-recipe).
They differ in quantities, yeast, sugar and fermentation. Answers selected one
coherent recipe, preserved source differences, and qualified unsupported best
claims. This tests captured recipe records, not autonomous web discovery or
arbitrary HTML extraction. The real native and direct runs batched differently,
so their call/time difference does not isolate transport alone.

## Design decision now implemented

- Interpretation, decomposition, supplied-input atomic work, checks, repairs and
  synthesis use direct Responses requests at the selected model and effort.
- Ordinary tool-using work starts the selected native runtime lazily.
- New tool-runtime runs default to hybrid; `backend=responses` supports direct-only
  work. Explicit native/CLI overrides remain available.
- Separate requests preserve task isolation, schemas and audit records.
- Missing API access stops dispatch rather than silently reverting to native.
- Existing checkpoints keep their recorded route and recovery identities.
- API credentials remain in environment settings, never prompts or committed
  configuration. API model/deployment IDs must be explicit. No model fallback.

The live-tested default uses Azure, gpt-6.1-sol and low effort, with Codex available
for tools. A default-route engine execution of the saved six-task fixture plan
completed checks, checkpoints and publication in 42.543 seconds using 19,108 tokens.
It did not perform fresh planning. OpenCode can use its configured provider
namespace while retaining the same API model, for example azure/gpt-6.1-sol.
Other model/provider/runtime combinations are not qualified by these results.

## Failures and limits retained

Original-request planning still did not complete. Native exhausted eight calls
after 84.599 seconds. Fresh direct planning stopped after seven calls, 51.718
seconds and 13,321 tokens because retrieval depended on an unavailable answer to
a best-criterion clarification. These generated different trees and are not a
matched latency comparison. Decomposition remains too rigid for simple copied
procedures; cheaper transport does not solve that problem.

The first real native test exposed a deterministic-checker bug: it treated a short
supporting quote as the whole assigned source and rejected supported quantities
elsewhere. The checker now uses the bound source for membership checks and handles
attached units and equivalent unit spellings. That failed attempt used 52,068
tokens/38.061 seconds before the corrected rerun. Clean record checks yield REVIEW,
not automatic PASS; completeness and meaning still need assessment.

OpenCode 1.19.4 text-only dispatch succeeded in 2.786 seconds with 54 tokens and no
tool process. Full tool configuration discovery timed out at 30 seconds. A
disposable file-only configuration reached the server but returned no result
before the 180-second worker limit; its usage is unknown. OpenCode tool readiness
is unresolved. No installed OpenCode settings were changed.

DSPy/RLM still require explicit native transport pending separate qualification.
Automatic selection of the minimal baseline, proportional decomposition, dynamic
retrieved-page binding and general quality evaluation remain work to do.

## Delivery and validation

72 focused tests and 16 subtests passed for routing, request validation, failure
handling, cancellation, configuration, diagnostics, recovery and runtime seams.
Reported tokens are usage, not independently checked billing. Local raw packets,
captures and machine configuration remain excluded from Git; published summaries
retain measurements and limitations without requiring those files.
