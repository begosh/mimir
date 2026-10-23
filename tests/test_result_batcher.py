"""Batching preserves per-candidate isolation and releases individual verdicts."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from backend import SwarmResult
from scheduler import execute_graph
from task_graph import Blackboard, TaskStatus
from test_result_gate import graph, Worker
from result_batcher import ResultBatcher


class BatchedWorker(Worker):
    batch_result_checks=True
    async def spawn_restricted(self,prompt,role,**options):
        if role!='Mimir-Result-Checker':
            return await super().spawn_restricted(prompt,role,**options)
        self.calls.append(role)
        context=json.loads(prompt.split('INPUTS:\n')[1])
        self.context=context
        checks=[{'id':c['id'],'verdict':'PASS' if c['result']['answer']=='2 minutes' else 'FAIL',
                 'issues':[] if c['result']['answer']=='2 minutes' else ['Invented duration']} for c in context['candidates']]
        return SwarmResult(role,'SUCCESS',{'checks':checks},json.dumps({'checks':checks}))


def test_two_ready_results_share_one_check_and_failed_dependent_remains_blocked():
    async def run():
        g=graph();worker=BatchedWorker();bb=Blackboard('batch')
        async def dispatch(node,prompt):
            value={'answer':'9 minutes' if node.id=='bad' else '2 minutes'} if node.role=='Atomic-Worker' else 'child'
            return SwarmResult(node.role,'SUCCESS',value,json.dumps(value))
        results=await execute_graph(g,worker,blackboard=bb,research_dispatch=dispatch)
        assert set(results)=={'good','good_child'}
        assert worker.calls.count('Mimir-Result-Checker')==1
        assert len(worker.context['candidates'])==2
        assert all(c['source_refs'] for c in worker.context['candidates'])
        assert len(worker.context['source_registry']) == 1
        assert g.nodes['bad_child'].status==TaskStatus.CANCELLED
        assert 'bad_result' not in bb.artifacts
    asyncio.run(run())


def test_single_result_flushes_without_waiting_for_its_dependent():
    async def run():
        g=graph();del g.nodes['bad'];del g.nodes['bad_child'];worker=BatchedWorker()
        results=await asyncio.wait_for(execute_graph(g,worker),timeout=4)
        assert set(results)=={'good','good_child'}
        assert worker.calls.count('Mimir-Result-Checker')==1
    asyncio.run(run())


def test_batch_error_fails_all_waiters_and_close_joins_pending_work():
    async def run():
        class Invalid(BatchedWorker):
            async def spawn_restricted(self,**options):
                return SwarmResult('Mimir-Result-Checker','SUCCESS',{'checks':[]},'raw')
        g=graph();batch=ResultBatcher(Invalid(),size=2,delay=.01)
        replies=await asyncio.gather(*(batch.check(n,{'answer':'2 minutes'},{})
            for n in g.nodes.values() if n.role=='Atomic-Worker'),return_exceptions=True)
        assert all(isinstance(r,ValueError) for r in replies)
        await batch.close()
        assert not batch.pending
        waiting=ResultBatcher(BatchedWorker(),size=2,delay=10)
        task=asyncio.create_task(waiting.check(g.nodes['good'],{'answer':'2 minutes'},{}))
        await asyncio.sleep(0)
        await waiting.close()
        result=await asyncio.gather(task,return_exceptions=True)
        assert isinstance(result[0],asyncio.CancelledError)
    asyncio.run(run())
