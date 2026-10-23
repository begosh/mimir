"""Bounded coalescing of completed results, with individual admission verdicts."""
import asyncio
from atomic_worker import worker_contract
from post_worker import check_results, result_gate_policy


class ResultBatcher:
    def __init__(self, backend, *, size=4, delay=2.0):
        self.backend = backend
        self.size = min(4, max(1, size))
        self.delay = delay
        self.pending = []
        self.timer = None
        self.tasks = set()

    async def check(self, node, result, dependencies):
        future = asyncio.get_running_loop().create_future()
        self.pending.append((node, result, dependencies, future))
        if len(self.pending) >= self.size:
            self.flush()
        elif self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(self.delay, self.flush)
        return await future

    def flush(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if not self.pending:
            return
        batch, self.pending = self.pending[:self.size], self.pending[self.size:]
        task = asyncio.create_task(self.run(batch))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        if self.pending:
            self.flush()

    async def run(self, batch):
        candidates = [{"id": f"candidate_{i}", "contract": worker_contract(node.input_artifacts["task_contract"]),
            "result": result, "supplied_sources": node.input_artifacts.get("supplied_sources", []),
            "dependency_results": dependencies} for i, (node, result, dependencies, _) in enumerate(batch, 1)]
        try:
            checked = await check_results(self.backend, {"candidates": candidates})
            verdicts = {v["id"]: v for v in checked["checks"]}
            for i, (_, _, _, future) in enumerate(batch, 1):
                if not future.done():
                    future.set_result({**verdicts[f"candidate_{i}"], "policy": result_gate_policy()})
        except (Exception, asyncio.CancelledError) as exc:
            for _, _, _, future in batch:
                if not future.done():
                    if isinstance(exc, asyncio.CancelledError):
                        future.cancel()
                    else:
                        future.set_exception(exc)

    async def close(self):
        if self.timer:
            self.timer.cancel()
        for _, _, _, future in self.pending:
            if not future.done():
                future.cancel()
        self.pending.clear()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
