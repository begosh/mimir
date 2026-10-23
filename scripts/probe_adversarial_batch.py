"""Original-request planning plus five blinded mixed-evidence checker batches."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from random import Random
import sys
import time

from atomic_worker import worker_contract
from backend import create_swarm_backend
from engine import _write_artifact
from extraction_checks import check_extraction
from post_worker import check_results
from probe_post_worker import CaptureBroker
from prompt_data import model_view
from recursive_planner import RecursivePlanner


async def probe(target):
    target=Path(target);target.mkdir(parents=True,exist_ok=False)
    saved=json.loads(Path('.mimir/live-worker-batching-20261023-fresh/checkpoint.json').read_text(encoding='utf-8'))
    source={**saved['research_config']['sources'][0],'status':'synthetic_fixture'}
    native=create_swarm_backend('codex','gpt-6.1-sol',max_concurrency=1,effort='low',timeout_seconds=180,worker_transport='native')
    broker=CaptureBroker(native,budget={'max_attempts':13,'max_seconds':240},journal=target/'operations.jsonl');broker.target=target
    record={'request':'Give me the best napoli pizza dough recipe.','runs':[],
            'planning_context':'Original request with supplied synthetic source; no host interpretation or dough-only domain override.'}
    try:
        planner=RecursivePlanner(broker,max_leaves=8,max_depth=3,available_sources=[model_view(source,[source])])
        started=time.monotonic()
        try:
            brief,leaves,trace=await planner.plan(record['request'])
            record['planning']={'brief':brief,'leaves':leaves,'trace':trace}
        except Exception as exc:
            record['planning']={'error':str(exc),'trace':planner.state}
        record['planning_seconds']=round(time.monotonic()-started,3)
        _write_artifact(target/'results.json',json.dumps(record,ensure_ascii=False,indent=2))
        print(json.dumps({'planning_status':planner.state['status'],'seconds':record['planning_seconds']}),flush=True)
        candidates=[]
        for node_id,envelope in saved['completed_data'].items():
            node=saved['graph']['nodes'][node_id]
            candidates.append({'origin':node_id,'expected':'PASS','contract':worker_contract(node['input_artifacts']['task_contract']),
                'result':deepcopy(envelope['result']),'supplied_sources':[source]})
        mix=next(c for c in candidates if c['origin'].endswith('mix_knead'))
        bad=deepcopy(mix);bad.update(origin='omitted_kneading',expected='FAIL')
        bad['result']['answer']='L03: Dissolve the yeast in water, add flour and salt; mix for 2 minutes. Temperatures unstated.'
        candidates.append(bad)
        fermentation=next(c for c in candidates if c['origin'].endswith('ferment_proof'))
        bad=deepcopy(fermentation);bad.update(origin='swapped_time_temperature',expected='FAIL')
        bad['result']['answer']=bad['result']['answer'].replace('18 hours at 20 C','20 hours at 18 C')
        candidates.append(bad)
        shape=next(c for c in candidates if c['origin'].endswith('divide_shape'))
        bad=deepcopy(shape);bad.update(origin='omitted_rolling_pin',expected='FAIL')
        bad['result']['answer']=bad['result']['answer'].replace('Do not use a rolling pin.','')
        # Claims still contain the omitted step: context cannot repair the answer.
        candidates.append(bad)
        record['code_checks']={c['origin']:check_extraction(c['result'],c['supplied_sources'])
            for c in candidates if c['contract']['operation']=='extract'}
        for repeat in range(5):
            batch=deepcopy(candidates);Random(740274+repeat).shuffle(batch);mapping={};expected={}
            for i,c in enumerate(batch,1):
                key=f'candidate_{i}';mapping[key]=c.pop('origin');expected[key]=c.pop('expected');c['id']=key
            before=len(broker.usage_calls);started=time.monotonic()
            checks=await check_results(broker,{'candidates':batch})
            verdicts={c['id']:c['verdict'] for c in checks['checks']}
            negatives=sum(v=='FAIL' for v in expected.values());positives=len(expected)-negatives
            run={'repeat':repeat+1,'mapping':mapping,'checks':checks,'expected':expected,
                'false_pass':sum(expected[k]=='FAIL' and verdicts[k]=='PASS' for k in expected),
                'false_fail':sum(expected[k]=='PASS' and verdicts[k]=='FAIL' for k in expected),
                'negative_count':negatives,'positive_count':positives,'seconds':round(time.monotonic()-started,3),
                'tokens':sum(c.get('tokens_used') or 0 for c in broker.usage_calls[before:])}
            record['runs'].append(run)
            _write_artifact(target/'results.json',json.dumps(record,ensure_ascii=False,indent=2))
            print(json.dumps({k:v for k,v in run.items() if k not in {'mapping','checks','expected'}}),flush=True)
    finally:
        await broker.aclose()
        record['usage_calls']=broker.usage_calls
        _write_artifact(target/'results.json',json.dumps(record,ensure_ascii=False,indent=2))


if __name__=='__main__':
    asyncio.run(probe(sys.argv[1]))
