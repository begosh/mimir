# Mímir porting contract

Use this when adapting the existing engine to another host. Read
[SKILL.md](../SKILL.md), [integration](../docs/INTEGRATION.md) and the source
interfaces before changing behavior. Do not reconstruct an alternate engine.

The host owns the objective, worker choice and chat presentation. Both MCP
and terminal entrypoints call engine.run_mimir. Runtime adapters implement
spawn and awaited cleanup. The scheduler owns dependency readiness, bounded
concurrency, durable result commits and retained-input validation.

Preserve these operating contracts:

- single uses one worker and direct publication; review uses two independent
  specialists, a dependent critic and one final synthesis; swarm opts into
  bounded model planning. Task count is separate from concurrency. No executive
  graph worker precedes final synthesis.
- Native Codex/Claude SDKs and owned OpenCode HTTP reuse native configuration;
  AGY retains its authenticated CLI. No silent transport/provider fallback.
- Structured worker results retain answer, sources, claims and gaps. Hashes
  establish identity; reported source support remains unverified. Public
  snippets/abstracts are discovery material and private facts need private evidence.
- Every successful task is persisted before dependent admission. Resume validates
  prompt, profile, dependencies and raw/parsed output identity. Failed/cancelled
  tasks can retry without repeating intact completed work.
- Saved checkpoints/artifacts are ready events. Final phase completion follows
  awaited cleanup. Publication recovery validates hashes and avoids repeated
  synthesis/learning. Recovering files does not prove historical descendants
  from an earlier failed process terminated.
- Writable learning state is project-scoped and independent of executable
  location. Read is default; off omits context; explicit write records candidates
  separately without automatic promotion or consumption.
- Diagnostics expose operating identity and credential presence without
  inference or secrets. Windows persisted keys may be supplied only to owned
  child environments; global configuration and user sessions remain untouched.
- Context admission never silently truncates evidence. Record known tokens,
  unavailable usage and durations; do not invent billed costs or quality gains.

Exercise the public interfaces with meaningful lifecycle failures, real MCP
protocol checks and authorized native read/schema probes. Keep implemented,
offline-tested, lifecycle-tested and authenticated research support distinct.
Compare new orchestration with a single-worker baseline before claiming an
improvement. Dataset-scored GEPA remains a separate opt-in optimizer.
