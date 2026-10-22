"""Scheduler regressions using synchronization rather than latency thresholds."""
import asyncio
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend import BaseSwarmBackend, SwarmResult
from task_graph import Blackboard, TaskGraph, TaskNode, TaskStatus
from scheduler import validate_retained
from mimir_config import ConfigurationRequired


class Worker(BaseSwarmBackend):
    def __init__(self, implementation, concurrency=2):
        super().__init__("agreed", concurrency)
        self.implementation = implementation

    async def spawn(self, prompt, role="Worker", **kwargs):
        return await self.implementation(prompt, role, **kwargs)


def make_graph():
    graph = TaskGraph("review")
    graph.add_node(TaskNode("slow", "slow", "Slow", "slow"))
    graph.add_node(TaskNode("fast", "fast", "Fast", "fast"))
    graph.add_node(TaskNode("dependent", "dependent", "Dependent", "dependent", dependencies={"fast"}))
    return graph


class Scheduling(unittest.IsolatedAsyncioTestCase):
    async def test_ready_dependency_starts_before_unrelated_sibling_finishes(self):
        release_slow = asyncio.Event()
        dependent_started = asyncio.Event()
        commits = []

        async def implementation(prompt, role, **kwargs):
            if role == "slow":
                await release_slow.wait()
            if role == "dependent":
                self.assertIn("fast output", prompt)
                self.assertEqual([node for node, _ in commits], ["fast"])
                dependent_started.set()
            return SwarmResult(role, "SUCCESS", f"{role} output", f"{role} output", tokens_used=11)

        graph = make_graph()
        worker = Worker(implementation)
        execution = asyncio.create_task(worker.execute_graph(graph, Blackboard("review"),
                        on_result_commit=lambda node, envelope: commits.append((node.id, envelope))))
        try:
            await asyncio.wait_for(dependent_started.wait(), 2)
            self.assertEqual(graph.nodes["slow"].status, TaskStatus.RUNNING)
            self.assertEqual(commits[0][1]["raw_response"], "fast output")
            self.assertEqual(commits[0][1]["tokens_used"], 11)
            self.assertEqual(len(commits[0][1]["input_fingerprint"]), 64)
        finally:
            release_slow.set()
        results = await execution
        self.assertEqual(set(results), set(graph.nodes))

    async def test_scheduler_limits_workers_even_without_adapter_semaphore(self):
        releases = {node: asyncio.Event() for node in ("a", "b", "c")}
        started = []
        entered = asyncio.Event()

        async def implementation(prompt, role, **kwargs):
            started.append(role)
            entered.set()
            await releases[role].wait()
            return SwarmResult(role, "SUCCESS", role, role)

        graph = TaskGraph("bounded")
        for nid in releases:
            graph.add_node(TaskNode(nid, nid, nid, nid))
        task = asyncio.create_task(Worker(implementation, concurrency=1).execute_graph(graph))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            self.assertEqual(started, ["a"])
            self.assertEqual(graph.nodes["b"].status, TaskStatus.PENDING)
        finally:
            for release in releases.values():
                release.set()
        await task
        self.assertEqual(started, ["a", "b", "c"])

    async def test_successful_result_survives_cancel_and_is_reused_with_provenance(self):
        committed = asyncio.Event()
        blocked = asyncio.Event()
        cleanup_started = asyncio.Event()
        cleanup_release = asyncio.Event()
        retained = {}
        calls = []

        async def implementation(prompt, role, **kwargs):
            calls.append(role)
            if role == "slow":
                blocked.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleanup_started.set()
                    await cleanup_release.wait()
            return SwarmResult(role, "SUCCESS", role, role)

        def commit(node, envelope):
            retained[node.id] = envelope
            committed.set()

        graph = make_graph()
        worker = Worker(implementation)
        execution = asyncio.create_task(worker.execute_graph(graph, on_result_commit=commit))
        await asyncio.wait_for(blocked.wait(), 2)
        await asyncio.wait_for(committed.wait(), 2)
        execution.cancel()
        await asyncio.wait_for(cleanup_started.wait(), 2)
        execution.cancel()  # Repeated cancellation cannot bypass cleanup join.
        await asyncio.sleep(0)
        self.assertFalse(execution.done())
        cleanup_release.set()
        with self.assertRaises(asyncio.CancelledError):
            await execution
        self.assertIn("fast", retained)

        restored_graph = TaskGraph.from_dict(graph.to_dict())
        for node in restored_graph.nodes.values():
            if node.status != TaskStatus.COMPLETED:
                node.status = TaskStatus.PENDING
        calls.clear()

        async def successful(prompt, role, **kwargs):
            calls.append(role)
            return SwarmResult(role, "SUCCESS", role, role)

        worker.implementation = successful
        result = await worker.execute_graph(restored_graph, Blackboard("restored"), retained_results=retained)
        self.assertNotIn("fast", calls)
        self.assertEqual(set(result), set(graph.nodes))

    async def test_retained_results_reject_changed_inputs_data_and_profile(self):
        calls = []

        async def implementation(prompt, role, **kwargs):
            calls.append(role)
            return SwarmResult(role, "SUCCESS", {"finding": role}, role)

        graph = TaskGraph("original goal")
        graph.add_node(TaskNode("source", "Analyst", "Source", "Inspect"))
        worker = Worker(implementation)
        results = await worker.execute_graph(graph)
        validate_retained(graph, worker, results)
        for variation in ("prompt", "goal", "data", "raw", "model", "dependencies", "execution_identity"):
            resumed = TaskGraph.from_dict(graph.to_dict())
            retained = copy.deepcopy(results)
            worker.default_model = "agreed"
            worker.execution_identity = None
            if variation == "prompt":
                resumed.nodes["source"].prompt += " changed"
            elif variation == "goal":
                resumed.goal += " changed"
            elif variation == "data":
                retained["source"]["result"] = {"finding": "changed"}
            elif variation == "raw":
                retained["source"]["raw_response"] += "changed"
            elif variation == "model":
                worker.default_model = "changed"
            elif variation == "execution_identity":
                worker.execution_identity = "provider or native tools configuration changed"
            else:
                resumed.add_node(TaskNode("new", "Analyst", "New", "New"))
                resumed.nodes["source"].dependencies = {"new"}
            calls.clear()
            with self.subTest(variation=variation), self.assertRaises(ValueError):
                validate_retained(resumed, worker, retained)
            self.assertFalse(calls)

    async def test_commit_failure_joins_other_workers_and_prevents_dependents(self):
        cleaning = asyncio.Event()
        released = asyncio.Event()
        started = []

        async def implementation(prompt, role, **kwargs):
            started.append(role)
            if role == "slow":
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await released.wait()
            return SwarmResult(role, "SUCCESS", role, role)

        def commit(node, envelope):
            raise OSError("Checkpoint storage unavailable")

        task = asyncio.create_task(Worker(implementation).execute_graph(make_graph(), on_result_commit=commit))
        await asyncio.wait_for(cleaning.wait(), 2)
        self.assertFalse(task.done())
        self.assertNotIn("dependent", started)
        released.set()
        with self.assertRaises(OSError):
            await task

    async def test_context_admission_failure_is_fatal_and_joins_peer_cleanup(self):
        peer_started = asyncio.Event()
        peer_cleaned = asyncio.Event()

        async def implementation(prompt, role, **kwargs):
            if role == "slow":
                peer_started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    await asyncio.sleep(0)
                    peer_cleaned.set()
            await peer_started.wait()
            raise ConfigurationRequired("Worker context exceeds --max-context-chars")

        with self.assertRaisesRegex(ConfigurationRequired, "max-context-chars"):
            await Worker(implementation).execute_graph(make_graph())
        self.assertTrue(peer_cleaned.is_set())
