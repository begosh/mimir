# Mímir worker and host integration research

> Historical development snapshot. Local run/capture artifacts were cleared
> during workspace cleanup; use current setup docs and tests to reproduce behavior.

Date: 2026-10-22. Scope: replace fragile worker subprocess protocol handling with supported programmatic adapters; determine whether local MCP can replace the skill's shell execution and polling without duplicating the autonomous engine.

This note distinguishes documented capability, inspected release source, local read-only observations, and design decisions. No model inference, login flow, credential inspection, or host configuration changes were performed for this research. Product documentation is current and may change; tagged source and published release metadata qualify the implementation contracts below.

## Findings that change the implementation

1. **Codex has an official stable Python SDK.** `openai-codex` controls local app-server over JSON-RPC and pins a CLI runtime. Use its async thread/turn interface instead of rebuilding JSON-RPC or continuing to scrape `codex exec`. It still owns a local runtime process. [Codex SDK](https://developers.openai.com/codex/sdk), [0.163.0 Python reference](https://github.com/openai/codex/blob/rust-v0.163.0/sdk/python/docs/api-reference.md).
2. **Claude Agent SDK also owns a bundled local CLI.** Its tool availability, approval allowlist, deny list, hooks, structured output, and terminal result are different concepts. Treating `allowed_tools` as tool removal is incorrect. [0.2.172 README](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/README.md), [0.2.172 types](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/src/claude_agent_sdk/types.py).
3. **OpenCode 1.19.3 preserves the legacy HTTP routes alongside its newer modules.** Current repository organization and overview tables alone do not establish the request schema. The tagged generated OpenAPI document establishes model, variant, session permission, structured format, abort and deletion contracts. [1.19.3 OpenAPI](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/sdk/openapi.json).
4. **Antigravity now has a supported Python SDK, but documented authentication differs from AGY cached login.** The SDK documents Gemini API keys or Vertex credentials; the CLI documents cached credentials. Replacing AGY automatically would assume an unverified authentication equivalence. Preserve its CLI adapter for the existing native-login contract. [SDK quickstart](https://antigravity.google/docs/sdk/overview/), [CLI headless mode](https://antigravity.google/docs/cli/headless/).
5. **Local stdio MCP is documented across all four hosts.** It can replace skill-side shell invocation and transcript parsing, while the same Python engine continues to own graph execution and evidence. It does not eliminate worker runtime processes. [Codex MCP](https://developers.openai.com/codex/mcp), [Claude SDK MCP configuration](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/README.md), [OpenCode local MCP](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/web/src/content/docs/mcp-servers.mdx), [Antigravity MCP](https://antigravity.google/docs/mcp).
6. **Do not build this engine around host sampling or MCP experimental Tasks.** Sampling was an optional negotiated client capability in the 2025-11-25 specification, with a separate capability for tools. The current Python v2 migration guide additionally documents sampling deprecation and removal of experimental Tasks. Short tools returning durable run identifiers avoid those dependencies. [2025 sampling specification](https://modelcontextprotocol.io/specification/2025-11-25/client/sampling), [Python v2 migration](https://py.sdk.modelcontextprotocol.io/migration/).

## Version evidence

The installed harness versions were obtained with `--version`, without making worker calls:

| Harness/runtime | Local initial observation | Published release inspected |
| --- | --- | --- |
| Codex CLI | 0.163.0 | `openai-codex` 0.163.0; Python >=3.10 |
| Claude Code | 2.1.29 | `claude-agent-sdk` 0.2.172; Python >=3.10; Windows wheel bundles CLI 2.1.308 |
| OpenCode | 1.19.3 | tagged 1.19.3 generated OpenAPI |
| AGY | 1.4.4 | `google-antigravity` 0.1.22; Python >=3.10; Windows x64/ARM64 wheels exist |
| MCP Python SDK | initially absent in global Python | `mcp` 2.3.0; Python >=3.10 |

Published package versions and compatibility fields came from first-party package metadata: [openai-codex](https://pypi.org/pypi/openai-codex/json), [claude-agent-sdk](https://pypi.org/pypi/claude-agent-sdk/json), [google-antigravity](https://pypi.org/pypi/google-antigravity/json), [mcp](https://pypi.org/pypi/mcp/json). The bundled Claude version was read from `_cli_version.py` inside its published 0.2.172 Windows wheel, obtained using the distribution URL from that metadata. Initial package absence describes global Python, not the repository virtual environment after implementation installs dependencies.

The older system Claude CLI should not silently displace the SDK's newer bundled runtime. Both SDKs document bundled/pinned runtime defaults and intentional executable overrides. [Codex installation](https://developers.openai.com/codex/sdk), [Claude installation](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/README.md).

## Codex adapter contract

The release-qualified interface is `AsyncCodex` plus `CodexConfig`, `AsyncThread`, and `AsyncTurnHandle`:

```python
client = AsyncCodex(config=CodexConfig(cwd=workspace))
await client.start()
thread = await client.thread_start(
    model=selected_model,
    cwd=workspace,
    ephemeral=True,
    approval_mode=ApprovalMode.deny_all,
    sandbox=Sandbox.read_only,
    developer_instructions=research_guidance,
)
turn = await thread.turn(
    prompt,
    model=selected_model,
    effort=ReasoningEffort(selected_effort),
    output_schema=schema,
    approval_mode=ApprovalMode.deny_all,
    sandbox=Sandbox.read_only,
)
result = await turn.run()
```

The release reference explicitly describes `thread_start(... ephemeral=...)`, `run(... output_schema=...)`, `turn(...)`, turn-local `stream()`, `interrupt()`, and `run()`. `run()` is the convenience interface; a turn handle is appropriate when interruption is required. A sandbox supplied to a turn applies to that and later turns on the thread. [0.163.0 reference](https://github.com/openai/codex/blob/rust-v0.163.0/sdk/python/docs/api-reference.md).

Use `result.status` and `result.error` before trusting `final_response`; token usage is exposed as `usage.last.total_tokens`. Preserve final model output separately from transport errors, and validate the returned payload against Mímir's schema even when generation was constrained. SDK approval presets include `deny_all`; its wire mapping is `never`, while SDK defaults differ. Do not omit the explicit worker policy. [run result source](https://github.com/openai/codex/blob/rust-v0.163.0/sdk/python/src/openai_codex/_run.py), [approval mapping](https://github.com/openai/codex/blob/rust-v0.163.0/sdk/python/src/openai_codex/_approval_mode.py).

Authentication and model-provider configuration remain runtime-owned. App-server documents API key, managed ChatGPT sign-in, external-token and Bedrock modes. An adapter must not assume the hosting assistant has provided its current session credentials or selected endpoint to a new worker. Let the runtime read native configuration unless a caller explicitly supplies a supported override. An ephemeral worker thread and a Mímir durable run are separate things. [app-server authentication and thread lifecycle](https://developers.openai.com/codex/app-server).

The Python SDK owns transport startup, notifications and process teardown. Its async implementation wraps synchronous operations; cancellation during startup therefore needs deliberate cleanup of an operation that may finish late. Interrupt a known active turn, then close the client in cancellation-resistant cleanup. A stalled OS process launch has no public SDK cancellation handle; waiting for that launch before final cleanup can exceed the normal worker deadline. SDK 0.163.0's close implementation also leaves stdout/stderr pipe objects to garbage collection, producing ResourceWarning in local adapter tests. Do not promise that SDK process termination proves arbitrary independent descendants have stopped. [async implementation](https://github.com/openai/codex/blob/rust-v0.163.0/sdk/python/src/openai_codex/async_client.py), [client lifecycle](https://github.com/openai/codex/blob/rust-v0.163.0/sdk/python/src/openai_codex/client.py).

The read-only sandbox controls filesystem access. Remote MCP side effects retain their own configured permissions; a research prompt is guidance, not hard proof that every MCP operation is read-only. Codex exposes per-server tool allow/deny lists and approval modes, but the adapter must not describe an unchanged native MCP catalog as an enforced read-only catalog. [Codex MCP tool controls](https://developers.openai.com/codex/mcp), [SDK sandbox presets](https://developers.openai.com/codex/sdk).

Codex app-server stdio is the appropriate local transport. The official documentation explicitly calls WebSocket experimental and unsupported. `codex mcp-server` was removed; it is not a fallback worker interface. [app-server transports](https://developers.openai.com/codex/app-server), [SDK migration notice](https://developers.openai.com/codex/sdk).

## Claude adapter contract

Use `claude_agent_sdk.query()` for independent one-shot jobs, or `ClaudeSDKClient` when explicit interrupt and interactive lifecycle control justify it. The SDK transports structured messages rather than exposing only CLI stdout. [query source](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/src/claude_agent_sdk/query.py), [client source](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/src/claude_agent_sdk/client.py).

For version 0.2.172:

| Option/result | Meaning |
| --- | --- |
| `tools=[...]` | Select available built-in tools; `[]` disables all built-ins |
| `allowed_tools=[...]` | Preapprove listed tool calls; does not remove other tools |
| `disallowed_tools=[...]` | Remove the specified tools from model context |
| `permission_mode="dontAsk"` | Deny operations that are not already approved |
| `hooks={"PreToolUse": ...}` | Gate tool calls, including calls otherwise preapproved |
| `setting_sources=["user", "project", "local"]` | Explicitly load native settings and project instructions; `None` currently loads all sources |
| `extra_args={"no-session-persistence": None}` | Forward native boolean non-persistence flag |
| `verbatim_prompts=True` | Prevent assembled prompt text from dispatching slash commands or expanding `@path` mentions |
| `effort=...` | Supported model effort option; do not force unsupported levels onto every model |
| `output_format={"type": "json_schema", "schema": ...}` | Request structured generation |
| `ResultMessage.structured_output` | Parsed constrained result |
| `ResultMessage.is_error` | Terminal error indicator, regardless of whether partial text exists |
| `ResultMessage.api_error_status` | Structured HTTP diagnostic where available |

These semantics and fields are documented in the [tagged types](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/src/claude_agent_sdk/types.py). Native argument forwarding is in the [tagged transport](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/src/claude_agent_sdk/_internal/transport/subprocess_cli.py). CLI 2.1.29's local `mcp add --help` separately confirmed stdio, HTTP and SSE transports and local/user/project scopes; that observation does not qualify it for newer SDK options.

A `can_use_tool` callback alone cannot constrain preapproved tools: the SDK documents that it runs only when normal permission evaluation reaches `ask`. For a research-only worker, select read/search built-ins and apply a deny hook to unapproved MCP operations. Explicitly approved Work IQ `ask_work_iq` calls may be permitted; arbitrary MCP tools must not become approved because a server name sounds like a research server. Existing native deny settings still apply. [README warning and hook example](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/README.md), [callback warning source](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/src/claude_agent_sdk/types.py).

The SDK merges inherited environment and caller overrides while removing `CLAUDECODE`; it owns the subprocess. It also loads configured settings and preserves `apiKeyHelper` behavior in relevant resume flows. These are documented mechanisms for native runtime integration, not a claim that this user's current authentication works. Authentication must be reported from a real runtime result or preflight. No successful authenticated Claude worker call was made during this research. [environment handling](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/src/claude_agent_sdk/_internal/transport/subprocess_cli.py), [changelog: settings and authentication](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/CHANGELOG.md).

Interrupt and transport close are distinct. Current SDK source shields cleanup against async cancellation and documents cleanup contracts; result `terminal_reason` distinguishes completed and aborted work. Preserve ERROR/cancelled state rather than accepting partial assistant text. [query teardown](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/src/claude_agent_sdk/_internal/query.py), [changelog cancellation fixes](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/CHANGELOG.md).

## OpenCode adapter contract

Run a dedicated `opencode serve` process on loopback, using an ephemeral port and a generated per-process Basic-auth password. The official server docs establish `OPENCODE_SERVER_PASSWORD`, default username `opencode`, and optional `OPENCODE_SERVER_USERNAME`. The official JavaScript SDK launcher establishes the port-zero startup/readiness pattern; Python can perform the same supported HTTP operations directly. [server documentation source](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/web/src/content/docs/server.mdx), [SDK launcher](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/sdk/js/src/server.ts).

Use dedicated disposable storage instead of attaching to a user's interactive server. Native configuration and authentication need separate handling from conversation persistence; do not mutate provider login or global configuration through HTTP. The v1.19.3 generated schema establishes these exact routes:

| Operation | Verified interface |
| --- | --- |
| `GET /global/health` | `{healthy: true, version: string}` |
| `GET /config` | Native effective configuration; inspect necessary policy fields without printing credential-bearing content |
| `POST /session` | Creates owned session; accepts `permission` as a `PermissionRuleset` |
| `POST /session/{sessionID}/message` | Waits for terminal response; accepts model `{providerID, modelID}`, optional `variant`, `parts`, and `format` |
| `POST /session/{sessionID}/abort` | Abort owned session |
| `DELETE /session/{sessionID}` | Delete owned session and its data |

`PermissionRuleset` on these routes uses `{permission, pattern, action}` entries, with action allow/deny/ask. `format` uses `{type: "json_schema", schema: ..., retryCount?: ...}`. The response is `{info, parts}`; `info.error` must be checked, `info.structured` is the structured payload, `info.tokens` carries usage, and text parts carry unconstrained output. A valid HTTP 200 envelope is not proof of a successful worker finding. [tagged OpenAPI schemas](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/sdk/openapi.json).

The repository also contains newer permission types `{action, resource, effect}`. Do not send those to the legacy route because they look equivalent. Tagged source preserves configuration order and uses last matching rule in permission evaluation. Broad worker defaults followed by allowances must therefore reapply native restrictions in the correct order; unrestricted arbitrary MCP tools must not be implicitly allowed. [legacy config conversion](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/core/src/v1/config/migrate.ts), [order preservation](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/core/src/v1/config/permission.ts), [legacy evaluation](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/permission/index.ts).

Legacy tool execution explicitly merges `agent.permission` followed by `session.permission`, so supplied session rules override matching agent rules. Runtime-approved rules are subsequently considered, which is another reason to use a fresh dedicated instance and never grant interactive approvals. Sending the deprecated prompt `tools` map replaces the entire session permission array; omit it when creating a session with explicit rules. `StructuredOutput` is injected after ordinary tool resolution and its synthetic function does not call the normal permission gate. [tool ruleset construction](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/session/tools.ts), [prompt permission replacement and output tool injection](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/session/prompt.ts), [legacy permission evaluation](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/permission/index.ts).

On timeout or cancellation, abort before deleting an owned session and stop the dedicated process. Cleanup failure is a separate failure, not proof of deletion. Use bounded requests, disable proxy inheritance for loopback requests, and never follow endpoint redirects with authentication or prompts. The latter are adapter design decisions needed to keep a local configured transport local, not promises made by the overview documentation.

## Antigravity: supported SDK and retained native-login adapter

`google-antigravity` 0.1.22 exposes `Agent`, `LocalAgentConfig`, tools, hooks, policies, output schemas and cancellation. The documented SDK is a local Go-based harness with Python lifecycle management; it is not a pure network-free library. [SDK overview](https://antigravity.google/docs/sdk/overview/), [0.1.22 configuration](https://github.com/google-antigravity/antigravity-sdk-python/blob/v0.1.22/google/antigravity/connections/local/local_connection_config.py), [0.1.22 connection](https://github.com/google-antigravity/antigravity-sdk-python/blob/v0.1.22/google/antigravity/connections/local/local_connection.py).

The SDK quickstart explicitly configures `GEMINI_API_KEY`; Vertex uses project/location and Google credentials. Configured endpoints support Gemini and Vertex models. No fetched official source established that an SDK agent automatically reuses AGY CLI cached-login authentication, its plan quota or its selected model. That is an explicit unresolved equivalence, not evidence of no SDK. Preserve `agy` for users relying on existing native login; a separately selected SDK adapter would require its own supported authentication contract. [SDK quickstart](https://antigravity.google/docs/sdk/overview/), [CLI cached-login behavior](https://antigravity.google/docs/cli/headless/).

The existing CLI adapter can still improve: local AGY 1.4.4 `--help` confirms `--output-format json`, `--json-schema`, `--effort`, `--input-format stream-json`, and `--print-timeout`. Official headless docs specify a terminal JSON envelope with `status`, `response`, optional `structured_output`, `error`, and `usage.total_tokens`. Check envelope status and prefer `structured_output` when a schema was requested. Text stdout alone discards this terminal status and metadata. [headless output specification](https://antigravity.google/docs/cli/headless/).

Headless documentation states cached credentials are used and unauthenticated noninteractive runs fail instead of hanging. The same documentation describes stdout response/stderr diagnostics and streaming input; those claims still need version-qualified local tests before depending on every detail. AGY's permissions differ by OS, and the official guide calls out Windows's previous system. Never infer Windows containment guarantees from Linux documentation. [headless mode](https://antigravity.google/docs/cli/headless/), [permissions and Windows differences](https://antigravity.google/docs/permissions/).

The SDK supports explicit read-only built-in tool groups and MCP connection configuration, Pydantic/JSON schema output, and `response.cancel()`. These establish a viable future adapter when authentication is selected deliberately. [tools](https://antigravity.google/docs/sdk/tools/), [MCP](https://antigravity.google/docs/sdk/mcp/), [structured output](https://antigravity.google/docs/sdk/structured-output/), [cancel source](https://github.com/google-antigravity/antigravity-sdk-python/blob/v0.1.22/google/antigravity/types.py).

## Host MCP seam

MCP belongs at the hosting assistant → Mímir engine seam. Worker adapters remain behind `BaseSwarmBackend.spawn()`. A run module can hide execution, journaling, status, cancellation, result retrieval and cleanup behind a small interface, used equally by CLI and MCP. These are design decisions applying the invoked codebase-design skill; MCP does not dictate Mímir's run state or graph semantics.

Prefer short calls: start returns a run identifier; status returns truthful stages and terminal state; cancel requests cancellation; result retrieves a completed report and artifact references. Keep journal ownership and leases independent of the MCP connection, so host reconnection does not invent completed state or start a second engine for an active run. Host termination, stale ownership and worker cleanup failure must remain distinguishable. Do not claim durable continuation without actually implementing and testing the corresponding recovery semantics.

The baseline stdio protocol requires UTF-8 newline-delimited JSON-RPC. Only valid protocol messages may reach stdout; diagnostics belong on stderr. MCP tool output schemas govern server-produced data and are different from model generation schemas. `structuredContent` should be accompanied by serialized text for older clients; tool execution failures use `isError`, and annotations are hints rather than trustworthy enforcement. [stdio transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [tool output specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

In Python MCP 2.3.0, `MCPServer` replaces `FastMCP`; Python model fields use snake_case, transport-specific options moved to `run()`, sync handlers run on worker threads, and the package depends on `httpx2`. Tests and imports must exercise the pinned release. Its `stdio_server()` protects the wire using private descriptors and redirects stray stdout, but explicitly avoiding engine console output is still the clearest integration. [v2.3.0 README](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/README.md), [migration guide](https://py.sdk.modelcontextprotocol.io/migration/), [stdio source](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/stdio.py).

### Local host configuration examples

The examples below are configuration shapes, not changes to this user's installed hosts. Replace executable/script/workspace paths with the actual installed location. Absolute executable and script paths avoid dependence on whichever directory the host starts in.

Codex `~/.codex/config.toml` or trusted project `.codex/config.toml`:

```toml
[mcp_servers.mimir]
command = "C:/path/to/mimir/.venv/Scripts/python.exe"
args = ["C:/path/to/mimir/scripts/mcp_server.py"]
cwd = "C:/path/to/project"
```

These fields are directly documented by [Codex MCP configuration](https://developers.openai.com/codex/mcp).

Claude project `.mcp.json`:

```json
{"mcpServers":{"mimir":{"type":"stdio","command":"C:/path/to/mimir/.venv/Scripts/python.exe","args":["C:/path/to/mimir/scripts/mcp_server.py"]}}}
```

The stdio command/argument shape is documented by the [Claude SDK README](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/README.md) and confirmed in installed Claude Code's `mcp add --help`. Runtime policy and project trust remain host-owned.

OpenCode `opencode.jsonc`:

```json
{"mcp":{"mimir":{"type":"local","command":["C:/path/to/mimir/.venv/Scripts/python.exe","C:/path/to/mimir/scripts/mcp_server.py"],"cwd":"C:/path/to/project","enabled":true}}}
```

The command array, working directory and local transport fields are documented by [OpenCode 1.19.3 MCP configuration](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/web/src/content/docs/mcp-servers.mdx).

Antigravity/AGY `.agents/mcp_config.json` or `~/.gemini/config/mcp_config.json`:

```json
{"mcpServers":{"mimir":{"command":"C:/path/to/mimir/.venv/Scripts/python.exe","args":["C:/path/to/mimir/scripts/mcp_server.py"],"cwd":"C:/path/to/project"}}}
```

The global/workspace paths and stdio fields are documented by [Antigravity MCP](https://antigravity.google/docs/mcp). Remote configurations use `serverUrl`, not `url`/`httpUrl`; local stdio avoids that distinction.

### Sampling is not inherited host execution

In the 2025 specification, clients choose whether to advertise sampling; servers cannot assume it. Sampling model hints do not force the client's exact model or provider, tool-enabled sampling requires its own capability, and tools are supplied in the sampling request rather than guaranteed to be the host's complete configured catalog. `includeContext=thisServer/allServers` was already soft-deprecated. [sampling specification](https://modelcontextprotocol.io/specification/2025-11-25/client/sampling), [capability negotiation](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

The current v2 migration guide further documents roots/sampling/logging deprecation and no server back channel in 2026-era connections, plus removal of experimental Tasks. Mímir should expose ordinary tools and own its run lifecycle, not rely on unverified host sampling support to remove worker runtimes. [Python v2 migration](https://py.sdk.modelcontextprotocol.io/migration/).

## Validation obligations and remaining uncertainty

The contracts above support implementation, but they do not establish successful authenticated execution on this machine. Required verification should exercise the adapter interface with meaningful lifecycle, nonempty-result, schema, timeout, cancellation and cleanup tests, then perform read-only startup/health/tool-discovery checks on the installed runtimes. No need to call a model merely to verify JSON serialization or OpenAPI shape.

Use controlled fakes for terminal worker errors and cleanup races; protocol tests should traverse a real MCP stdio client/server connection. A clean stdio handshake does not prove every host was reconfigured or that all downstream credentials work. Record those limits in delivery notes. Native endpoint configuration must remain runtime-owned so an old saved thread/provider override cannot be silently injected by Mímir's adapter.

Open questions remain explicit: AGY SDK/native-login equivalence; account-specific model availability; success of this machine's Claude authentication; Claude's synthetic structured-output tool name when combining a deny hook with constrained generation (first-party tests verify generation, not that hook combination); hard read-only filtering of arbitrary Codex MCP operations; independent tool-process descendants after SDK shutdown; host-specific reattachment behavior beyond the tested journal/lease recovery contract. None of these should be converted into a confirmed capability by the adapter or final report. [Claude structured-output tests](https://github.com/anthropics/claude-agent-sdk-python/blob/v0.2.172/e2e-tests/test_structured_output.py).
