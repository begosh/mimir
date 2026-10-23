"""Live phased engine run with explicit fixture binding after plan review."""
import asyncio
import json
from pathlib import Path
import sys
import time

from backend import create_swarm_backend
from engine import run_mimir, _save_state, _write_artifact
from task_graph import TaskGraph


async def probe(target, use_manifest=False):
    target=Path(target)
    resume_plan=use_manifest and (target/'checkpoint.json').is_file()
    target.mkdir(parents=True,exist_ok=resume_plan)
    source=Path('tests/fixtures/pizza_extraction_source.txt').read_text(encoding='utf-8')
    counter=len(json.loads((target/'checkpoint.json').read_text(encoding='utf-8')).get('usage_calls', [])) if resume_plan else 0
    def factory(**settings):
        native=create_swarm_backend(**settings)
        original=native.spawn_restricted
        async def capture(prompt,role='Worker',**options):
            nonlocal counter
            counter+=1;n=counter
            _write_artifact(target/f'prompt-{n}.txt',prompt)
            _write_artifact(target/f'schema-{n}.json',json.dumps(options.get('json_schema'),indent=2))
            result=await original(prompt=prompt,role=role,**options)
            _write_artifact(target/f'response-{n}.txt',result.raw_response)
            return result
        native.spawn_restricted=capture
        return native
    events=[]
    def event(item):
        events.append(item)
        print(json.dumps(item,ensure_ascii=True),flush=True)
    options={'backend':'codex','model':'gpt-6.1-sol','effort':'low','worker_transport':'native',
             'mode':'swarm','max_tasks':6,'max_depth':3,'max_concurrency':2,'memory_mode':'off',
             'state_file':str(target/'checkpoint.json'),'output_path':str(target/'report.md'),
             'progress_format':'events','event_sink':event,'worker_factory':factory}
    goal=('Give me the best napoli pizza dough recipe. For this explicit pipeline test, use only '
          'the supplied synthetic fixture fixture:pizza_extraction_source. It is not an authentic or recommended recipe. '
          'Extract its declared yield, dough ingredient quantities, and ordered dough preparation including fermentation '
          'and shaping. No target quantity or scaling. Dough only: no toppings, sauce or baking. '
          'Do not search, retrieve or ask for choices; qualify best as unestablished. '
          'The source is supplied below and will also be bound to every worker. Keep tasks extract-only and stupid easy.\n'
          'SUPPLIED SYNTHETIC SOURCE fixture:pizza_extraction_source:\n'+source)
    if use_manifest:
        manifest=target/'sources.json'
        _write_artifact(manifest,json.dumps({'sources':[{'id':'fixture:pizza_extraction_source',
            'path':str(Path('tests/fixtures/pizza_extraction_source.txt').resolve()),'status':'synthetic_fixture'}]}))
        options['source_manifest']=str(manifest)
        goal=goal.split('The source is supplied below')[0]+'Use the captured source manifest. Its exact source ID is fixture:pizza_extraction_source.'
    started=time.monotonic();record={}
    try:
        state=json.loads((target/'checkpoint.json').read_text(encoding='utf-8')) if resume_plan else await run_mimir(goal=goal,phase='plan',recursive_plan=True,**options)
        graph=TaskGraph.from_dict(state['graph'])
        if any(n.input_artifacts['task_contract']['operation'] not in {'extract', 'check'} for n in graph.nodes.values()):
            raise ValueError('Fixture plan requires operations beyond supplied-source extraction; inspect before execution')
        for node in ([] if use_manifest else graph.nodes.values()):
            node.input_artifacts['supplied_sources']=[{'id':'fixture:pizza_extraction_source',
                'locator':'fixture:pizza_extraction_source','status':'synthetic_fixture','retrieval_type':'local_file',
                'retrieved_at':'','text':source}]
        state['graph']=graph.to_dict()
        state['source_registry']=[{'id':'fixture:pizza_extraction_source','locator':'fixture:pizza_extraction_source',
                                  'status':'synthetic_fixture'}]
        state['scope_rules']=['Dough only. No toppings, sauce or baking. Supplied synthetic fixture only.']
        if not use_manifest:
            _save_state(state,options['state_file'])
        # Explicit test binding, not a claim that automatic retrieval-page handoff exists.
        await run_mimir(phase='execute',**options)
        final=await run_mimir(phase='synthesize',**options)
        record={'phase':final['phase'],'report':final['report_path'],'calls':len(final['usage_calls']),
                'tokens':sum(c.get('tokens_used') or 0 for c in final['usage_calls']),
                'final_check':final['final_answer_check'],'synthesis':final['synthesis_result']}
    finally:
        record.update(seconds=round(time.monotonic()-started,3),events=events)
        _write_artifact(target/'probe.json',json.dumps(record,ensure_ascii=False,indent=2))
        print(json.dumps({k:v for k,v in record.items() if k!='events'},ensure_ascii=True),flush=True)


if __name__=='__main__':
    asyncio.run(probe(sys.argv[1],use_manifest='--manifest' in sys.argv[2:]))
