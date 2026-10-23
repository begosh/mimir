"""Blinded, shuffled repeated checks on byte-identified recorded worker outputs."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from random import Random
import sys
import time

from atomic_worker import worker_contract
from backend import create_swarm_backend
from engine import _write_artifact
from post_worker import check_results, synthesis_context, synthesize
from probe_post_worker import CaptureBroker
from recursive_planner import RecursivePlanner


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def probe(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    paths = ['.mimir/pizza-execution-probe-20261022/execution.json',
             '.mimir/pizza-atomic-wrapper-blinded-20261023/execution.json']
    packets = [json.loads(Path(p).read_text(encoding='utf-8')) for p in paths]
    saved = packets[1]
    previous = json.loads(Path('.mimir/post-worker-prompts-live-20261023/results.json').read_text(encoding='utf-8'))
    identity = {'packets': {p: {node_id: {'answer': envelope['result']['answer'],
                             'answer_hash': digest(envelope['result']['answer']),
                             'result_hash': digest(envelope['result'])}
                      for node_id, envelope in packet['results'].items()} for p,packet in zip(paths,packets)},
                'later_matches_post_worker': all(digest(envelope['result']) == digest(next(
                    c['result'] for c in previous['checker_context']['candidates'] if previous['candidate_mapping'][c['id']]==node_id))
                    for node_id,envelope in saved['results'].items())}
    _write_artifact(target/'identity.json', json.dumps(identity, ensure_ascii=False, indent=2))
    native = create_swarm_backend('codex', 'gpt-6.1-sol', max_concurrency=1, effort='low',
                                 timeout_seconds=180, worker_transport='native')
    broker = CaptureBroker(native, budget={'max_attempts':12, 'max_seconds':300}, journal=target/'operations.jsonl')
    broker.target = target
    record = {'identity':identity, 'runs':[], 'expectations':{}}
    started = time.monotonic()
    base = [{'origin':node_id,'contract':worker_contract(next(t for t in saved['tasks'] if t['id']==node_id)),
             'result':deepcopy(envelope['result'])} for node_id,envelope in saved['results'].items()]
    for item in base:
        record['expectations'][item['origin']] = 'PASS'
    bad = deepcopy(next(c for c in base if c['origin'].endswith('fermentation')))
    bad['origin'] = 'negative_invented_temperature'
    bad['result']['answer'] += ' Final-proof temperature: 25 C.'
    base.append(bad)
    bad = deepcopy(next(c for c in base if c['origin'].endswith('mix_knead')))
    bad['origin'] = 'negative_missing_kneading'
    bad['result']['answer'] = 'Dissolve yeast in water, add flour and salt, and mix for 2 minutes.'
    base.append(bad)
    bad = deepcopy(next(c for c in base if c['origin'].endswith('shaping')))
    bad['origin'] = 'negative_missing_shaping_gaps'
    bad['result']['gaps'] = []
    base.append(bad)
    record['expectations'].update({c['origin']:'FAIL' for c in base if c['origin'].startswith('negative_')})
    old = Path('.mimir/post-worker-prompts-live-20261023/prompt-1.txt').read_text(encoding='utf-8').split('\n{"source":')[0]
    try:
        for repeat in range(5):
            for variant in ('original', 'clarified'):
                candidates = deepcopy(base)
                Random(740274+repeat).shuffle(candidates)
                mapping = {}
                for i,c in enumerate(candidates,1):
                    mapping[f'candidate_{i}'] = c.pop('origin')
                    c['id'] = f'candidate_{i}'
                context = {'source':saved['source_text'], 'candidates':candidates}
                if variant == 'original':
                    planner = RecursivePlanner(broker,budget={'max_calls':1,'max_seconds':120})
                    planner.deadline = time.monotonic()+120
                    checks = await planner.ask(old+'\n'+json.dumps(context,ensure_ascii=False),
                                               'Mimir-Result-Checker',field='checks_json')
                else:
                    checks = await check_results(broker, context)
                run = {'repeat':repeat+1,'variant':variant,'mapping':mapping,'checks':checks,
                       'mapped':[{**c,'origin':mapping[c['id']]} for c in checks['checks']]}
                record['runs'].append(run)
                _write_artifact(target/'results.json',json.dumps(record,ensure_ascii=False,indent=2))
                print(json.dumps({'repeat':repeat+1,'variant':variant,'verdicts':{
                    c['origin']:c['verdict'] for c in run['mapped']}}),flush=True)
        state = {'goal':previous['original_goal'],'completed_data':saved['results'],
                 'task_brief':{'constraints':['Dough only. No toppings, sauce or baking instructions.'],
                               'components':['ingredients','mix_knead','fermentation','shaping']},
                 'component_coverage':{'ingredients':'NOT RUN', **{c['origin'].split('.')[-1]:'PASS' for c in base[:3]}},
                 'source_registry':[{'id':'fixture:pizza_extraction_source','locator':'fixture:pizza_extraction_source',
                                     'status':'synthetic_fixture'}]}
        record['synthesis'],record['synthesis_context'] = await synthesize(broker,synthesis_context(state))
        # Qualify direct nested schemas on the native runtime, not just fake tests.
        planner = RecursivePlanner(broker,budget={'max_calls':1,'max_seconds':120})
        planner.deadline=time.monotonic()+120
        record['direct_decomposition'] = await planner.ask(
            'Split this one supplied component into one atomic extract task: extract the declared dough yield from supplied fixture L01. '
            'Use id yield, one supplied source input, no dependencies or blocked inputs, max_input_items 1, max_output_words 30. '
            'Include every contract key. Do not answer the task. Return {"tasks":[...]} directly.',
            'Mimir-Decomposer',field='tasks_json')
    finally:
        await broker.aclose()
        record.update(duration_seconds=round(time.monotonic()-started,3),usage_calls=broker.usage_calls,
                      reported_tokens=sum(c.get('tokens_used') or 0 for c in broker.usage_calls))
        _write_artifact(target/'results.json',json.dumps(record,ensure_ascii=False,indent=2))
        print(json.dumps({'seconds':record['duration_seconds'],'tokens':record['reported_tokens'],
                          'synthesis':record.get('synthesis')}),flush=True)


if __name__ == '__main__':
    asyncio.run(probe(sys.argv[1]))
