"""Observable Codex SDK worker contracts, without credentials or model calls."""

import asyncio
from enum import Enum
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import SwarmTask, WorkerCleanupError
from codex_sdk_backend import CodexSdkSwarmBackend


class ApprovalMode(Enum):
    deny_all = "deny_all"


class Sandbox(Enum):
    read_only = "read-only"


class Effort(Enum):
    low = "low"
    high = "high"


class FakeSdk:
    """A programmable implementation of the official SDK's public interface."""

    def __init__(self):
        self.clients = []
        self.result = SimpleNamespace(
            status="completed", error=None, final_response='{"finding": "supported"}',
            usage=SimpleNamespace(last=SimpleNamespace(total_tokens=17)),
        )
        self.start_error = None
        self.run_error = None
        self.close_error = None
        self.block_start = None
        self.block_run = None
        self.block_close = None
        self.entered = asyncio.Event()
        self.running = asyncio.Event()
        self.closing = asyncio.Event()
        self.events = []

    def bindings(self):
        return SimpleNamespace(
            AsyncCodex=self.client, CodexConfig=lambda **kw: SimpleNamespace(**kw),
            ApprovalMode=ApprovalMode, Sandbox=Sandbox, ReasoningEffort=Effort,
            version="test-sdk",
        )

    def client(self, *, config):
        sdk = self

        class Client:
            def __init__(self):
                self.config = config
                self.closed = False
                self.close_calls = 0
                self.thread_options = None
                self.turn_options = None
                self.prompt = None
                self.interrupted = False

            async def __aenter__(self):
                sdk.entered.set()
                sdk.events.append("start")
                if sdk.block_start is not None:
                    await sdk.block_start.wait()
                if sdk.start_error:
                    raise sdk.start_error
                self.closed = False
                sdk.events.append("started")
                return self

            async def close(self):
                self.close_calls += 1
                sdk.closing.set()
                if sdk.block_close is not None:
                    await sdk.block_close.wait()
                if sdk.close_error:
                    raise sdk.close_error
                self.closed = True
                sdk.events.append("closed")

            async def thread_start(self, **options):
                self.thread_options = options
                return self

            async def turn(self, prompt, **options):
                self.prompt = prompt
                self.turn_options = options
                return self

            async def run(self):
                sdk.running.set()
                if sdk.block_run is not None:
                    await sdk.block_run.wait()
                if sdk.run_error:
                    raise sdk.run_error
                return sdk.result

            async def interrupt(self):
                self.interrupted = True
                sdk.events.append("interrupted")

        instance = Client()
        self.clients.append(instance)
        return instance


class CodexSdkContracts(unittest.IsolatedAsyncioTestCase):
    async def test_restricted_call_preserves_instructions_and_rejects_tool_attempt(self):
        backend = self.backend()
        self.sdk.result.items = [SimpleNamespace(type="mcpToolCall")]
        with patch("codex_sdk_backend.text_only_overrides", return_value=('features.shell_tool=false',)):
            result = await backend.spawn_restricted("messages", completion_instructions="Trusted DSPy signature")
        self.assertEqual(result.status, "ERROR")
        self.assertIn("Trusted DSPy signature", self.sdk.clients[-1].thread_options["developer_instructions"])
        self.assertEqual(self.sdk.clients[-1].config.config_overrides, ('features.shell_tool=false',))

    def backend(self, sdk=None, **kwargs):
        self.sdk = sdk or FakeSdk()
        return CodexSdkSwarmBackend(default_model="worker-model",
                                    sdk_factory=self.sdk.bindings, **kwargs)

    async def test_preserves_native_provider_and_uses_ephemeral_read_only_worker(self):
        backend = self.backend(codex_path="chosen-codex")
        result = await backend.spawn("Investigate", role="researcher", model="task-model",
                                     effort="high", input_data={"value": "evidence"})
        self.assertEqual((result.status, result.data, result.tokens_used),
                         ("SUCCESS", {"finding": "supported"}, 17))
        client = self.sdk.clients[0]
        self.assertEqual(client.config.codex_bin, "chosen-codex")
        self.assertFalse(hasattr(client.config, "config_overrides"))
        self.assertFalse(hasattr(client.config, "env"))
        self.assertNotIn("model_provider", client.thread_options)
        self.assertNotIn("config", client.thread_options)
        self.assertTrue(client.thread_options["ephemeral"])
        self.assertEqual(client.thread_options["sandbox"], Sandbox.read_only)
        self.assertEqual(client.thread_options["approval_mode"], ApprovalMode.deny_all)
        self.assertEqual(client.thread_options["model"], "task-model")
        self.assertIn("RESEARCH TOOLS AND EVIDENCE", client.thread_options["developer_instructions"])
        self.assertIn("Do not launch Mimir", client.thread_options["developer_instructions"])
        self.assertIn("UNTRUSTED EVIDENCE", client.prompt)
        self.assertIn('"value": "evidence"', client.prompt)
        self.assertEqual(client.turn_options["effort"], Effort.high)
        self.assertEqual(client.turn_options["sandbox"], Sandbox.read_only)
        self.assertTrue(client.closed)
        self.assertGreaterEqual(result.duration_seconds, 0)

    async def test_sdk_uses_matching_runtime_unless_explicit_path(self):
        backend = self.backend()
        await backend.spawn("task")
        self.assertFalse(hasattr(self.sdk.clients[0].config, "codex_bin"))

    async def test_schema_rejection_preserves_original_output_and_usage(self):
        backend = self.backend()
        result = await backend.spawn("task", json_schema={"type": "object", "properties": {
            "finding": {"type": "string", "maxLength": 2}}})
        self.assertEqual(result.status, "ERROR")
        self.assertEqual(result.tokens_used, 17)
        self.assertEqual(result.rejected_output["result"], {"finding": "supported"})
        self.assertTrue(self.sdk.clients[0].closed)

    async def test_worker_low_effort_overrides_host_and_retains_usage_breakdown(self):
        backend = self.backend()
        self.sdk.result.usage = SimpleNamespace(total=SimpleNamespace(
            total_tokens=110, input_tokens=100, cached_input_tokens=80,
            output_tokens=10, reasoning_output_tokens=3))
        result = await backend.spawn("One bounded task", model="gpt-6.1-sol")
        client = self.sdk.clients[0]
        self.assertEqual(client.turn_options["model"], "gpt-6.1-sol")
        self.assertEqual(client.turn_options["effort"], Effort.low)
        self.assertEqual(result.usage_details["cached_input_tokens"], 80)
        self.assertEqual(result.usage_details["reasoning_output_tokens"], 3)
        self.assertEqual(result.tokens_used, 110)
        self.assertTrue({"runtime_start_seconds", "thread_ready_seconds", "turn_seconds", "cleanup_seconds"} <= result.timing.keys())

    async def test_check_does_not_start_runtime_or_authenticate(self):
        backend = self.backend()
        self.assertEqual(backend.transport, "sdk")
        checked = await backend.check_cli()
        self.assertEqual(checked["transport"], "sdk")
        self.assertEqual(checked["sdk_version"], "test-sdk")
        self.assertEqual(self.sdk.clients, [])

    async def test_selected_sdk_dependency_missing_has_no_cli_fallback(self):
        backend = CodexSdkSwarmBackend(default_model="worker")
        with patch("codex_sdk_backend.importlib.import_module", side_effect=ImportError):
            result = await backend.spawn("sensitive prompt")
            self.assertEqual(result.status, "ERROR")
            self.assertIn("openai-codex==0.163.0", result.raw_response)
            self.assertIn("--worker-transport cli", result.raw_response)
            self.assertNotIn("sensitive prompt", result.raw_response)
            with self.assertRaisesRegex(RuntimeError, "openai-codex"):
                await backend.check_cli()

    async def test_explicit_model_is_required(self):
        sdk = FakeSdk()
        backend = CodexSdkSwarmBackend(sdk_factory=sdk.bindings)
        result = await backend.spawn("task")
        self.assertEqual(result.status, "ERROR")
        self.assertEqual(sdk.clients, [])
        with self.assertRaises(ValueError):
            await backend.check_cli()

    async def test_invalid_effort_fails_before_runtime(self):
        backend = self.backend()
        result = await backend.spawn("task", effort="unsupported-effort")
        self.assertEqual(result.status, "ERROR")
        self.assertEqual(self.sdk.clients, [])

    async def test_schema_dependency_missing_fails_before_runtime(self):
        backend = self.backend()
        with patch("codex_sdk_backend.importlib.import_module", side_effect=ImportError):
            result = await backend.spawn("task", json_schema={"type": "object"})
        self.assertEqual(result.status, "ERROR")
        self.assertIn("jsonschema", result.raw_response)
        self.assertEqual(self.sdk.clients, [])

    async def test_prose_with_embedded_json_remains_prose(self):
        backend = self.backend()
        self.sdk.result.final_response = 'Finding and example:\n```json\n{"example": 1}\n```'
        result = await backend.spawn("task")
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.data, self.sdk.result.final_response)

    async def test_failed_interrupted_and_empty_turns_never_publish_partial_answer(self):
        for status, error, response in [
            ("failed", None, "partial"), ("interrupted", None, "partial"),
            ("completed", SimpleNamespace(message="secret-token"), "partial"),
            ("completed", None, None), ("completed", None, " "),
            ("completed", None, "{}"),
        ]:
            with self.subTest(status=status, response=response):
                backend = self.backend()
                self.sdk.result.status = status
                self.sdk.result.error = error
                self.sdk.result.final_response = response
                result = await backend.spawn("task")
                self.assertEqual(result.status, "ERROR")
                self.assertIsNone(result.data)
                self.assertNotIn("secret-token", result.raw_response)
                self.assertTrue(self.sdk.clients[0].closed)

    async def test_failure_diagnostics_do_not_expose_provider_body(self):
        backend = self.backend()
        self.sdk.run_error = RuntimeError("HTTP 401 secret-token https://private.invalid/?key=secret")
        result = await backend.spawn("secret prompt")
        self.assertEqual(result.status, "ERROR")
        self.assertIn("authentication", result.raw_response)
        self.assertNotIn("secret", result.raw_response)
        self.assertTrue(self.sdk.clients[0].closed)

    async def test_startup_failure_closes_client(self):
        backend = self.backend()
        self.sdk.start_error = RuntimeError("startup failed secret")
        result = await backend.spawn("task")
        self.assertEqual(result.status, "ERROR")
        self.assertNotIn("secret", result.raw_response)
        self.assertTrue(self.sdk.clients[0].closed)

    async def test_timeout_interrupts_and_closes_before_result(self):
        backend = self.backend()
        backend.timeout_seconds = 0.01
        self.sdk.block_run = asyncio.Event()
        result = await backend.spawn("task")
        self.assertEqual(result.status, "ERROR")
        self.assertIn("timed out", result.raw_response)
        self.assertTrue(self.sdk.clients[0].interrupted)
        self.assertTrue(self.sdk.clients[0].closed)

    async def test_repeated_cancellation_waits_for_cleanup(self):
        backend = self.backend()
        self.sdk.block_run = asyncio.Event()
        self.sdk.block_close = asyncio.Event()
        task = asyncio.create_task(backend.spawn("task"))
        await self.sdk.running.wait()
        task.cancel()
        await self.sdk.closing.wait()
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.sdk.block_close.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.sdk.clients[0].closed)

    async def test_cancellation_during_start_settles_late_start_then_closes(self):
        backend = self.backend()
        backend.cleanup_timeout_seconds = 0.001
        self.sdk.block_start = asyncio.Event()
        task = asyncio.create_task(backend.spawn("task"))
        await self.sdk.entered.wait()
        task.cancel()
        await self.sdk.closing.wait()
        await asyncio.sleep(0.01)
        self.assertFalse(task.done())
        self.sdk.block_start.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.sdk.clients[0].closed)
        self.assertEqual(self.sdk.events[-1], "closed")

    async def test_close_adapter_cancels_active_and_queued_workers(self):
        backend = self.backend(max_concurrency=1)
        self.sdk.block_run = asyncio.Event()
        active = asyncio.create_task(backend.spawn("one"))
        queued = asyncio.create_task(backend.spawn("two"))
        await self.sdk.running.wait()
        await backend.aclose()
        self.assertTrue(active.cancelled())
        self.assertTrue(queued.cancelled())
        self.assertEqual(len(self.sdk.clients), 1)
        self.assertTrue(self.sdk.clients[0].closed)
        self.assertEqual((await backend.spawn("three")).status, "ERROR")

    async def test_parallel_workers_get_independent_clients_closed_before_completion(self):
        backend = self.backend()
        results = await backend.parallel([SwarmTask("one", "one"), SwarmTask("two", "two")])
        self.assertTrue(all(result.status == "SUCCESS" for result in results))
        self.assertEqual(len(self.sdk.clients), 2)
        self.assertIsNot(self.sdk.clients[0], self.sdk.clients[1])
        self.assertTrue(all(client.closed for client in self.sdk.clients))

    async def test_cleanup_failure_invalidates_success(self):
        backend = self.backend()
        self.sdk.close_error = OSError("secret process details")
        result = await backend.spawn("task")
        self.assertEqual(result.status, "ERROR")
        self.assertIn("cleanup could not be confirmed", result.raw_response)
        self.assertNotIn("secret", result.raw_response)

    async def test_cleanup_failure_on_cancel_cannot_claim_cancelled_cleanly(self):
        backend = self.backend()
        self.sdk.block_run = asyncio.Event()
        self.sdk.close_error = OSError("secret process details")
        task = asyncio.create_task(backend.spawn("task"))
        await self.sdk.running.wait()
        task.cancel()
        with self.assertRaisesRegex(WorkerCleanupError, "cleanup could not be confirmed"):
            await task

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "worker schema dependency unavailable")
    async def test_schema_rejects_wrong_shape_and_invalid_json(self):
        schema = {"type": "object", "properties": {"finding": {"type": "string"}},
                  "required": ["finding"], "additionalProperties": False}
        for response in ['{"finding": 12}', '{"wrong": "value"}', "not JSON"]:
            with self.subTest(response=response):
                backend = self.backend()
                self.sdk.result.final_response = response
                result = await backend.spawn("task", json_schema=schema)
                self.assertEqual(result.status, "ERROR")
                self.assertIn("schema validation", result.raw_response)
                self.assertTrue(self.sdk.clients[0].closed)
        backend = self.backend()
        result = await backend.spawn("task", json_schema=schema)
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(self.sdk.clients[0].turn_options["output_schema"], schema)

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "worker schema dependency unavailable")
    async def test_invalid_schema_fails_before_starting_runtime(self):
        backend = self.backend()
        result = await backend.spawn("task", json_schema={"type": "unrecognized"})
        self.assertEqual(result.status, "ERROR")
        self.assertEqual(self.sdk.clients, [])

    @unittest.skipUnless(importlib.util.find_spec("openai_codex"), "official SDK not installed")
    async def test_real_sdk_public_types_accept_adapter_arguments_without_launch(self):
        from openai_codex import CodexConfig, AsyncCodex, ApprovalMode as ActualApproval, Sandbox as ActualSandbox
        from openai_codex.types import ReasoningEffort
        import inspect
        config = CodexConfig(cwd=str(Path.cwd()), client_name="mimir_worker", client_title="Mimir worker")
        client = AsyncCodex(config=config)
        self.assertEqual(ActualApproval.deny_all.value, "deny_all")
        self.assertEqual(ActualSandbox.read_only.value, "read-only")
        self.assertEqual(ReasoningEffort("high").value, "high")
        inspect.signature(client.thread_start).bind(
            model="worker", cwd=str(Path.cwd()), ephemeral=True,
            approval_mode=ActualApproval.deny_all, sandbox=ActualSandbox.read_only,
            developer_instructions="instructions")
        await client.close()

    @unittest.skipUnless(importlib.util.find_spec("openai_codex"), "official SDK not installed")
    async def test_real_sdk_serializes_policy_and_collects_turn_from_local_protocol(self):
        # Execute the installed SDK's real transport and collectors against a
        # local protocol fixture. This performs no authentication or model call.
        import openai_codex
        from openai_codex.types import ReasoningEffort
        program = r'''
import json,sys,time
from pathlib import Path
trace=Path(sys.argv[1])
def write(value):
 print(json.dumps(value),flush=True)
def notify(method,params):
 write({'method':method,'params':params})
def turn(status):
 return {'id':'turn-fixture','items':[],'status':status,'error':None}
for line in sys.stdin:
 request=json.loads(line)
 with trace.open('a',encoding='utf-8') as handle:
  handle.write(json.dumps(request)+'\n')
 method=request['method'];params=request.get('params',{})
 if 'id' not in request:continue
 if method=='initialize':
  result={'userAgent':'codex/0.163.0','serverInfo':{'name':'codex','version':'0.163.0'}}
 elif method=='thread/start':
  thread={'id':'thread-fixture','sessionId':'session-fixture','cliVersion':'0.163.0',
   'createdAt':1,'updatedAt':1,'cwd':params['cwd'],'ephemeral':True,
   'modelProvider':'fixture-native','preview':'','source':'exec','status':{'type':'idle'},'turns':[]}
  result={'thread':thread,'model':params['model'],'modelProvider':'fixture-native',
   'cwd':params['cwd'],'approvalPolicy':'never','approvalsReviewer':'user',
   'sandbox':{'type':'readOnly'}}
 elif method=='turn/start':
  result={'turn':turn('inProgress')}
 elif method=='turn/interrupt':
  result={}
 else:
  write({'id':request['id'],'error':{'code':-32601,'message':'unsupported fixture operation'}})
  continue
 write({'id':request['id'],'result':result})
 if method=='turn/start':
  notify('item/completed',{'threadId':'thread-fixture','turnId':'turn-fixture','completedAtMs':1,
   'item':{'id':'answer-fixture','type':'agentMessage','phase':'final_answer','text':'{"finding":"fixture"}'}})
  usage={'inputTokens':10,'cachedInputTokens':0,'outputTokens':7,'reasoningOutputTokens':0,'totalTokens':17}
  notify('thread/tokenUsage/updated',{'threadId':'thread-fixture','turnId':'turn-fixture',
   'tokenUsage':{'last':usage,'total':usage}})
  notify('turn/completed',{'threadId':'thread-fixture','turn':turn('completed')})
'''
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime.py"
            trace = Path(directory) / "protocol.jsonl"
            runtime.write_text(program, encoding="utf-8")

            def config(**values):
                return openai_codex.CodexConfig(
                    **values, launch_args_override=(sys.executable, str(runtime), str(trace)))

            sdk = SimpleNamespace(
                AsyncCodex=openai_codex.AsyncCodex, CodexConfig=config,
                ApprovalMode=openai_codex.ApprovalMode, Sandbox=openai_codex.Sandbox,
                ReasoningEffort=ReasoningEffort, version=openai_codex.__version__)
            backend = CodexSdkSwarmBackend(default_model="fixture-model", sdk_factory=lambda: sdk)
            backend.timeout_seconds = 5
            result = await backend.spawn("fixture question", effort="high")
            self.assertEqual((result.status, result.data, result.tokens_used),
                             ("SUCCESS", {"finding": "fixture"}, 17), result.raw_response)
            requests = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
            start = next(request["params"] for request in requests if request["method"] == "thread/start")
            turn = next(request["params"] for request in requests if request["method"] == "turn/start")
            self.assertTrue(start["ephemeral"])
            self.assertEqual(start["approvalPolicy"], "never")
            self.assertEqual(start["sandbox"], "read-only")
            self.assertIsNone(start.get("modelProvider"))
            self.assertIsNone(start.get("config"))
            self.assertEqual(turn["effort"], "high")
            self.assertEqual(turn["sandboxPolicy"]["type"], "readOnly")
            await backend.aclose()


if __name__ == "__main__":
    unittest.main()
