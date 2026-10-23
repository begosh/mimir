"""Repair stays within its original contract and cannot release failed results."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from backend import SwarmResult
from post_worker import result_repair_policy
from scheduler import execute_graph, validate_retained
from task_graph import Blackboard, TaskGraph, TaskStatus
from test_result_gate import graph, Worker


class RepairWorker(Worker):
    async def spawn_restricted(self,prompt,role,**options):
        if role=='Mimir-Result-Repairer':
            self.calls.append(role)
            data={'action':'REPHRASE','objective':'Extract exactly the stated duration; do not substitute another value.',
                  'reason':'The answer invented a duration'}
            return SwarmResult(role,'SUCCESS',data,json.dumps(data))
        return await super().spawn_restricted(prompt,role,**options)


def test_repair_succeeds_without_mutating_original_contract_and_releases_child_once():
    async def run():
        g=graph(); del g.nodes['good']; del g.nodes['good_child']
        g.nodes['bad'].input_artifacts['result_repair']=result_repair_policy()
        worker=RepairWorker(); bb=Blackboard('repair'); snapshots=[]; commits=[]; prompts=[]
        original=g.nodes['bad'].prompt
        async def dispatch(node,prompt):
            prompts.append(prompt)
            data={'answer':'9 minutes' if node.retry_count==0 else '2 minutes'} if node.id=='bad' else 'child'
            return SwarmResult(node.role,'SUCCESS',data,json.dumps(data))
        results=await execute_graph(g,worker,blackboard=bb,research_dispatch=dispatch,
            on_result_attempt=lambda n:snapshots.append(g.to_dict()),
            on_result_commit=lambda n,e:commits.append(n.id))
        assert commits==['bad','bad_child'] and set(results)==set(commits)
        assert g.nodes['bad'].retry_count==1 and g.nodes['bad'].prompt==original
        assert 'ORIGINAL ACCEPTANCE CONTRACT' in prompts[1]
        attempts=results['bad']['result_attempts']
        assert [a['status'] for a in attempts]==['FAIL','PASS']
        assert attempts[0]['result']['answer']=='9 minutes'
        assert g.nodes['bad'].rejected_output is None
        restored=TaskGraph.from_dict(g.to_dict())
        assert restored.nodes['bad'].result_attempts==attempts
        validate_retained(restored,worker,results)
        assert any(s['nodes']['bad']['retry_count']==1 and s['nodes']['bad']['status']=='RUNNING' for s in snapshots)
    asyncio.run(run())


def test_two_retries_exhaust_then_block_child_without_touching_other_branch():
    async def run():
        g=graph(); g.nodes['bad'].input_artifacts['result_repair']=result_repair_policy()
        worker=RepairWorker(); executions=[]
        async def dispatch(node,prompt):
            executions.append(node.id)
            data={'answer':'9 minutes' if node.id=='bad' else '2 minutes'} if node.role=='Atomic-Worker' else 'child'
            return SwarmResult(node.role,'SUCCESS',data,json.dumps(data))
        results=await execute_graph(g,worker,research_dispatch=dispatch)
        assert set(results)=={'good','good_child'}
        assert executions.count('bad')==3 and 'bad_child' not in executions
        assert worker.calls.count('Mimir-Result-Repairer')==2
        assert g.nodes['bad'].retry_count==2 and len(g.nodes['bad'].result_attempts)==3
        assert g.nodes['bad_child'].status==TaskStatus.CANCELLED
    asyncio.run(run())


def test_invalid_checker_never_triggers_task_repair():
    async def run():
        g=graph(); g.nodes['bad'].input_artifacts['result_repair']=result_repair_policy()
        worker=RepairWorker(malformed=True)
        await execute_graph(g,worker)
        assert 'Mimir-Result-Repairer' not in worker.calls and g.nodes['bad'].retry_count==0
    asyncio.run(run())
