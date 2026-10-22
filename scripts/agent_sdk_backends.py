"""Native worker protocols behind the existing ``spawn`` interface.

Claude uses a fresh Agent SDK query and its bundled runtime. OpenCode uses a
privately authenticated, owned headless server in disposable session storage.
Neither adapter attaches to, resumes, or removes a user's existing sessions.
Optional dependencies are imported only when their adapter is selected.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing, suppress
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
from typing import Any, Callable, Dict, Optional

from backend import (BaseSwarmBackend, RESEARCH_TOOL_GUIDANCE, SwarmResult,
                     WorkerCleanupError, claude_research_tools,
                     disposable_cli_env, has_worker_result, worker_diagnostic)


_READ_TOOLS = ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]
_MUTATION_TOOLS = ["Bash", "Edit", "Write", "NotebookEdit", "Task", "Agent", "Skill"]
_OPENCODE_QUERIES = ["read", "glob", "grep", "webfetch", "websearch", "*_ask_work_iq"]


class _SchemaError(ValueError):
    pass


async def _release_environment(environment: Any, root: Path, timeout: float) -> None:
    """Retry Windows handle-release races only in our verified disposable root."""
    try:
        environment.__exit__(None, None, None)
        return
    except PermissionError:
        pass
    resolved = root.resolve()
    if resolved.parent != Path(tempfile.gettempdir()).resolve() or not resolved.name.startswith("mimir_opencode_"):
        raise WorkerCleanupError("Refusing cleanup outside the owned OpenCode temporary root.")
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        try:
            if resolved.exists():
                shutil.rmtree(resolved)
            return
        except PermissionError:
            if asyncio.get_running_loop().time() >= deadline:
                raise WorkerCleanupError("Owned OpenCode temporary storage remains locked after process shutdown.") from None
            await asyncio.sleep(.05)


def _prompt(prompt: str, role: str, input_data: Any) -> str:
    result = (f"You are a Mimir micro-worker ({role}). Solve only this task. "
              f"Do not launch Mimir or delegate.\n\n{RESEARCH_TOOL_GUIDANCE}\n{prompt}")
    if input_data is not None:
        result += "\n\nINPUT DATA:\n" + json.dumps(input_data, ensure_ascii=False)
    return result


def _validate_schema(value: Any, schema: Optional[Dict[str, Any]]) -> None:
    if schema is None:
        return
    try:
        jsonschema = importlib.import_module("jsonschema")
    except ImportError:
        raise RuntimeError("Structured worker output requires the jsonschema dependency.") from None
    try:
        validator = jsonschema.validators.validator_for(schema)
        validator.check_schema(schema)
        validator(schema).validate(value)
    except (jsonschema.ValidationError, jsonschema.SchemaError):
        raise _SchemaError("Worker output does not satisfy the requested JSON schema.") from None


def _tokens(usage: Any, input_key: str, output_key: str) -> int:
    if not isinstance(usage, dict):
        return 0
    return sum(int(value) for key in (input_key, output_key)
               if isinstance((value := usage.get(key)), (int, float)) and value >= 0)


def _claude_error(value: Any) -> str:
    """Classify SDK fields privately and return only fixed actionable text."""
    status = getattr(value, "api_error_status", None)
    if status == 401:
        return "Claude SDK worker failed: authentication failed (HTTP 401); check Claude Code login or configured provider credentials."
    if status == 403:
        return "Claude SDK worker failed: access denied (HTTP 403); check the configured provider and existing permissions."
    if status == 429:
        return "Claude SDK worker failed: provider rate limit reached (HTTP 429); wait before retrying."
    if isinstance(status, int):
        return f"Claude SDK worker failed: HTTP {status}; check the configured provider and connectivity."
    subtype = getattr(value, "subtype", None)
    limits = {"error_max_turns": "maximum worker turns reached",
              "error_max_budget_usd": "maximum worker cost reached",
              "error_max_structured_output_retries": "structured output generation failed"}
    if subtype in limits:
        return f"Claude SDK worker failed: {limits[subtype]}."
    # These strings can contain prompts/credentials. Classification uses them
    # locally; worker_diagnostic returns templates without copying their text.
    diagnostic = "\n".join(str(item) for item in (getattr(value, "errors", None) or [])
                            if isinstance(item, str))
    diagnostic += "\n" + str(getattr(value, "result", None) or "")
    diagnostic += "\n" + str(getattr(value, "stderr", None) or "")
    if isinstance(value, BaseException):
        diagnostic += "\n" + str(value)
    name = type(value).__name__
    if name == "CLIConnectionError":
        return "Claude SDK worker failed: runtime connection failed; check the bundled runtime and configured provider."
    if name == "CLIJSONDecodeError":
        return "Claude SDK worker failed: invalid runtime protocol response; update the SDK and its bundled runtime."
    return worker_diagnostic("Claude SDK", diagnostic, code=getattr(value, "exit_code", None),
                             error=value if isinstance(value, BaseException) else None)


class ClaudeAgentSDKBackend(BaseSwarmBackend):
    """One-shot Claude SDK queries, native settings and no session persistence.

    SDK lifecycle and cancellation stay inside one AnyIO task. Cancelling the
    caller signals an AnyIO cancel scope, rather than cancelling the SDK's raw
    asyncio task while it is closing its subprocess. The supported bundled
    runtime is the default; an explicit runtime must support verbatim prompts.
    """

    def __init__(self, default_model: str = "haiku", default_effort: str = "low",
                 claude_path: Optional[str] = None, max_concurrency: int = 4,
                 *, sdk: Any = None):
        super().__init__(default_model, max_concurrency)
        self.default_effort = default_effort
        self.claude_path = claude_path
        self._sdk = sdk
        self.transport = "sdk"
        self._closed = False
        self._running: Dict[asyncio.Task, Any] = {}
        # The supported SDK may spend up to 20s escalating subprocess shutdown.
        self.cleanup_timeout_seconds = 25
        self.session_policy = "fresh Agent SDK query; native --no-session-persistence"
        self.research_tool_policy = "Native Claude settings/MCP; query tools with fail-closed mutation hook"

    def _load_sdk(self) -> Any:
        if self._sdk is None:
            try:
                self._sdk = importlib.import_module("claude_agent_sdk")
            except ImportError:
                raise RuntimeError("Claude SDK transport requires claude-agent-sdk>=0.2.172,<0.3; install the optional worker dependency.") from None
        return self._sdk

    def _options(self, model: str, effort: str, schema: Optional[Dict[str, Any]]) -> Any:
        sdk = self._load_sdk()
        queries = set(_READ_TOOLS + claude_research_tools())

        async def query_only_hook(value: Any, tool_use_id: Any, context: Any) -> Dict[str, Any]:
            # Empty output leaves native deny/ask rules in force. Never return
            # an allow decision: that would bypass existing permission checks.
            name = value.get("tool_name") if isinstance(value, dict) else None
            if name in queries or (schema is not None and name == "StructuredOutput"):
                return {}
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": "Mimir workers may only use approved read/query tools."}}

        values: Dict[str, Any] = {
            "model": model, "cwd": str(Path.cwd()), "tools": list(_READ_TOOLS),
            "allowed_tools": sorted(queries), "disallowed_tools": list(_MUTATION_TOOLS),
            "permission_mode": "dontAsk", "setting_sources": ["user", "project", "local"],
            "verbatim_prompts": True,
            "extra_args": {"no-session-persistence": None, "disable-slash-commands": None},
            "hooks": {"PreToolUse": [sdk.HookMatcher(hooks=[query_only_hook])]},
        }
        if self.claude_path:
            values["cli_path"] = self.claude_path
        # Haiku has no adjustable reasoning effort; keep the selected model.
        if "haiku" not in model.lower() and effort != "none":
            values["effort"] = effort
        if schema is not None:
            values["output_format"] = {"type": "json_schema", "schema": schema}
        try:
            return sdk.ClaudeAgentOptions(**values)
        except (TypeError, AttributeError):
            raise RuntimeError("Claude SDK is missing required worker controls; install claude-agent-sdk>=0.2.172,<0.3.") from None

    async def check_cli(self) -> Dict[str, Any]:
        if self._closed:
            raise RuntimeError("Claude SDK backend is closed.")
        self._options(self.default_model, self.default_effort, None)
        if self.claude_path:
            code, stdout, _ = await self._run_cli([self.claude_path, "--version"])
            match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", stdout)
            if code or match is None or tuple(map(int, match.groups())) < (2, 1, 248):
                raise RuntimeError("Explicit Claude runtime must be version 2.1.248 or newer for verbatim worker prompts; use the SDK bundled runtime.")
        return {
            "backend": self.__class__.__name__, "transport": "sdk",
            "model": self.default_model, "model_configured": True,
            "effort": "not adjustable for Haiku" if "haiku" in self.default_model.lower() else self.default_effort,
            "session_policy": self.session_policy, "research_tools": self.research_tool_policy,
            "timeout_seconds": self.timeout_seconds,
            "runtime": self.claude_path or "SDK bundled Claude Code",
        }

    async def _query(self, text: str, options: Any) -> Any:
        if self._closed:
            raise RuntimeError("Claude SDK backend is closed.")
        anyio = importlib.import_module("anyio")
        scope = anyio.CancelScope()
        task = asyncio.current_task()
        self._running[task] = scope
        try:
            with scope:
                with anyio.fail_after(self.timeout_seconds):
                    result = None
                    # Complete consumption and closure take place in the same
                    # task as the SDK's nested AnyIO cancel scopes.
                    try:
                        async with aclosing(self._load_sdk().query(prompt=text, options=options)) as messages:
                            async for message in messages:
                                if isinstance(message, self._load_sdk().ResultMessage):
                                    result = message
                    except Exception as exc:
                        # SDK emits a failed terminal ResultMessage and then
                        # raises ResultError on the runtime's nonzero exit.
                        # Keep the structured terminal evidence in that case.
                        result_error = getattr(self._load_sdk(), "ResultError", None)
                        if result is None or result_error is None or not isinstance(exc, result_error):
                            raise
                        if not result.is_error:
                            raise
                    return result
            raise asyncio.CancelledError
        finally:
            self._running.pop(task, None)

    async def _cancel_query(self, task: asyncio.Task) -> None:
        # A task may have been cancelled by its caller before entering _query.
        await asyncio.sleep(0)
        scope = self._running.get(task)
        if scope is not None:
            scope.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), self.cleanup_timeout_seconds)
        except asyncio.CancelledError:
            if not task.done():
                raise
        except asyncio.TimeoutError:
            raise WorkerCleanupError("Claude SDK cleanup deadline exceeded.") from None
        except Exception:
            if not task.done():
                raise

    async def spawn(self, prompt: str, role: str = "Micro-Worker", model: Optional[str] = None,
                    effort: Optional[str] = None, json_schema: Optional[Dict[str, Any]] = None,
                    input_data: Any = None) -> SwarmResult:
        async with self.semaphore:
            start = asyncio.get_running_loop().time()
            def failure(message: str) -> SwarmResult:
                return SwarmResult(role, "ERROR", None, message, asyncio.get_running_loop().time() - start)
            task = None
            try:
                if self._closed:
                    raise RuntimeError("Claude SDK backend is closed.")
                options = self._options(model or self.default_model, effort or self.default_effort, json_schema)
                task = asyncio.create_task(self._query(_prompt(prompt, role, input_data), options))
                message = await asyncio.shield(task)
                if message is None or message.is_error or message.subtype != "success":
                    return failure(_claude_error(message) if message is not None else "Claude SDK worker failed: absent terminal result.")
                content = message.structured_output if message.structured_output is not None else message.result
                if json_schema is not None and message.structured_output is None:
                    return failure("Claude SDK returned no structured result for the requested schema.")
                if not has_worker_result(content):
                    return failure("Claude SDK returned no usable result.")
                raw = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                data = self.parse_json_from_text(raw)
                _validate_schema(data, json_schema)
                if not has_worker_result(data):
                    return failure("Claude SDK returned no usable result.")
                return SwarmResult(role, "SUCCESS", data, raw,
                                   asyncio.get_running_loop().time() - start,
                                   _tokens(message.usage, "input_tokens", "output_tokens"))
            except asyncio.CancelledError:
                if task is not None:
                    await self._cancel_query(task)
                raise
            except RuntimeError as exc:
                # Only our actionable dependency/runtime messages are exposed.
                if str(exc).startswith(("Claude SDK transport requires", "Claude SDK is missing", "Claude SDK backend is closed", "Structured worker output requires")):
                    return failure(str(exc))
                return failure(_claude_error(exc))
            except _SchemaError:
                return failure("Claude SDK output does not satisfy the requested JSON schema.")
            except Exception as exc:
                return failure(_claude_error(exc))

    async def aclose(self) -> None:
        self._closed = True
        tasks = list(self._running)
        await asyncio.gather(*(self._cancel_query(task) for task in tasks))

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()


def _permission_rules(config: Any) -> list[Dict[str, str]]:
    """Intersect native OpenCode rules with the worker's query-only policy.

    Preserve native rule order, path denials and specific query grants after
    wildcard denials. Native wildcard grants must never enable mutation tools.
    'ask' becomes deny because workers cannot prompt for permissions.
    """
    rules = [{"permission": "*", "pattern": "*", "action": "deny"}]
    rules.extend({"permission": name, "pattern": "*", "action": "allow"}
                 for name in _OPENCODE_QUERIES)
    if isinstance(config, str):
        config = {"*": config}
    if not isinstance(config, dict):
        raise ValueError("Invalid native OpenCode permissions.")
    for permission, value in config.items():
        is_query = permission in _OPENCODE_QUERIES or permission.endswith("_ask_work_iq")
        choices = value.items() if isinstance(value, dict) else [("*", value)]
        for pattern, action in choices:
            if action not in ("allow", "deny", "ask"):
                raise ValueError("Invalid native OpenCode permission action.")
            if action == "allow" and not is_query:
                continue
            rules.append({"permission": permission, "pattern": pattern,
                          "action": "deny" if action == "ask" else action})
    return rules


async def _stop_process(proc: Any, timeout: float) -> None:
    """Terminate the owned headless server and its process tree before disposal."""
    if proc is None:
        return
    failed = False
    if os.name == "nt" and getattr(proc, "pid", None):
        kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.DEVNULL, "stderr": asyncio.subprocess.DEVNULL,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        }
        suinfo = subprocess.STARTUPINFO()
        suinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        suinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = suinfo
        killer = None
        try:
            killer = await asyncio.wait_for(asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(proc.pid), "/T", "/F", **kwargs), timeout)
            await asyncio.wait_for(killer.wait(), timeout)
            failed = bool(killer.returncode) and proc.returncode is None
        except (OSError, asyncio.TimeoutError):
            failed = proc.returncode is None
            if killer is not None and killer.returncode is None:
                with suppress(ProcessLookupError):
                    killer.kill()
    elif getattr(proc, "pid", None):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            failed = True
    if proc.returncode is None:
        with suppress(ProcessLookupError):
            proc.kill()
    try:
        await asyncio.wait_for(proc.wait(), timeout)
    except asyncio.TimeoutError:
        failed = True
    if failed:
        raise WorkerCleanupError("OpenCode headless server process-tree cleanup could not be confirmed.")


class OpenCodeServerBackend(BaseSwarmBackend):
    """OpenCode's supported HTTP protocol on an isolated, owned local server.

    The only CLI calls are native configuration discovery and starting/stopping
    the server. Every worker uses an independent HTTP session. ``aclose`` must
    be awaited to abort workers, reap the process and release disposable storage.
    ``http_client`` is an internal seam for protocol tests, never a CLI attach
    option. The adapter owns only sessions it creates, even with that seam.
    """

    def __init__(self, default_model: Optional[str] = None, default_effort: str = "low",
                 opencode_path: Optional[str] = None, max_concurrency: int = 4,
                 *, http_client: Any = None, client_factory: Optional[Callable] = None):
        if not default_model or "/" not in default_model:
            raise ValueError("OpenCode requires an explicit provider/model via --model or MIMIR_OPENCODE_MODEL.")
        super().__init__(default_model, max_concurrency)
        self.default_effort = default_effort
        self.transport = "server"
        self.opencode_path = opencode_path or shutil.which("opencode")
        if not self.opencode_path and http_client is None:
            raise FileNotFoundError("Could not find 'opencode' in PATH.")
        self._client = http_client
        self._injected_client = http_client is not None
        self._client_factory = client_factory
        self._process = None
        self._environment = None
        self._environment_root = None
        self._drainer = None
        self._start_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._closed = False
        self._configured = http_client is not None
        self._native_permissions: Any = {}
        self._agent_permissions: Any = {}
        self._owned_sessions: set[str] = set()
        self._workers: set[asyncio.Task] = set()
        self.startup_timeout_seconds = 30
        self.discovery_timeout_seconds = 30
        self.session_policy = "owned HTTP sessions in disposable XDG/home storage; no attach/resume/share"
        self.research_tool_policy = "Native OpenCode MCP/config; query-only session rules preserve native denials"

    async def _discover_config(self) -> None:
        if self._configured:
            return
        auth = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "opencode" / "auth.json"
        if not auth.exists():
            raise RuntimeError("OpenCode needs reusable auth.json login storage; DB-only credentials cannot be copied without conversations.")
        environment = disposable_cli_env("opencode")
        env = environment.__enter__()
        root = Path(env["HOME"])
        try:
            inline = json.loads(os.environ.get("OPENCODE_CONFIG_CONTENT") or "{}")
            inline.update({"share": "disabled", "autoupdate": False})
            env["OPENCODE_CONFIG_CONTENT"] = json.dumps(inline)
            env.update(OPENCODE_DISABLE_MODELS_FETCH="1", OPENCODE_DISABLE_LSP_DOWNLOAD="1",
                       OPENCODE_DISABLE_DEFAULT_PLUGINS="1")
            try:
                code, stdout, _ = await asyncio.wait_for(self._run_cli(
                    [self.opencode_path, "debug", "config"], env=env), self.discovery_timeout_seconds)
            except asyncio.TimeoutError:
                raise RuntimeError("OpenCode native configuration discovery timed out; check configured plugins/MCP connectivity or increase the discovery timeout.") from None
        finally:
            await _release_environment(environment, root, self.cleanup_timeout_seconds)
        try:
            config = json.loads(stdout)
            permissions = config.get("permission", {})
            _permission_rules(permissions)
            agents = config.get("agent", {})
            build = agents.get("build", {}) if isinstance(agents, dict) else {}
            agent_permissions = build.get("permission", {}) if isinstance(build, dict) else {}
            _permission_rules(agent_permissions)
            if code:
                raise ValueError("Configuration discovery failed.")
        except (ValueError, TypeError, AttributeError):
            raise RuntimeError("Cannot resolve native OpenCode research permissions; repair its configuration.") from None
        self._native_permissions = permissions
        self._agent_permissions = agent_permissions
        self._configured = True

    async def check_cli(self) -> Dict[str, Any]:
        if self._closed:
            raise RuntimeError("OpenCode server backend is closed.")
        try:
            importlib.import_module("httpx")
        except ImportError:
            raise RuntimeError("OpenCode server transport requires httpx>=0.27; install worker dependencies.") from None
        await self._discover_config()
        if not self._injected_client:
            code, stdout, stderr = await self._run_cli([self.opencode_path, "serve", "--help"])
            if code or not all(flag in stdout + stderr for flag in ("--hostname", "--port")):
                raise RuntimeError("OpenCode cannot start a headless server; repair or update its CLI.")
        return {"backend": self.__class__.__name__, "transport": "server",
                "model": self.default_model, "model_configured": True,
                "effort": f"provider variant: {self.default_effort} (none disables variants)",
                "session_policy": self.session_policy, "research_tools": self.research_tool_policy,
                "timeout_seconds": self.timeout_seconds}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def _ensure_started(self) -> None:
        async with self._start_lock:
            if self._closed:
                raise RuntimeError("OpenCode server backend is closed.")
            if self._client is not None:
                return
            await self._discover_config()
            httpx = importlib.import_module("httpx")
            native = self._native_permissions if isinstance(self._native_permissions, dict) else {"*": self._native_permissions}
            self._environment = disposable_cli_env("opencode", research_permissions=native)
            env = self._environment.__enter__()
            self._environment_root = Path(env["HOME"])
            password = secrets.token_urlsafe(32)
            env.update(OPENCODE_SERVER_USERNAME="mimir", OPENCODE_SERVER_PASSWORD=password)
            kwargs: Dict[str, Any] = {"stdin": asyncio.subprocess.DEVNULL,
                                      "stdout": asyncio.subprocess.PIPE,
                                      "stderr": asyncio.subprocess.DEVNULL, "env": env}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                suinfo = subprocess.STARTUPINFO()
                suinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                suinfo.wShowWindow = subprocess.SW_HIDE
                kwargs["startupinfo"] = suinfo
            else:
                kwargs["start_new_session"] = True
            try:
                self._process = await asyncio.create_subprocess_exec(
                    self.opencode_path, "serve", "--hostname=127.0.0.1", "--port=0", **kwargs)

                async def readiness() -> str:
                    while True:
                        line = await self._process.stdout.readline()
                        if not line:
                            raise RuntimeError("OpenCode server exited before becoming ready.")
                        text = line.decode("utf-8", errors="replace").strip()
                        match = re.fullmatch(r"opencode server listening on (http://127\.0\.0\.1:\d+)", text)
                        if match:
                            return match.group(1)

                url = await asyncio.wait_for(readiness(), self.startup_timeout_seconds)
                factory = self._client_factory or httpx.AsyncClient
                self._client = factory(base_url=url, auth=("mimir", password),
                                       timeout=self.timeout_seconds, trust_env=False,
                                       params={"directory": str(Path.cwd())})

                async def drain_stdout() -> None:
                    while await self._process.stdout.read(65536):
                        pass

                self._drainer = asyncio.create_task(drain_stdout())
                health = await asyncio.wait_for(self._request("GET", "/global/health"), self.startup_timeout_seconds)
                if not isinstance(health, dict) or health.get("healthy") is not True:
                    raise RuntimeError("OpenCode server returned invalid health information.")
            except BaseException:
                await self._close_server()
                raise

    async def _cleanup_session(self, session: str, *, abort: bool) -> None:
        if session not in self._owned_sessions or self._client is None:
            return
        failure = None
        if abort:
            try:
                result = await asyncio.wait_for(self._request("POST", f"/session/{session}/abort"), self.cleanup_timeout_seconds)
                if result is not True:
                    raise WorkerCleanupError("OpenCode session abort was not confirmed.")
            except Exception as exc:
                failure = exc
        try:
            result = await asyncio.wait_for(self._request("DELETE", f"/session/{session}"), self.cleanup_timeout_seconds)
            if result is not True:
                raise WorkerCleanupError("OpenCode session deletion was not confirmed.")
            self._owned_sessions.discard(session)
        except Exception as exc:
            failure = exc
        if failure is not None:
            raise WorkerCleanupError("OpenCode owned session cleanup could not be confirmed.") from None

    async def _worker(self, text: str, model: str, effort: str,
                      schema: Optional[Dict[str, Any]], owner: list[str]) -> Any:
        await self._ensure_started()
        permissions = _permission_rules(self._native_permissions)
        # Do not let session-level query grants override build-agent denials.
        # Skip the generated worker defaults when appending native agent rules.
        permissions.extend(_permission_rules(self._agent_permissions)[1 + len(_OPENCODE_QUERIES):])
        session = await self._request("POST", "/session", json={
            "title": "Mimir disposable worker", "permission": permissions})
        identifier = session.get("id") if isinstance(session, dict) else None
        if not isinstance(identifier, str) or re.fullmatch(r"ses[A-Za-z0-9_-]+", identifier) is None:
            raise ValueError("OpenCode returned an invalid session identifier.")
        owner.append(identifier)
        self._owned_sessions.add(identifier)
        provider, selected_model = model.split("/", 1)
        body: Dict[str, Any] = {"model": {"providerID": provider, "modelID": selected_model}, "agent": "build",
                                "parts": [{"type": "text", "text": text}]}
        if effort != "none":
            body["variant"] = effort
        if schema is not None:
            body["format"] = {"type": "json_schema", "schema": schema, "retryCount": 0}
        return await self._request("POST", f"/session/{identifier}/message", json=body)

    async def spawn(self, prompt: str, role: str = "Micro-Worker", model: Optional[str] = None,
                    effort: Optional[str] = None, json_schema: Optional[Dict[str, Any]] = None,
                    input_data: Any = None) -> SwarmResult:
        async with self.semaphore:
            task = asyncio.current_task()
            self._workers.add(task)
            owner: list[str] = []
            abort = True
            start = asyncio.get_running_loop().time()
            result = None
            cancelled = False
            try:
                selected_model = model or self.default_model
                if "/" not in selected_model or not all(selected_model.split("/", 1)):
                    raise ValueError("OpenCode requires provider/model.")
                response = await asyncio.wait_for(self._worker(
                    _prompt(prompt, role, input_data), selected_model, effort or self.default_effort,
                    json_schema, owner), self.timeout_seconds)
                info = response.get("info", {}) if isinstance(response, dict) else {}
                if not isinstance(info, dict) or info.get("role") != "assistant" or info.get("error"):
                    result = SwarmResult(role, "ERROR", None, "OpenCode server returned an unsuccessful assistant result.")
                elif info.get("finish") not in ("stop", "end_turn") and not (
                        info.get("finish") == "tool-calls" and info.get("structured") is not None):
                    result = SwarmResult(role, "ERROR", None, "OpenCode server returned an incomplete assistant result.")
                else:
                    abort = False
                    content = info.get("structured")
                    if json_schema is not None and content is None:
                        result = SwarmResult(role, "ERROR", None, "OpenCode server returned no structured result for the requested schema.")
                    else:
                        if content is None:
                            content = "\n".join(part.get("text", "") for part in response.get("parts", [])
                                                if isinstance(part, dict) and part.get("type") == "text" and not part.get("ignored"))
                        raw = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                        data = self.parse_json_from_text(raw)
                        _validate_schema(data, json_schema)
                        if not has_worker_result(data):
                            result = SwarmResult(role, "ERROR", None, "OpenCode server returned no usable result.")
                        else:
                            result = SwarmResult(role, "SUCCESS", data, raw,
                                                 asyncio.get_running_loop().time() - start,
                                                 _tokens(info.get("tokens"), "input", "output"))
            except asyncio.CancelledError:
                cancelled = True
            except _SchemaError:
                result = SwarmResult(role, "ERROR", None, "OpenCode server output does not satisfy the requested JSON schema.")
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                error = f"OpenCode server worker failed: HTTP {status}; check provider, authentication, and limits." if isinstance(status, int) else worker_diagnostic("OpenCode server", error=exc)
                result = SwarmResult(role, "ERROR", None, error)
            finally:
                try:
                    if owner:
                        await self._cleanup_session(owner[0], abort=abort)
                except Exception as exc:
                    result = SwarmResult(role, "ERROR", None, worker_diagnostic("OpenCode server", error=exc))
                finally:
                    self._workers.discard(task)
            if cancelled:
                raise asyncio.CancelledError
            if result is not None and result.status == "ERROR":
                result.duration_seconds = asyncio.get_running_loop().time() - start
            return result

    async def _close_server(self) -> None:
        client_failure = None
        try:
            if self._client is not None and not self._injected_client:
                await self._client.aclose()
                self._client = None
        except Exception as exc:
            client_failure = exc
        # Reap the owned process even when closing its HTTP connection fails.
        if self._process is not None:
            await _stop_process(self._process, self.cleanup_timeout_seconds)
            self._process = None
        if self._drainer is not None:
            self._drainer.cancel()
            with suppress(asyncio.CancelledError):
                await self._drainer
            self._drainer = None
        if self._environment is not None:
            await _release_environment(self._environment, self._environment_root, self.cleanup_timeout_seconds)
            self._environment = None
            self._environment_root = None
        if client_failure is not None:
            raise WorkerCleanupError("OpenCode HTTP connection cleanup failed after server shutdown.") from None

    async def aclose(self) -> None:
        async with self._close_lock:
            self._closed = True
            workers = [task for task in self._workers if task is not asyncio.current_task()]
            for task in workers:
                task.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            failures = await asyncio.gather(*(self._cleanup_session(session, abort=True)
                                              for session in list(self._owned_sessions)), return_exceptions=True)
            async with self._start_lock:
                await self._close_server()
            if any(isinstance(value, BaseException) for value in failures):
                raise WorkerCleanupError("OpenCode owned session cleanup could not be confirmed.")

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()
