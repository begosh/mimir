"""Controlled checker-call comparison on identical recorded fixture findings."""
import asyncio
import json
from pathlib import Path
import sys
import time

from backend import create_swarm_backend, SwarmResult
from engine import _write_artifact
from probe_post_worker import CaptureBroker
from post_worker import result_gate_policy
from scheduler import execute_graph
from task_graph import TaskGraph, TaskStatus, Blackboard


async def probe(target):
    target=Path(target);target.mkdir(parents=True,exist_ok=False)
    saved=json.loads(Path('.mimir/pizza-source-handoff-live-20261023-text/checkpoint.json').read_text(encoding='utf-8'))
    records=[]
    for batching in (False,True):
        folder=target/('batched' if batching else 'individual');folder.mkdir()
        graph=TaskGraph.from_dict(saved['graph'])
        for node in graph.nodes.values():
            node.status=TaskStatus.PENDING;node.output_data=None;node.result_attempts=[];node.retry_count=0
            node.input_artifacts['result_gate']=result_gate_policy()
            node.input_artifacts.pop('result_repair',None)
        native=create_swarm_backend('codex','gpt-6.1-sol',max_concurrency=2,effort='low',timeout_seconds=180,worker_transport='native')
        broker=CaptureBroker(native,budget={'max_attempts':6,'max_seconds':120},journal=folder/'operations.jsonl')
        broker.target=folder;broker.batch_result_checks=batching
        async def dispatch(node,prompt):
            result=saved['completed_data'][node.id]['result']
            return SwarmResult(node.role,'SUCCESS',result,json.dumps(result,ensure_ascii=False))
        started=time.monotonic()
        record={'batching':batching}
        try:
            results=await execute_graph(graph,broker,blackboard=Blackboard('batching-comparison'),research_dispatch=dispatch)
            record['verdicts']={nid:e['result_check']['verdict'] for nid,e in results.items()}
            assert len(results)==6 and all(v=='PASS' for v in record['verdicts'].values())
        finally:
            await broker.aclose()
            record.update(seconds=round(time.monotonic()-started,3),calls=len(broker.usage_calls),
                tokens=sum(c.get('tokens_used') or 0 for c in broker.usage_calls),usage_calls=broker.usage_calls)
            records.append(record)
            _write_artifact(target/'comparison.json',json.dumps(records,ensure_ascii=False,indent=2))
            print(json.dumps({k:v for k,v in record.items() if k!='usage_calls'}),flush=True)


if __name__=='__main__':
    asyncio.run(probe(sys.argv[1]))
