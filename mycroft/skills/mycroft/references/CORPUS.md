# Bounded corpus analysis

Use for evidence that exceeds a useful single-agent input or requires connecting
scattered records. Small captured evidence can use the ordinary investigator.
The native tools replace the RLM inspection environment; there is no generated
code interpreter, DSPy nested predictor or retained program state.

1. **Capture/index.** Enumerate authorized files/documents, stable source IDs,
   retrieval type/time, measured length when available, revision, content
   identity and locator. Use frozen copies for change-prone sources when file
   writes are available. Record encoding/parsing limitations. Do not normalize
   away revision dates, tables, headings or source boundaries.
   Index IDs (`corpus:<document>:<revision>`) identify corpus entries, not worker
   citations. On retrieval, mint a task-prefixed citation ID and record the index
   ID-to-citation ID mapping in `sources.json`. Worker records preserve their
   citation IDs across dependencies; never use an index ID as a citation namespace.
2. **Inspect cheaply.** Search literal terms and metadata using native tools
   (`rg` or equivalent for local text). A hit is a locator, not the answer.
   Open bounded spans including surrounding headers/context. Mark searched,
   actually read and untouched scopes separately. Avoid sending the whole
   corpus to every worker or admitting the first prefix as the whole source.
3. **Partition by question.** Assign a bounded question and source slices to a
   corpus worker. Partition by source when independent; partition by entity or
   question when cross-source joins matter. Include IDs/revisions required for
   joining; overlapping spans are allowed and accounted for. Respect task and
   input limits before dispatch. Unparseable PDFs/binaries require an available
   approved extractor; absent tools produce a gap, not a Python fallback.
4. **Reduce/recurse.** Worker returns the evidence contract and any unresolved
   bounded questions. The host decides whether to reread, assign a new task or
   follow up. Default root depth zero, workers depth one, no grandchildren.
   `max_rounds=2` bounds further analysis waves; every dispatched request shares
   the original global limits. Stop when the question is resolved from evidence,
   only unsupported possibilities remain, or a budget is exhausted.
5. **Join evidence.** Combine source/claim graphs using stable keys and revision
   identities. Reopen the spans supporting a cross-source inference; expose
   join ambiguity. Missing keys do not imply absent entities. Account for every
   indexed partition as read, searched-only or unread.
6. **Challenge/extract.** Critic checks the joined material claims and coverage.
   Host extracts the final answer from admitted claims and records unread scope.
   Compression must retain qualifiers, conflicting values, locators and links.
   Failed/denied required reads cannot disappear during final extraction.

Large individual files can be inspected through bounded native line/page reads;
the source stays outside model context. If the harness only supports whole-file
admission, require a smaller captured slice or explicitly report unsupported
inspection. Do not promise arbitrarily large corpora or complete coverage from
search alone. An output overflow requires a narrower record or partition, never
silent JSON clipping.

For benchmark or other sealed evaluation, investigators receive **only** the
case's assigned evidence/objective. Do not give them the dataset path containing
expected answers or a filesystem scope that exposes the grader files. Use a
separate workspace and an actual permission boundary where available. A fresh
agent context alone prevents accidental prompt leakage, not file access.
