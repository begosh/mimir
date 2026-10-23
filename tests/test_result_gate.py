"""Rejected findings never release dependencies; accepted checks survive resume."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from atomic_worker import atomic_prompt
from backend import SwarmResult
from post_worker import result_gate_policy
from scheduler import execute_graph, validate_retained
from task_graph import Blackboard, TaskGraph, TaskNode, TaskStatus


def graph():
    g=TaskGraph('Extract supplied value')
    contract={'objective':'Extract value','operation':'extract','inputs':['source'],
              'expected_output':'Value','acceptance_check':'Matches source'}
    for name in ('good','bad'):
        g.add_node(TaskNode(name,'Atomic-Worker',name,atomic_prompt(contract),input_artifacts={
            'worker_wrapper':'atomic_v1','task_contract':contract,'result_gate':result_gate_policy(),
            'supplied_sources':[{'id':'source','text':'L01 Value: 2 minutes.'}]}))
        g.add_node(TaskNode(name+'_child','Child',name+'_child','Use parent result',dependencies={name}))
    return g


class Worker:
    default_model='agreed'; default_effort='low'; max_concurrency=2
    def __init__(self, *, malformed=False):
        self.calls=[]; self.malformed=malformed
    async def spawn_restricted(self, prompt, role, **options):
        self.calls.append(role)
        if role=='Mimir-Result-Checker':
            context=json.loads(prompt.split('INPUTS:\n')[1])
            value=context['candidates'][0]['result']['answer']
            data={'checks':[{'id':'candidate_1','verdict':'PASS' if value=='2 minutes' else 'FAIL',
                             'issues':[] if value=='2 minutes' else ['Invented duration']}]}
            if self.malformed:
                data={'checks':[]}
        else:
            data={'answer':'9 minutes' if 'TASK: Extract value' in prompt and options.get('bad') else '2 minutes'}
        return SwarmResult(role,'SUCCESS',data,json.dumps(data))
    async def spawn(self, prompt, role, **options):
        self.calls.append(role)
        return SwarmResult(role,'SUCCESS','Child executed','Child executed')


def test_failed_result_is_retained_and_cannot_enter_blackboard_or_release_child():
    async def run():
        g=graph(); worker=Worker(); bb=Blackboard('test'); committed=[]
        async def dispatch(node,prompt):
            data={'answer':'2 minutes' if node.id=='good' else '9 minutes'} if node.role=='Atomic-Worker' else 'child'
            worker.calls.append(node.id)
            return SwarmResult(node.role,'SUCCESS',data,json.dumps(data))
        results=await execute_graph(g,worker,blackboard=bb,research_dispatch=dispatch,
                                    on_result_commit=lambda n,e: committed.append(n.id))
        assert set(results)=={'good','good_child'}
        assert committed==['good','good_child']
        assert 'bad_result' not in bb.artifacts and 'good_result' in bb.artifacts
        assert g.nodes['bad'].status==TaskStatus.FAILED
        assert g.nodes['bad_child'].status==TaskStatus.CANCELLED
        assert 'bad_child' not in worker.calls
        assert g.nodes['bad'].rejected_output['result']['answer']=='9 minutes'
        assert results['good']['result_check']['verdict']=='PASS'
        assert not bb.artifact_contracts['good_result'].verification_passed
        validate_retained(g,worker,results)
        changed=deepcopy(results); changed['good']['result_check']['verdict']='FAIL'
        with pytest.raises(ValueError,match='result-check identity'):
            validate_retained(g,worker,changed)
        # Resume a graph containing only the accepted branch: no new calls.
        del g.nodes['bad']; del g.nodes['bad_child']
        before=len(worker.calls)
        restored=await execute_graph(g,worker,retained_results=results)
        assert restored==results and len(worker.calls)==before
    asyncio.run(run())


def test_checker_error_fails_closed_and_preserves_result():
    async def run():
        g=graph(); worker=Worker(malformed=True)
        results=await execute_graph(g,worker)
        assert results=={}
        assert all(g.nodes[name].rejected_output['result'] for name in ('good','bad'))
        assert worker.calls.count('Child')==0
    asyncio.run(run())
