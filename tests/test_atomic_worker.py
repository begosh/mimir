"""Atomic workers receive operation instructions without research/orchestration noise."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from atomic_worker import atomic_prompt
from scheduler import execute_graph
from task_graph import TaskGraph,TaskNode
from backend import SwarmResult


def contract():
    return {'objective':'Extract mixing instructions','expected_output':'Ordered steps',
            'acceptance_check':'Every step matches source','operation':'extract','inputs':['fixture:source'],
            'parent':'secret_parent','depth':3,'simplicity_review':{'reason':'secret_review'}}


def test_operation_wrapper_omits_research_goal_and_orchestration_metadata():
    prompt=atomic_prompt(contract(),original_request='Recommend a recipe')
    assert 'Recommend a recipe' not in prompt
    assert 'secret_parent' not in prompt and 'secret_review' not in prompt
    assert 'No general knowledge or retrieval' in prompt
    assert 'Do not label a supplied web excerpt local_file' in prompt
    retrieval={**contract(),'operation':'retrieve'}
    assert 'Recommend a recipe' in atomic_prompt(retrieval,original_request='Recommend a recipe')


def test_scheduler_supplies_inline_source_and_uses_restricted_dispatch():
    class Worker:
        default_model='agreed'
        default_effort='low'
        max_concurrency=1
        async def spawn_restricted(self,**options):
            self.options=options
            return SwarmResult('Atomic-Worker','SUCCESS',{'answer':'Mix for 2 minutes.'},'{"answer":"Mix for 2 minutes."}')
        async def spawn(self,**options):
            raise AssertionError('Extraction must not use tool-enabled dispatch')
    async def run():
        worker=Worker()
        graph=TaskGraph('Unrelated original goal')
        graph.add_node(TaskNode('mix','Atomic-Worker','Mix',atomic_prompt(contract()),
            input_artifacts={'task_contract':contract(),'worker_wrapper':'atomic_v1',
                             'supplied_sources':[{'id':'fixture:source','text':'L01 Mix for 2 minutes.'}]}))
        results=await execute_graph(graph,worker)
        assert 'L01 Mix for 2 minutes.' in worker.options['prompt']
        assert 'Unrelated original goal' not in worker.options['prompt']
        assert 'mix' in results
    asyncio.run(run())
