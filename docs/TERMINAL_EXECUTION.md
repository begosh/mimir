# Terminal execution

Use the same engine when Mímir MCP is unavailable. Diagnose an existing MCP
failure before choosing this route; do not run both frontends against one run.

The interpreter needs requirements-workers.txt for native SDK/MCP workers.
Write a self-contained UTF-8 objective to a unique file. Use unique checkpoint
and report paths. Add --skip-web for local/private objectives or a separate
public --search-query hint; never publish the complete private objective as a query.
Planning never performs preliminary web search. Optional --task-brief accepts a
compact JSON interpretation containing outcome, constraints, components,
evidence_needs and missing_information. The latter four fields are string arrays.
Without a host brief, focused workers interpret before tools; swarm's existing
planning call produces the brief and tasks. No extra planning call for single.

For the explicit recursive planner, add `--mode swarm --recursive-plan --depth 3
--max-tasks 12`. Planning first interprets, then recursively splits non-atomic
components. `--planning-budget` accepts a JSON object with `max_calls`,
`max_seconds`, `max_nodes`. Use `--phase plan` to inspect the interpretation and
leaf contracts before execution. The sidecar `checkpoint.planning.json` retains
partial work and call accounting on failure. Missing user choices stop execution;
clarify and create a new plan. Simple focused requests retain the cheaper path.

```powershell
python -u <skill-dir>/scripts/mimir.py --goal-file artifacts/review-goal.txt --backend codex --model <agreed-model> --effort low --mode review --max-tasks 4 --skip-web --progress jsonl --phase plan --state-file artifacts/review-state.json --output artifacts/review-report.md
python -u <skill-dir>/scripts/mimir.py --phase execute --state-file artifacts/review-state.json --progress jsonl
python -u <skill-dir>/scripts/mimir.py --phase synthesize --state-file artifacts/review-state.json --progress jsonl
```

Reuse persisted settings on resume. --mode single needs only one model call;
--mode swarm opts into bounded model planning. --jev opts into heuristic
pruning. --memory off|read|write defaults to read; write saves candidates only.
--diagnostics --backend codex inspects paths/dependencies/credential presence
without inference. --max-context-chars controls context admission.

Poll the same process session every 10–20 seconds with short tool yields. In
Codex this is exec_command then write_stdin; an orchestrating functions cell
has its own identifier. Translate observed JSONL events into concise chat
updates every 30–45 seconds. No raw event walls or reasoning dumps.

Each invocation's sequence starts at one. Ready events describe saved
checkpoints/artifacts; plan_completed, execute_completed and run_completed
follow awaited cleanup. Require both the completion event and successful process
exit before advancing. Waiting events prove liveness, not new findings.

On failure, retain settings and inspect the safe diagnostic. Execute retries
reuse completed tasks only when retained inputs and output identities match;
changed inputs require an explicit new plan. Synthesis recovery validates the
existing publication and avoids additional model/learning calls. Legacy
checkpoints without transport metadata retain CLI transport unless explicitly
overridden. Do not unlink leases while an owner may hold them.

After successful synthesis, read the complete Markdown report and JSON sidecar.
Source locators and model support labels still require independent assessment.
--phase all is available for standalone execution through the same engine.
