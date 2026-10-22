# Validation

This file records observed qualification of Mycroft 0.1.0. Structural validation
and live native behavioral checks are separate. This build does not claim
equivalence to executable DSPy/RLM or upstream GEPA, universal harness support,
calibrated scores or general research improvement.

## Package and tooling

- Three skill frontmatters passed the bundled skill-creator validator. Seven
  Codex TOML definitions, fourteen Markdown agent frontmatters and three UI
  metadata files parsed successfully; UI lengths and invocation names matched.
- The worker schema passed Draft 2020-12 schema validation. All text resources
  decoded as UTF-8. Local Markdown links and package resources resolved.
- `Build-Adapters.ps1 -Check` verified all 21 registration files match the seven
  canonical role prompts. Archive building runs this drift check as well.
- Copying the complete package to an unrelated temporary directory preserved
  working local references and adapter checks, without the Mimir checkout.
- An allowlisted ZIP built successfully, extracted to another directory, passed
  resource/adapter checks and installed into a project path containing spaces.
- PowerShell 7 and Windows PowerShell 5.1 each passed **37 tooling assertions**:
  three project installs, no-write preview, preserved existing configuration,
  reinstall/late collision rejection, valid publication, bad source links,
  discovery-only support, identity mismatch, exceeded dispatch cap, failed
  dependency, graph cycle, missing report, mismatched final status, extra nested
  fields, and honest partial publication with failed required evidence.

Tooling checks establish structure and file behavior. They do not establish
retrieval success, excerpt fidelity, claim entailment, hidden native token usage,
raw input/output size, cleanup or model compliance. The optional run checker is
for research ledgers; it does not validate optimizer experiments.

Development used existing Python tooling to parse/validate files only. No Python
model engine or SDK inference process was used for Mycroft's behavioral run.
The distributed package contains no Python scripts or dependencies.

## Native behavioral run

An isolated Harbour review used this host's native subagent tools with **three
logical roles, one active worker and six dispatches** (eight permitted). The
coordinator spawned one generic worker and reused it for alternatives, record
repairs and dependent critique because a native close tool was unavailable.
Provider/model settings were inherited. No Python/SDK model process ran.

The admitted evidence, alternatives and critic records preserved the September
two-zone proposal vs October one-zone operational report, RTO target 30 minutes
vs reported measured 47, target RPO 5 minutes without a measured RPO, unrecorded
owner and missing network diagram. The saved search snippet stayed discovery
evidence; the imported instruction injection supplied no owner, verification
claim or launch authorization. The critic reopened sources and retained those
qualifications. This is a fixture result, not live infrastructure verification.

Observed weaknesses and fixes:

- Three initial/narrowed returns exceeded their assigned output bound. The
  coordinator preserved them as invalid attempts and spent budget on repairs;
  final admitted evidence/alternative/critic transcripts measured 5,864 / 7,166 /
  7,322 characters against 8,000-character assigned bounds. The contract now
  explicitly counts JSON formatting and discourages redundant record text.
- Ledger `required_evidence`, reservation status and result receipt fields were
  initially ambiguous. The protocol now spells out boolean requirements, task
  vs attempt statuses and `result_path` conventions. Existing evidence records
  were preserved while ledger defects were corrected.
- Skills changed during this development smoke run; both observed instruction
  identities and drift were retained. It is not a qualification of unchanged
  instruction recovery. Production runs must freeze their dispatch packets.
- A reused native thread retains prior answers. The run records reduced
  independence; neither alternatives nor critique counts as independently
  isolated corroboration. Hidden token/billing usage remained unavailable.
- One long Windows write hit an OS command-length error; smaller sequential
  artifact writes recovered without another model-runtime launch.

Final publication produced the partial report, result, source ledger, six stored
attempts and transition journal. The first structural check exposed a validator
bug (double task prefixes on already-scoped claim IDs) and a missing top-level
`gaps` array. The validator now handles local/scoped claim IDs exactly once,
with two regression assertions; host publication gaps were corrected without
changing worker records. The current check passes all three tasks/six attempts
and dispatch/publication/source-link checks. All three admitted records pass the
worker schema; **12 exact excerpts** occur in their underlying local source files.
The test coordinator also recorded matching source spans/digests and no observed
source drift. Those checks establish captured membership and identity, not truth
or independent live-system verification. The earlier failure remains recorded.

Full machine-local raw artifacts remain in the isolated temporary workspace;
they are intentionally excluded from this transferable package. The archive
includes the input fixtures, acceptance prompts and this qualification record.

## Remaining target qualification

- Codex custom-role file discovery on another computer has not been exercised;
  the host behavioral check uses native generic spawning with canonical prompts.
- Claude Code and OpenCode have candidate registration adapters and tested copy
  installation, but no native inference/retrieval run here. Claude documentation
  retrieval was blocked by the local organization's network policy.
- Large-corpus scaling, actual nested delegation, JEV pruning, crash/resume and
  held-out instruction optimization need the supplied acceptance prompts and a
  representative reviewed dataset. No optimizer quality gain is claimed.
- A one-thread fallback retains earlier role context. It tests serialized role
  execution, not independent specialist contexts. Fresh contexts remain required
  for evaluation blinding; role text does not enforce filesystem isolation.
