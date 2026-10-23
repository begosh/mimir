"""Live repair and recheck of an injected failed fixture result."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

from atomic_worker import atomic_prompt
from backend import create_swarm_backend, SwarmResult
from engine import _write_artifact
from post_worker import result_gate_policy, result_repair_policy
from probe_post_worker import CaptureBroker
from research_contract import worker_result_schema
from scheduler import execute_graph
from task_graph import Blackboard, TaskGraph, TaskNode


async def probe(target):
    target=Path(target); target.mkdir(parents=True,exist_ok=False)
    saved=json.loads(Path('.mimir/pizza-atomic-wrapper-blinded-20261023/execution.json').read_text(encoding='utf-8'))
    task=deepcopy(next(t for t in saved['tasks'] if t['id'].endswith('fermentation')))
    result=deepcopy(saved['results'][task['id']]['result'])
    result['answer']+=' Final-proof temperature: 25 C.'
    graph=TaskGraph('Extract supplied dough fermentation stages')
    graph.add_node(TaskNode('fermentation','Atomic-Worker','Fermentation',atomic_prompt(task),
        json_schema=worker_result_schema(task['max_output_words']),max_answer_words=task['max_output_words'],
        input_artifacts={'worker_wrapper':'atomic_v1','task_contract':task,'result_gate':result_gate_policy(),
            'result_repair':result_repair_policy(),'supplied_sources':[{
                'id':'fixture:pizza_extraction_source','status':'synthetic_fixture','retrieval_type':'local_file',
                'retrieved_at':'','text':saved['source_text']}]}))
    graph.add_node(TaskNode('consumer','Probe-Consumer','Consume accepted result','Consume parent',dependencies={'fermentation'}))
    native=create_swarm_backend('codex','gpt-6.1-sol',max_concurrency=1,effort='low',timeout_seconds=180,worker_transport='native')
    broker=CaptureBroker(native,budget={'max_attempts':7,'max_seconds':120},journal=target/'operations.jsonl')
    broker.target=target
    bb=Blackboard('repair-live'); committed=[]; started=time.monotonic(); record={}
    async def dispatch(node,prompt):
        if node.id=='consumer':
            value={'answer':'Accepted fermentation consumed'}
            return SwarmResult(node.role,'SUCCESS',value,json.dumps(value))
        if node.retry_count==0:
            return SwarmResult(node.role,'SUCCESS',deepcopy(result),json.dumps(result,ensure_ascii=False))
        return await broker.spawn_restricted(prompt=prompt,role=node.role,json_schema=node.json_schema)
    def checkpoint(node):
        _write_artifact(target/'attempts.json',json.dumps(graph.to_dict(),ensure_ascii=False,indent=2))
    try:
        outputs=await execute_graph(graph,broker,blackboard=bb,research_dispatch=dispatch,
            on_result_attempt=checkpoint,on_result_commit=lambda n,e:committed.append(n.id))
        record.update(results=outputs,graph=graph.to_dict(),committed=committed)
        assert set(outputs)=={'fermentation','consumer'}
        assert graph.nodes['fermentation'].result_attempts[0]['status']=='FAIL'
        assert graph.nodes['fermentation'].result_attempts[-1]['status']=='PASS'
        assert graph.nodes['fermentation'].retry_count<=2
        print(json.dumps({'committed':committed,'retries':graph.nodes['fermentation'].retry_count,
                          'answer':outputs['fermentation']['result']['answer']}),flush=True)
    finally:
        await broker.aclose()
        record.update(seconds=round(time.monotonic()-started,3),usage_calls=broker.usage_calls,
                      tokens=sum(c.get('tokens_used') or 0 for c in broker.usage_calls))
        _write_artifact(target/'results.json',json.dumps(record,ensure_ascii=False,indent=2))
        print(json.dumps({'seconds':record['seconds'],'tokens':record['tokens']}),flush=True)


if __name__=='__main__':
    asyncio.run(probe(sys.argv[1]))
