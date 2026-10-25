"""Observable program, budget and evidence contracts across the real seams."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import SwarmResult
from invocation_broker import InvocationBroker, BudgetExhausted
from research_program import ResearchContext, ResearchRequest, prepare_research, load_instruction_manifest
from source_store import SourceStore, identity
from optimize_program import load_dataset
from unittest.mock import patch


class FakeNative:
    default_model = "test"
    default_effort = "low"
    max_concurrency = 1
    def __init__(self):
        self.prompts = []
        self.depths = []
        self.reply = lambda prompt: '{"answer":"42"}'
    async def spawn(self, prompt, **options):
        self.prompts.append(prompt)
        text = self.reply(prompt)
        return SwarmResult("test", "SUCCESS", text, text, tokens_used=10)
    spawn_restricted = spawn
    async def aclose(self):
        pass


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_restricted_synthesis_dispatch_and_accounting(self):
        class Native(FakeNative):
            async def spawn_restricted(self, prompt, **options):
                result = await super().spawn(prompt, **options)
                result.usage_details = {"input_tokens": 8, "cached_input_tokens": 4, "output_tokens": 2}
                result.timing = {"turn_seconds": .1}
                return result
            async def spawn(self, *args, **options):
                raise AssertionError("Restricted synthesis must not dispatch a research worker")
        broker = InvocationBroker(Native())
        await broker.spawn_restricted("Supplied evidence only", role="GEPA-Evolver")
        call = broker.usage_calls[0]
        self.assertEqual((call["model"], call["effort"], call["tool_policy"]), ("test", "low", "text_only"))
        self.assertEqual(call["usage_details"]["cached_input_tokens"], 4)
        self.assertEqual(call["timing"]["turn_seconds"], .1)

    async def test_crash_journal_charges_inflight_and_preserves_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "operations.jsonl"
            broker = InvocationBroker(FakeNative(), budget={"max_attempts": 2}, journal=journal)
            await broker.spawn("first")
            broker.event({"operation_id": "attempt-2", "status": "inflight", "tokens_used": None})
            with journal.open("a") as stream:
                stream.write('{"torn":')
            restored = InvocationBroker(FakeNative(), budget={"max_attempts": 2}, journal=journal, recover=True)
            self.assertEqual(restored.deadline, broker.deadline)
            self.assertEqual(restored.usage_calls[-1]["status"], "interrupted")
            with self.assertRaises(BudgetExhausted):
                await restored.spawn("repeat")

    async def test_reservations_prevent_review_starvation(self):
        native = FakeNative()
        broker = InvocationBroker(native, budget={"max_attempts": 3}, publication_reserve=2)
        await broker.spawn("investigate")
        with self.assertRaises(BudgetExhausted):
            await broker.spawn("more investigation")
        with self.assertRaises(BudgetExhausted):
            await broker.spawn("critic", role="Red-Team-Critic")
        await broker.spawn("synthesis", role="Mimir-Synthesizer")
        with self.assertRaises(BudgetExhausted):
            await broker.spawn("duplicate synthesis", role="Mimir-Synthesizer")
        await broker.spawn("check", role="Mimir-Final-Checker")
        self.assertEqual(len(native.prompts), 3)

    async def test_reserved_interrupted_call_is_consumed_on_resume(self):
        class HangingNative(FakeNative):
            async def spawn(self, **options):
                raise asyncio.CancelledError
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "operations.jsonl"
            broker = InvocationBroker(HangingNative(), budget={"max_attempts": 4},
                                      journal=journal, publication_reserve=2)
            with self.assertRaises(asyncio.CancelledError):
                await broker.spawn("assemble", role="Mimir-Synthesizer")
            restored = InvocationBroker(FakeNative(), budget={"max_attempts": 4},
                        journal=journal, publication_reserve=2, recover=True)
            self.assertEqual(restored.budget_status["publication_calls_remaining"], 1)
            self.assertEqual(restored.attempts, 1)
            await restored.spawn("worker")
            await restored.spawn("repair", role="Mimir-Assembly-Repairer")
            with self.assertRaises(BudgetExhausted):
                await restored.spawn("retry")
            await restored.spawn("check", role="Mimir-Final-Checker")
            self.assertEqual(restored.budget_status["publication_calls_remaining"], 0)

    async def test_journal_prevents_deadline_and_limit_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "operations.jsonl"
            with patch("invocation_broker.time.time", return_value=1000):
                broker = InvocationBroker(FakeNative(), budget={"max_seconds": 10}, journal=journal)
            with patch("invocation_broker.time.time", return_value=1011):
                restored = InvocationBroker(FakeNative(), budget={"max_seconds": 10}, journal=journal, recover=True)
                with self.assertRaises(BudgetExhausted):
                    await restored.spawn("late")
            self.assertEqual(restored.deadline, broker.deadline)
            with self.assertRaisesRegex(ValueError, "fixed by the journal"):
                InvocationBroker(FakeNative(), budget={"max_seconds": 11}, journal=journal, recover=True)
            with self.assertRaisesRegex(ValueError, "already exists"):
                InvocationBroker(FakeNative(), budget={"max_seconds": 10}, journal=journal)
            journal.unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                InvocationBroker(FakeNative(), budget={"max_seconds": 10}, journal=journal, recover=True)

    async def test_reported_token_threshold_can_overshoot_but_stops_next_call(self):
        broker = InvocationBroker(FakeNative(), budget={"max_reported_tokens": 1})
        await broker.spawn("first turn")
        self.assertEqual(broker.budget_status["reported_tokens"], 10)
        with self.assertRaisesRegex(BudgetExhausted, "overshoot"):
            await broker.spawn("next turn")

    async def test_deadline_cancels_inflight_call_and_journals_the_charge(self):
        class HangingNative(FakeNative):
            async def spawn(self, **options):
                await asyncio.Event().wait()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "operations.jsonl"
            broker = InvocationBroker(HangingNative(), budget={"max_seconds": 1}, journal=journal)
            with self.assertRaises(TimeoutError):
                await broker.spawn("too slow")
            restored = InvocationBroker(FakeNative(), budget={"max_seconds": 1}, journal=journal, recover=True)
            self.assertEqual(restored.attempts, 1)
            self.assertEqual(restored.usage_calls[0]["status"], "interrupted")
            self.assertEqual(restored.budget_status["unknown_usage_calls"], 1)
            with self.assertRaises(BudgetExhausted):
                await restored.spawn("repeat")

    async def test_depth_and_profile_cannot_escape_budget(self):
        broker = InvocationBroker(FakeNative(), budget={"max_depth": 0})
        with self.assertRaises(BudgetExhausted):
            await broker.invoke("child", depth=1)
        with self.assertRaises(ValueError):
            await broker.invoke("override", model="different")

    async def test_parallel_attempts_and_unknown_usage_are_truthful(self):
        broker = InvocationBroker(FakeNative(), budget={"max_attempts": 2})
        results = await asyncio.gather(*(broker.spawn("query") for _ in range(3)), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, BudgetExhausted) for r in results), 1)
        self.assertEqual(len(broker.usage_calls), 2)


class SourceTests(unittest.TestCase):
    def test_citation_identity_does_not_accept_invented_quotes(self):
        import hashlib
        store = SourceStore([dict(id="s", locator="source.txt", retrieved_at="2026-10-22T10:00:00Z",
                   retrieval_type="local_file", text="Port 42", sha256=hashlib.sha256(b"Port 42").hexdigest())])
        good = dict(locator="source.txt:L1", retrieved_at="2026-10-22T10:00:00Z", retrieval_type="local_file", support_excerpt="Port 42")
        store.validate_citations({"sources": [good]})
        with self.assertRaises(ValueError):
            store.validate_citations({"sources": [good | {"support_excerpt": "Port 43"}]})

    def test_remote_capture_rejects_unapproved_domain_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({"allowed_domains": ["docs.example"], "sources": [{"id": "x", "url": "https://unapproved.example/source"}]}))
            with patch("urllib.request.build_opener") as network:
                with self.assertRaises(ValueError):
                    SourceStore.capture(path)
                network.assert_not_called()

    def test_content_drift_and_changed_policy_reject_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("Owner Operations", encoding="utf-8")
            manifest = root / "sources.json"
            manifest.write_text(json.dumps({"sources": [{"id": "owner", "path": "source.txt"}]}))
            config, store, _ = prepare_research("rlm", None, str(manifest), None, {}, root)
            self.assertEqual(store.read_span("owner", 0, 5)["text"], "Owner")
            (root / "source.txt").write_text("Owner Changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare_research(None, None, None, None, {"research_config": config, "research_program": "rlm"}, root)

    def test_unreviewed_candidate_and_group_leakage_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "candidate.json"
            candidate = {"version": 1, "program": "dspy", "instructions": {"predict": "answer"}, "evaluation": {}, "reviewed": False}
            p.write_text(json.dumps(candidate | {"sha256": identity(candidate)}))
            with self.assertRaises(ValueError):
                load_instruction_manifest(p)
            row = {"group": "shared", "objective": "q", "evidence": "e", "expected": "a"}
            p.write_text(json.dumps({"train": [row], "dev": [row], "held_out": [row]}))
            with self.assertRaises(ValueError):
                load_dataset(p)


@unittest.skipUnless(importlib.util.find_spec("dspy"), "Optional research dependencies required")
class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_upstream_gepa_generates_instruction_proposals_without_heldout(self):
        from dspy_runtime.host import run_program
        class TrainingNative(FakeNative):
            async def spawn_restricted(self, prompt, completion_instructions=None, **options):
                if 'new_instruction' in (completion_instructions or ''):
                    text = '[[ ## new_instruction ## ]]\nUse supplied evidence and return JSON with answer.\n[[ ## completed ## ]]'
                else:
                    text = '[[ ## result_json ## ]]\n{"answer":"42"}\n[[ ## completed ## ]]'
                self.prompts.append(prompt)
                return SwarmResult('test','SUCCESS',text,text,tokens_used=10)
        native=TrainingNative()
        with tempfile.TemporaryDirectory() as tmp:
            broker=InvocationBroker(native,budget={"max_attempts":30,"max_seconds":60})
            context=ResearchContext(broker,SourceStore(),Path(tmp),{"program":"dspy","budget":broker.budget,"sources":[]})
            rows=[dict(group='train',objective='q',evidence='42',expected='42')]
            response,_=await run_program(ResearchRequest('training','q','test','test','low',None),context,
                optimize=dict(program='dspy',train=rows,dev=[rows[0]|{'group':'dev'}],max_metric_calls=5))
            self.assertGreater(len(response.data['evaluation']['proposals']),0)
            self.assertFalse(response.data['reviewed'])
            self.assertTrue(all('held_out' not in prompt for prompt in native.prompts))

    async def test_rlm_action_trace_is_available_to_upstream_gepa_feedback(self):
        import dspy
        from dspy_runtime.engines import NativeEngine
        from dspy_runtime.programs import build_student
        from dspy_runtime.interpreter import InterpreterFactory
        from dspy.teleprompt.gepa.gepa_utils import DspyAdapter
        from invocation_broker import validate_budget
        class Channel:
            def call(self, kind, payload):
                if kind == 'lm':
                    return dict(text='[[ ## reasoning ## ]]\ncheck\n[[ ## code ## ]]\nSUBMIT(result_json=\'{"answer":"42"}\')\n[[ ## completed ## ]]',operation_id='x',tokens=1)
        channel=Channel()
        lm=dspy.LM('mimir/test',engine=NativeEngine(channel),cache=False,num_retries=0)
        budget=validate_budget({'max_depth':0})
        student=build_student('rlm',lm,InterpreterFactory(channel,budget),budget)
        metric=lambda *args: dspy.Prediction(score=1.0,feedback='correct')
        adapter=DspyAdapter(student,metric,{n:lambda **kwargs:dict(score=1.0,feedback='correct') for n,p in student.named_predictors()},num_threads=1)
        candidate={n:p.signature.instructions for n,p in student.named_predictors()}
        example=dspy.Example(objective='q',evidence='42',expected='42').with_inputs('objective','evidence')
        with dspy.context(lm=lm,adapter=dspy.ChatAdapter()):
            batch=await asyncio.to_thread(adapter.evaluate,[example],candidate,capture_traces=True)
            feedback=adapter.make_reflective_dataset(candidate,batch,['investigator.generate_action'])
        self.assertEqual(feedback['investigator.generate_action'][0]['Feedback'],'correct')

    async def test_guest_host_access_denied_and_no_secret_environment(self):
        native = FakeNative()
        code = '''import os, json
checks = [os.environ.get("MIMIR_TEST_SECRET") is None]
for op in [lambda: open("C:/Windows/win.ini").read(), lambda: __import__("urllib.request", fromlist=["urlopen"]).urlopen("https://example.com",timeout=1).read(), lambda: __import__("subprocess").run(["whoami"])]:
 try:
  op()
  checks.append(False)
 except Exception:
  checks.append(True)
SUBMIT(result_json=json.dumps({"denied":checks}))'''
        native.reply = lambda prompt: '[[ ## reasoning ## ]]\ncheck\n[[ ## code ## ]]\n' + code + '\n[[ ## completed ## ]]'
        with patch.dict("os.environ", {"MIMIR_TEST_SECRET": "synthetic-secret"}):
            result, trace, broker = await self.run_runtime(native)
        self.assertEqual(result.data["denied"], [True, True, True, True])
        self.assertEqual(len(broker.interpreters), 0)

    async def test_native_engine_sync_async_usage_and_control_rejection(self):
        from dspy_runtime.engines import NativeEngine, AsyncNativeEngine
        from dspy.lm15 import Request, Message, Config, InvalidRequestError
        class Channel:
            def call(self, kind, payload):
                return {"text": "answer", "operation_id": "attempt-1", "tokens": 17}
        engine = NativeEngine(Channel())
        request = Request(model="mimir/test", messages=[Message.user("q")])
        result = engine.complete(request)
        self.assertEqual(result.text, "answer")
        self.assertEqual(result.provider_data["mimir"]["native_reported_total_tokens"], 17)
        self.assertEqual((await AsyncNativeEngine(engine).complete(request)).text, "answer")
        with self.assertRaises(InvalidRequestError):
            engine.complete(Request(model="mimir/test", messages=[Message.user("q")], config=Config(temperature=.7)))

    async def run_runtime(self, native, budget=None):
        from dspy_runtime.host import run_program
        with tempfile.TemporaryDirectory() as tmp:
            broker = InvocationBroker(native, budget={"max_seconds": 60, **(budget or {})})
            context = ResearchContext(broker, SourceStore(), Path(tmp),
                                      {"program": "rlm", "budget": broker.budget, "sources": []})
            result, trace = await run_program(ResearchRequest("test", "Answer 42", "test", "test", "low", None), context)
            return result, json.loads(Path(trace).read_text()), broker

    async def test_actual_nested_rlm_and_concurrency_one(self):
        native = FakeNative()
        def reply(prompt):
            if "Nested-question" in prompt and 'subset' in prompt:
                code = 'SUBMIT(answer="42")'
            else:
                code = 'child=dspy.RLM("subset, query -> answer"); child(subset="42",query="Nested-question"); SUBMIT(result_json=\'{"answer":"42","sources":[],"claims":[],"gaps":[]}\')'
            return '[[ ## reasoning ## ]]\nCheck evidence\n[[ ## code ## ]]\n' + code + '\n[[ ## completed ## ]]'
        native.reply = reply
        result, trace, broker = await self.run_runtime(native, {"max_depth": 1})
        self.assertEqual(result.data["answer"], "42")
        self.assertEqual([r["depth"] for r in broker.usage_calls], [0, 1])
        self.assertTrue(any(r["kind"] == "child" for r in trace["events"]))

    async def test_fatal_subcall_cannot_be_hidden_by_submit(self):
        native = FakeNative()
        native.reply = lambda prompt: '[[ ## reasoning ## ]]\ncheck\n[[ ## code ## ]]\nllm_query("child"); SUBMIT(result_json=\'{"answer":"42"}\')\n[[ ## completed ## ]]'
        with self.assertRaises(ValueError):
            await self.run_runtime(native, {"max_attempts": 1})

    async def test_policy_override_cannot_be_hidden_by_submit(self):
        native = FakeNative()
        native.reply = lambda prompt: '[[ ## reasoning ## ]]\ncheck\n[[ ## code ## ]]\ntry:\n dspy.RLM("x -> y", max_iters=100)(x="x")\nexcept Exception:\n pass\nSUBMIT(result_json=\'{"answer":"42"}\')\n[[ ## completed ## ]]'
        with self.assertRaises(ValueError):
            await self.run_runtime(native, {"max_depth": 1})

    async def test_cancel_infinite_guest_execution_joins_process(self):
        from dspy_runtime.host import run_program
        native = FakeNative()
        native.reply = lambda prompt: '[[ ## reasoning ## ]]\nloop\n[[ ## code ## ]]\nwhile True: pass\n[[ ## completed ## ]]'
        with tempfile.TemporaryDirectory() as tmp:
            broker = InvocationBroker(native, budget={"max_seconds": 60})
            context = ResearchContext(broker, SourceStore(), Path(tmp), {"program": "rlm", "budget": broker.budget, "sources": []})
            task = asyncio.create_task(run_program(ResearchRequest("loop", "q", "test", "test", "low", None), context))
            await asyncio.sleep(4)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 10)
