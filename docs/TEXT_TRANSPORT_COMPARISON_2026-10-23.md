# Direct text requests versus native workers, 2026-10-23

Direct Azure Responses requests work with the exact selected gpt-6.1-sol model and low effort. The matched synthetic six-worker comparison used 18,728 direct tokens versus 212,517 native tokens (91.2% fewer), with both final consistency checks passing. A minimal extraction-plus-synthesis baseline used 5,154 tokens including final checking. Real conflicting recipe captures also favored direct requests for tokens; parallel extraction was faster than one larger extraction in this run.

## Measured runs

All token counts are reported total input plus output usage, not verified billing. All times include generation and final checking, with cleanup. No fresh planning calls are included in these rows.

| Inputs | Execution | Calls | Tokens | Seconds | Final checker |
| --- | --- | ---: | ---: | ---: | --- |
| synthetic | minimal_direct | 3 | 5,154 | 21.4 | PASS |
| synthetic | direct_swarm | 14 | 18,728 | 43.7 | PASS |
| synthetic | native_swarm | 14 | 212,517 | 65.9 | PASS |
| real_conflicting | minimal_direct | 3 | 14,649 | 62.1 | PASS |
| real_conflicting | direct_swarm | 5 | 23,101 | 48.8 | PASS |
| real_conflicting | native_swarm, corrected code gate | 6 | 107,229 | 62.7 | PASS |

The synthetic native and direct swarm arms use the same six previously saved contracts and the same source; neither changes model or effort. All six checks happened as individual calls because workers did not finish within the two-second batching delay. The direct real arm coalesced its two checks; the corrected native real arm did not. Their five-versus-six call difference is a timing-dependent batching effect, so that row is not a pure transport comparison.

Minimal-direct generation takes two calls; the table includes a third final-check call. Synthetic generation alone: 3,347 tokens. Real generation alone: 10,184 tokens. Minimal baseline has no separate task checker, so it has fewer acceptance boundaries than the swarm; final checking is identical in role and prompt but consumes each arm's own findings. This is a topology/cost comparison, not a claim of identical safeguards.

## Exact-prompt transport control

The five previously saved blinded nine-candidate checker prompts and schemas were replayed unchanged through direct Azure requests. Both runtimes used gpt-6.1-sol/low. Each batch included six correct and three subtly corrupted outputs in shuffled orders.

- Native: 93,665 total tokens, 35.375 seconds, 0/15 false PASS, 0/30 false FAIL.
- Direct: 24,558 total tokens, 21.733 seconds, 0/15 false PASS, 0/30 false FAIL.
- Input tokens per identical prompt: native 18,522 versus direct 4,683, a 13,839-token difference. No hidden-context breakdown is inferred from this difference.

This controlled replay isolates transport more closely than fresh worker runs. Repeated cases share one fixture and three corruption types; these are observed case counts, not general error-rate estimates. Cached input tokens were zero in all measured arms: no caching savings are claimed.

## Real sources and quality limits

Public pages were retrieved with certificate validation using the configured Zscaler trust certificate. Their published Recipe JSON-LD was parsed deterministically, preserving ingredient fields, declared yields and all instructions, including out-of-scope baking text. Indexed captured inputs were 3,861 and 6,008 characters. Raw HTML and parsed JSON remain in the packet. This tests two real recipe records, not full-page research, discovery ranking or extraction from arbitrary HTML.

- [Vincenzo's Plate](https://www.vincenzosplate.com/neapolitan-pizza-dough/): 1 kg flour, 600 ml water, 30 grams salt, 1-2 grams fresh yeast; at least two-hour rest and 24-hour ball fermentation at 16-18 C.
- [King Arthur](https://www.kingarthurbaking.com/recipes/neapolitan-style-pizza-crust-recipe): 232 g flour, 170 g water, 8 g salt, dry yeast and sugar; 12-24-hour first rise and 45-minute to one-hour second rise.

Published yield metadata also contains unexplained values. Successful outputs retain uncertainty instead of silently reconciling it. Final answers select one coherent recipe and state the other recipe's differences. They qualify best as unestablished, cite source URLs and exclude baking and toppings. Model PASS is a consistency verdict, not independent factual verification. Short final answers summarize some alternative details rather than reproducing every published conversion or stand-mixer instruction. Source-conflict preservation was demonstrated; exhaustive completeness is not established by this test.

The original unsteered question is retained as the request, but transport/topology arms use explicit dough-only scope and fixed contracts. They do not prove autonomous interpretation of that request. This scope matches the comparison's acceptance criteria and is disclosed instead of being hidden in a rewritten request.

## Found and fixed during testing

The first native real-source attempt failed at 52,068 tokens/38.061 seconds. Code treated a short supporting quote as the complete assigned source, incorrectly rejecting supported values elsewhere in the source. The conservative record checker now uses the bound full source for membership checks; the model still evaluates source-line support and completeness. Unit handling also recognizes attached units (24hr, 600ml) and equivalent unit spellings (grams/g, hr/hours). The original failure remains in the packet; the corrected native run is a fresh run and its additional cost is not omitted from the evidence.

## Original-request planning

Fresh direct planning on the original request plus the synthetic fixture stopped after seven calls, 13,321 tokens and 51.718 seconds. Earlier native planning stopped after eight calls/84.599 seconds. These are different generated trees, not a matched-speed comparison. The direct plan required an answer to its best-criterion clarification before retrieval; its reviewer correctly observed that a clarification worker returns a question, not the user's answer. The simplicity prompt still requires splitting a whole multi-stage procedure even when it is straightforward copying from one short page. Planning remains incomplete; cheaper transport does not fix unnecessary clarification or over-splitting.

## Implemented route

Use `--backend codex --model gpt-6.1-sol --effort low --worker-transport hybrid`, or the corresponding MCP start_run fields. Native remains the default and no project profile was saved. Explicit hybrid selection sends restricted/text-only operations to Responses; ordinary tool-using spawn stays native. Both routes share the selected model/effort and broker audit, schema validation, bounded repairs, source qualification, checkpoint identity and publication gates. Each request contains no tools, no conversation history, store=false and an explicit reasoning effort. No automatic HTTP retries or native fallback occurs. Credentials are read from configured environment (including persisted Windows User/Machine variables), never copied into artifacts. Configured CA certificates remain enforced.

Provider selection can be made explicit with MIMIR_TEXT_API_PROVIDER=azure or openai; otherwise hybrid uses an explicitly configured Azure endpoint if present, then OpenAI. Azure accepts a resource root or its /openai/v1 endpoint. Missing keys fail before dispatch. Endpoint/provider identity is retained in recovery fingerprints without credentials. No undocumented subscription-auth endpoint is used.

An integrated hybrid engine run completed execute, checkpoints, source handoff, synthesis and final PASS: 13 calls, 18,436 tokens, 37.312 seconds. Its batching differs from the controlled six-task arms, so it is operational validation rather than another matched row.

Default routing and automatic task sizing have not changed. Online DSPy/GEPA optimization and caching behavior remain separate work. The minimal baseline is a benchmark, not an automatically selected production mode.

## Validation and packet

Focused tests cover minimal request payloads, schema/incomplete failures with retained usage, cancellation, tool/text routing and cleanup, numeric source checks, scheduler acceptance, repair, checkpoints and MCP lifecycle. Exact prompts, schemas, replies, source captures, control mappings, per-call usage and timings are retained locally.

[Consolidated comparison](../.mimir/transport-comparison-20261023/comparison.json).

- [direct_blinded_replay](../.mimir/transport-comparison-20261023/direct_blinded_replay/results.json)
- [direct_original_planning](../.mimir/transport-comparison-20261023/direct_original_planning/results.json)
- [real_conflicting-direct_swarm](../.mimir/transport-comparison-20261023/real_conflicting-direct_swarm/results.json)
- [real_conflicting-minimal_direct](../.mimir/transport-comparison-20261023/real_conflicting-minimal_direct/results.json)
- [real_conflicting-native_swarm](../.mimir/transport-comparison-20261023/real_conflicting-native_swarm/results.json)
- [record_check_fix\real_conflicting-native_swarm](../.mimir/transport-comparison-20261023/record_check_fix/real_conflicting-native_swarm/results.json)
- [synthetic-direct_swarm](../.mimir/transport-comparison-20261023/synthetic-direct_swarm/results.json)
- [synthetic-minimal_direct](../.mimir/transport-comparison-20261023/synthetic-minimal_direct/results.json)
- [synthetic-native_swarm](../.mimir/transport-comparison-20261023/synthetic-native_swarm/results.json)

Official API references: [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Reasoning effort](https://developers.openai.com/api/docs/guides/reasoning). These establish request formats; measurements above come from the local test packet.
