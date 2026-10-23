"""Fresh live checks gate recorded fixture findings before blackboard release."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

from atomic_worker import atomic_prompt
from backend import create_swarm_backend, SwarmResult
from engine import _write_artifact
from post_worker import result_gate_policy
from probe_post_worker import CaptureBroker
from scheduler import execute_graph
from task_graph import Blackboard, TaskGraph, TaskNode


async def probe(target):
    target=Path(target); target.mkdir(parents=True,exist_ok=False)
    saved=json.loads(Path('.mimir/pizza-atomic-wrapper-blinded-20261023/execution.json').read_text(encoding='utf-8'))
    task=deepcopy(next(t for t in saved['tasks'] if t['id'].endswith('fermentation')))
    result=deepcopy(saved['results'][task['id']]['result'])
    graph=TaskGraph('Test supplied fermentation findings')
    for name in ('candidate_a','candidate_b'):
        graph.add_node(TaskNode(name,'Atomic-Worker',name,atomic_prompt(task),input_artifacts={
            'worker_wrapper':'atomic_v1','task_contract':task,'result_gate':result_gate_policy(),
            'supplied_sources':[{'id':'fixture:pizza_extraction_source','status':'synthetic_fixture','text':saved['source_text']}]}))
        graph.add_node(TaskNode(name+'_dependent','Probe-Consumer','Consume accepted result','Use accepted parent',dependencies={name}))
    native=create_swarm_backend('codex','gpt-6.1-sol',max_concurrency=1,effort='low',timeout_seconds=180,worker_transport='native')
    broker=CaptureBroker(native,budget={'max_attempts':2,'max_seconds':120},journal=target/'operations.jsonl')
    broker.target=target
    bb=Blackboard('result-gate-live'); committed=[]; executed=[]; started=time.monotonic()
    record={'synthetic_fixture':True,'injected_recorded_outputs':True}
    async def dispatch(node,prompt):
        executed.append(node.id)
        value=deepcopy(result) if node.role=='Atomic-Worker' else {'answer':'Accepted parent consumed'}
        if node.id=='candidate_b':
            value['answer']+=' Final-proof temperature: 25 C.'
        return SwarmResult(node.role,'SUCCESS',value,json.dumps(value,ensure_ascii=False))
    try:
        results=await execute_graph(graph,broker,blackboard=bb,research_dispatch=dispatch,
            on_result_commit=lambda n,e: committed.append(n.id))
        record.update(results=results,graph=graph.to_dict(),committed=committed,executed=executed,
                      blackboard_artifacts=bb.artifacts)
        assert set(results)=={'candidate_a','candidate_a_dependent'}
        assert 'candidate_b_dependent' not in executed and 'candidate_b_result' not in bb.artifacts
        assert graph.nodes['candidate_b'].rejected_output['result']['answer'].endswith('25 C.')
        print(json.dumps({'accepted':list(results),'blocked_dependent':'candidate_b_dependent','committed':committed}),flush=True)
    finally:
        await broker.aclose()
        record.update(seconds=round(time.monotonic()-started,3),usage_calls=broker.usage_calls,
                      tokens=sum(c.get('tokens_used') or 0 for c in broker.usage_calls))
        _write_artifact(target/'results.json',json.dumps(record,ensure_ascii=False,indent=2))
        print(json.dumps({'seconds':record['seconds'],'tokens':record['tokens']}),flush=True)


if __name__=='__main__':
    asyncio.run(probe(sys.argv[1]))
