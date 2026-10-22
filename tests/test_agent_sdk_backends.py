"""Native worker contracts exercised without credentials or model calls."""
import asyncio
from fnmatch import fnmatchcase
import json
from pathlib import Path
import os
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import anyio
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent_sdk_backends import ClaudeAgentSDKBackend, OpenCodeServerBackend, _release_environment
from backend import WorkerCleanupError


SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}},
          "required": ["answer"], "additionalProperties": False}


class FakeResult:
    def __init__(self, **values):
        self.__dict__.update(dict(is_error=False, subtype="success", result="found",
                                 structured_output=None, usage={"input_tokens": 3, "output_tokens": 2}), **values)


class FakeSDK:
    ResultMessage = FakeResult
    ClaudeAgentOptions = SimpleNamespace
    HookMatcher = SimpleNamespace

    def __init__(self, results=None, error=None, block=False):
        self.results = results if results is not None else [FakeResult()]
        self.error = error
        self.block = block
        self.calls = []
        self.closed = 0
        self.started = asyncio.Event()

    async def query(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        try:
            if self.block:
                await anyio.sleep_forever()
            if self.error:
                raise self.error
            for result in self.results:
                yield result
        finally:
            # Verify SDK cleanup receives an AnyIO cancellation, allowing its
            # shielded subprocess shutdown to complete.
            with anyio.CancelScope(shield=True):
                await anyio.sleep(0)
                self.closed += 1


class ClaudeSDKContracts(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_options_preserve_native_config_and_gate_mutation(self):
        sdk = FakeSDK([FakeResult(structured_output={"answer": "found"})])
        backend = ClaudeAgentSDKBackend(sdk=sdk)
        with patch("agent_sdk_backends.claude_research_tools", return_value=["mcp__workiq__ask_work_iq"]):
            result = await backend.spawn("read @/private and /command literally", json_schema=SCHEMA, input_data={"value": 1})
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.data, {"answer": "found"})
        self.assertEqual(result.tokens_used, 5)
        options = sdk.calls[0]["options"]
        self.assertTrue(options.verbatim_prompts)
        self.assertEqual(options.setting_sources, ["user", "project", "local"])
        self.assertEqual(options.permission_mode, "dontAsk")
        self.assertIn("no-session-persistence", options.extra_args)
        self.assertNotIn("effort", options.__dict__)
        self.assertNotIn("cli_path", options.__dict__)
        self.assertNotIn("resume", options.__dict__)
        self.assertEqual(options.output_format, {"type": "json_schema", "schema": SCHEMA})
        self.assertIn("INPUT DATA", sdk.calls[0]["prompt"])
        hook = options.hooks["PreToolUse"][0].hooks[0]
        self.assertEqual(await hook({"tool_name": "Read"}, None, None), {})
        self.assertEqual(await hook({"tool_name": "mcp__workiq__ask_work_iq"}, None, None), {})
        self.assertEqual(await hook({"tool_name": "StructuredOutput"}, None, None), {})
        for name in ("Bash", "Agent", "mcp__workiq__send_email", "mcp__admin__change_settings", None):
            output = await hook({"tool_name": name}, None, None)
            self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(sdk.closed, 1)
        await backend.aclose()

    async def test_effort_and_schema_failure(self):
        sdk = FakeSDK([FakeResult(structured_output={"answer": 42})])
        backend = ClaudeAgentSDKBackend(default_model="sonnet", sdk=sdk)
        result = await backend.spawn("task", effort="medium", json_schema=SCHEMA)
        self.assertEqual(sdk.calls[0]["options"].effort, "medium")
        self.assertEqual(result.status, "ERROR")
        self.assertIn("JSON schema", result.raw_response)
        self.assertNotIn("42", result.raw_response)

    async def test_unsuccessful_terminal_absence_and_empty_are_errors(self):
        for messages in ([FakeResult(is_error=True)], [FakeResult(subtype="error_max_turns")],
                         [], [FakeResult(result="")], [FakeResult(result="{}")]):
            with self.subTest(messages=messages):
                sdk = FakeSDK(messages)
                result = await ClaudeAgentSDKBackend(sdk=sdk).spawn("task")
                self.assertEqual(result.status, "ERROR")
        sdk = FakeSDK([FakeResult(result='{"answer":"found"}')])
        result = await ClaudeAgentSDKBackend(sdk=sdk).spawn("task", json_schema=SCHEMA)
        self.assertEqual(result.status, "ERROR")
        self.assertIn("no structured result", result.raw_response)

    async def test_provider_exception_never_echoes_prompt_or_secret(self):
        sdk = FakeSDK(error=RuntimeError("secretkey prompt http://credentials@server"))
        result = await ClaudeAgentSDKBackend(sdk=sdk).spawn("secret prompt")
        self.assertEqual(result.status, "ERROR")
        self.assertNotIn("secret", result.raw_response)
        self.assertNotIn("credentials", result.raw_response)

    async def test_typed_sdk_error_is_classified_after_terminal_error(self):
        class ResultError(RuntimeError):
            pass
        class TerminalSDK(FakeSDK):
            async def query(self, **kwargs):
                try:
                    yield FakeResult(is_error=True, result="Invalid API key secret prompt", api_error_status=401)
                    raise ResultError("runtime exited secret prompt")
                finally:
                    self.closed += 1
        sdk = TerminalSDK()
        sdk.ResultError = ResultError
        result = await ClaudeAgentSDKBackend(sdk=sdk).spawn("task")
        self.assertEqual(result.status, "ERROR")
        self.assertIn("authentication failed", result.raw_response)
        self.assertIn("401", result.raw_response)
        self.assertNotIn("secret", result.raw_response)
        self.assertGreater(result.duration_seconds, 0)
        self.assertEqual(sdk.closed, 1)

    async def test_sdk_error_result_prose_is_classified_without_echoing_it(self):
        sdk = FakeSDK([FakeResult(is_error=True, result="Invalid API key: credentials and secret prompt")])
        result = await ClaudeAgentSDKBackend(sdk=sdk).spawn("task")
        self.assertIn("authentication failed", result.raw_response)
        self.assertNotIn("secret", result.raw_response)
        self.assertNotIn("credentials", result.raw_response)
        for status, label in [(403, "access denied"), (429, "rate limit")]:
            sdk = FakeSDK([FakeResult(is_error=True, api_error_status=status)])
            result = await ClaudeAgentSDKBackend(sdk=sdk).spawn("task")
            self.assertIn(label, result.raw_response)

    async def test_timeout_and_cancellation_close_sdk(self):
        sdk = FakeSDK(block=True)
        backend = ClaudeAgentSDKBackend(sdk=sdk)
        backend.timeout_seconds = .02
        result = await backend.spawn("task")
        self.assertEqual(result.status, "ERROR")
        self.assertIn("timed out", result.raw_response)
        self.assertEqual(sdk.closed, 1)
        sdk = FakeSDK(block=True)
        backend = ClaudeAgentSDKBackend(sdk=sdk)
        worker = asyncio.create_task(backend.spawn("task"))
        await sdk.started.wait()
        worker.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await worker
        self.assertEqual(sdk.closed, 1)
        self.assertEqual(backend._running, {})

    async def test_close_aborts_running_worker_and_is_idempotent(self):
        sdk = FakeSDK(block=True)
        backend = ClaudeAgentSDKBackend(sdk=sdk)
        worker = asyncio.create_task(backend.spawn("task"))
        await sdk.started.wait()
        await backend.aclose()
        with self.assertRaises(asyncio.CancelledError):
            await worker
        await backend.aclose()
        self.assertEqual(sdk.closed, 1)
        self.assertEqual((await backend.spawn("task")).status, "ERROR")

    async def test_preflight_loads_dependency_without_inference(self):
        sdk = FakeSDK()
        backend = ClaudeAgentSDKBackend(sdk=sdk)
        info = await backend.check_cli()
        self.assertEqual(info["transport"], "sdk")
        self.assertEqual(sdk.calls, [])
        self.assertEqual(info["runtime"], "SDK bundled Claude Code")


class OpenCodeProtocol:
    def __init__(self, structured=None, error=None, block=False, finish="stop", delete=True):
        self.structured = structured
        self.error = error
        self.block = block
        self.finish = finish
        self.delete = delete
        self.calls = []
        self.count = 0
        self.started = asyncio.Event()

    async def __call__(self, request):
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        path = request.url.path
        if path == "/session" and request.method == "POST":
            self.count += 1
            return httpx.Response(200, json={"id": f"ses_owned{self.count}"})
        if path.endswith("/message"):
            self.started.set()
            if self.block:
                await asyncio.Event().wait()
            info = {"role": "assistant", "finish": self.finish,
                    "tokens": {"input": 4, "output": 6, "reasoning": 3}}
            if self.error:
                info["error"] = self.error
            if self.structured is not None:
                info["structured"] = self.structured
            return httpx.Response(200, json={"info": info, "parts": [{"type": "text", "text": "evidence"}]})
        if path.endswith("/abort"):
            return httpx.Response(200, json=True)
        if request.method == "DELETE":
            return httpx.Response(200, json=self.delete)
        if path == "/global/health":
            return httpx.Response(200, json={"healthy": True, "version": "1.19.3"})
        raise AssertionError(f"Unexpected request {request.method} {path}")


class OpenCodeHTTPContracts(unittest.IsolatedAsyncioTestCase):
    def client(self, protocol):
        return httpx.AsyncClient(base_url="http://127.0.0.1:34567", transport=httpx.MockTransport(protocol))

    async def test_structured_native_request_and_owned_cleanup(self):
        protocol = OpenCodeProtocol(structured={"answer": "found"})
        async with self.client(protocol) as client:
            backend = OpenCodeServerBackend(default_model="provider/model", http_client=client)
            result = await backend.spawn("read evidence", effort="medium", json_schema=SCHEMA)
            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(result.data, {"answer": "found"})
            self.assertEqual(result.tokens_used, 10)
            create = protocol.calls[0][2]
            self.assertEqual(create["permission"][0], {"permission": "*", "pattern": "*", "action": "deny"})
            body = protocol.calls[1][2]
            self.assertEqual(body["model"], {"providerID": "provider", "modelID": "model"})
            self.assertEqual(body["agent"], "build")
            self.assertEqual(body["variant"], "medium")
            self.assertEqual(body["format"], {"type": "json_schema", "schema": SCHEMA, "retryCount": 0})
            self.assertEqual(protocol.calls[-1][:2], ("DELETE", "/session/ses_owned1"))
            self.assertFalse(any(call[1].endswith("/abort") for call in protocol.calls))
            await backend.aclose()
            self.assertFalse(client.is_closed)  # Dependency owner closes injected client.

    async def test_native_permissions_intersect_query_policy(self):
        protocol = OpenCodeProtocol()
        async with self.client(protocol) as client:
            backend = OpenCodeServerBackend(default_model="p/m", default_effort="none", http_client=client)
            backend._native_permissions = {"*": "allow", "bash": "allow", "read": {"*": "allow", "secrets/*": "deny"},
                                           "mcp_admin_mutate": "allow", "webfetch": "ask", "grep": "deny"}
            backend._agent_permissions = {"read": {"agent-private/*": "deny"}, "bash": "allow"}
            self.assertEqual((await backend.spawn("task")).status, "SUCCESS")
            rules = protocol.calls[0][2]["permission"]
            def decision(tool, resource):
                matching = [rule["action"] for rule in rules
                            if fnmatchcase(tool, rule["permission"]) and fnmatchcase(resource, rule["pattern"])]
                return matching[-1]
            self.assertEqual(decision("read", "public.txt"), "allow")
            for tool, resource in [("bash", "*"), ("mcp_admin_mutate", "*"), ("read", "secrets/key"),
                                   ("read", "agent-private/key"), ("webfetch", "url"), ("grep", "x")]:
                self.assertEqual(decision(tool, resource), "deny")
            self.assertEqual(decision("workiq_ask_work_iq", "query"), "allow")
            self.assertNotIn("variant", protocol.calls[1][2])

    async def test_native_wildcard_deny_preserves_specific_query_grants(self):
        protocol = OpenCodeProtocol()
        async with self.client(protocol) as client:
            backend = OpenCodeServerBackend(default_model="p/m", http_client=client)
            backend._native_permissions = {"*": "deny", "read": "allow"}
            await backend.spawn("task")
            rules = protocol.calls[0][2]["permission"]
            self.assertEqual(rules[-2:], [{"permission": "*", "pattern": "*", "action": "deny"},
                                         {"permission": "read", "pattern": "*", "action": "allow"}])

    async def test_error_and_incomplete_are_never_success_and_abort_only_owned_session(self):
        for kwargs in ({"error": {"name": "APIError", "data": {"message": "secret prompt"}}},
                       {"finish": "length"}, {"finish": None}):
            with self.subTest(kwargs=kwargs):
                protocol = OpenCodeProtocol(**kwargs)
                async with self.client(protocol) as client:
                    backend = OpenCodeServerBackend(default_model="p/m", http_client=client)
                    result = await backend.spawn("secret prompt")
                    self.assertEqual(result.status, "ERROR")
                    self.assertNotIn("secret", result.raw_response)
                    self.assertEqual(protocol.calls[-2][:2], ("POST", "/session/ses_owned1/abort"))
                    self.assertEqual(protocol.calls[-1][:2], ("DELETE", "/session/ses_owned1"))
                    await backend.aclose()
                    self.assertFalse(any(call[0] == "GET" and call[1] == "/session" for call in protocol.calls))

    async def test_schema_validation_and_missing_structured_result(self):
        for structured in (None, {"answer": 42}):
            protocol = OpenCodeProtocol(structured=structured)
            async with self.client(protocol) as client:
                backend = OpenCodeServerBackend(default_model="p/m", http_client=client)
                result = await backend.spawn("task", json_schema=SCHEMA)
                self.assertEqual(result.status, "ERROR")
                self.assertNotIn("42", result.raw_response)

    async def test_structured_output_tool_call_finish_is_terminal_success(self):
        # OpenCode returns immediately after synthetic StructuredOutput and
        # preserves the provider's existing tool-calls finish marker.
        protocol = OpenCodeProtocol(structured={"answer": "found"}, finish="tool-calls")
        async with self.client(protocol) as client:
            result = await OpenCodeServerBackend(default_model="p/m", http_client=client).spawn("task", json_schema=SCHEMA)
            self.assertEqual(result.status, "SUCCESS")

    async def test_windows_storage_handle_race_is_retried_only_in_owned_root(self):
        root = Path(tempfile.mkdtemp(prefix="mimir_opencode_"))
        class LockedEnvironment:
            def __exit__(self, *args):
                raise PermissionError("handle still closing")
        original = __import__("shutil").rmtree
        attempts = []
        def retry(path):
            attempts.append(path)
            if len(attempts) == 1:
                raise PermissionError("closing")
            original(path)
        with patch("agent_sdk_backends.shutil.rmtree", side_effect=retry):
            await _release_environment(LockedEnvironment(), root, .5)
        self.assertEqual(len(attempts), 2)
        self.assertFalse(root.exists())
        with self.assertRaises(WorkerCleanupError):
            await _release_environment(LockedEnvironment(), Path.cwd(), .01)

    async def test_start_failure_reaps_process_and_releases_storage(self):
        import agent_sdk_backends as module
        from contextlib import contextmanager
        class EmptyPipe:
            async def readline(self):
                return b""
        process = SimpleNamespace(stdout=EmptyPipe(), pid=123, returncode=1)
        released = []
        @contextmanager
        def environment(*args, **kwargs):
            with tempfile.TemporaryDirectory(prefix="mimir_opencode_") as root:
                try:
                    yield {"HOME": root}
                finally:
                    released.append(root)
        async def start(*args, **kwargs):
            self.assertIn("--hostname=127.0.0.1", args)
            self.assertIn("--port=0", args)
            self.assertTrue(kwargs["env"]["OPENCODE_SERVER_PASSWORD"])
            self.assertEqual(kwargs["stderr"], asyncio.subprocess.DEVNULL)
            return process
        stopped = []
        async def stop(proc, timeout):
            stopped.append(proc)
        backend = OpenCodeServerBackend(default_model="p/m", opencode_path="opencode")
        backend._configured = True
        with patch.object(module, "disposable_cli_env", environment), patch.object(module.asyncio, "create_subprocess_exec", start), patch.object(module, "_stop_process", stop):
            result = await backend.spawn("task")
        self.assertEqual(result.status, "ERROR")
        self.assertEqual(stopped, [process])
        self.assertEqual(len(released), 1)
        self.assertFalse(Path(released[0]).exists())
        self.assertIsNone(backend._environment)
        self.assertIsNone(backend._process)

    async def test_timeout_aborts_and_deletes_before_return(self):
        protocol = OpenCodeProtocol(block=True)
        async with self.client(protocol) as client:
            backend = OpenCodeServerBackend(default_model="p/m", http_client=client)
            backend.timeout_seconds = .02
            result = await backend.spawn("task")
            self.assertEqual(result.status, "ERROR")
            self.assertIn("timed out", result.raw_response)
            self.assertEqual(protocol.calls[-2][:2], ("POST", "/session/ses_owned1/abort"))
            self.assertEqual(protocol.calls[-1][:2], ("DELETE", "/session/ses_owned1"))
            self.assertEqual(backend._owned_sessions, set())

    async def test_cancel_and_close_abort_and_delete_then_propagate(self):
        for mode in ("cancel", "close"):
            protocol = OpenCodeProtocol(block=True)
            async with self.client(protocol) as client:
                backend = OpenCodeServerBackend(default_model="p/m", http_client=client)
                worker = asyncio.create_task(backend.spawn("task"))
                await protocol.started.wait()
                if mode == "cancel":
                    worker.cancel()
                else:
                    await backend.aclose()
                with self.assertRaises(asyncio.CancelledError):
                    await worker
                self.assertEqual(protocol.calls[-2][:2], ("POST", "/session/ses_owned1/abort"))
                self.assertEqual(protocol.calls[-1][:2], ("DELETE", "/session/ses_owned1"))
                await backend.aclose()
                self.assertEqual(backend._owned_sessions, set())

    async def test_session_cleanup_failure_cannot_report_success(self):
        protocol = OpenCodeProtocol(delete=False)
        async with self.client(protocol) as client:
            result = await OpenCodeServerBackend(default_model="p/m", http_client=client).spawn("task")
            self.assertEqual(result.status, "ERROR")
            self.assertIn("cleanup", result.raw_response)

    async def test_http_errors_do_not_echo_response_or_endpoint(self):
        async def fail(request):
            return httpx.Response(401, json={"secret": "credential and prompt"})
        async with self.client(fail) as client:
            result = await OpenCodeServerBackend(default_model="p/m", http_client=client).spawn("task")
            self.assertEqual(result.status, "ERROR")
            self.assertIn("HTTP 401", result.raw_response)
            self.assertNotIn("secret", result.raw_response)
            self.assertNotIn("127.0.0.1", result.raw_response)


if __name__ == "__main__":
    unittest.main()
