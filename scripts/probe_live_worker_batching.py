"""Fresh execution and final assembly of a fixed previously reviewed fixture plan."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

from backend import create_swarm_backend
from engine import run_mimir, _save_state, _write_artifact
from research_program import prepare_research
from task_graph import TaskGraph, TaskStatus


async def probe(target, transport='native'):
    target=Path(target);target.mkdir(parents=True,exist_ok=False)
    baseline=json.loads(Path('.mimir/pizza-source-handoff-live-20261023-text/checkpoint.json').read_text(encoding='utf-8'))
    graph=TaskGraph.from_dict(baseline['graph'])
    for node in graph.nodes.values():
        node.status=TaskStatus.PENDING;node.output_data=None;node.result_attempts=[];node.retry_count=0
        node.rejected_output=None;node.error_trace=None;node.duration_seconds=0;node.output_deltas=[]
        node.input_artifacts.pop('result_gate',None);node.input_artifacts.pop('result_repair',None)
        node.input_artifacts.pop('supplied_sources',None)
    state={k:deepcopy(baseline[k]) for k in ('version','goal','backend','model','effort','worker_timeout',
        'worker_transport','max_concurrency','mode','max_tasks','max_depth','task_brief','task_brief_origin',
        'planning_trace','planning_budget','recursive_plan','max_context_chars','intel_brief','intel_context') if k in baseline}
    manifest=target/'sources.json'
    _write_artifact(manifest,json.dumps({'sources':[{'id':'fixture:pizza_extraction_source',
        'path':str(Path('tests/fixtures/pizza_extraction_source.txt').resolve()),'status':'synthetic_fixture'}]}))
    config,_,identity=prepare_research('native',None,str(manifest),None,{},target)
    # A new evaluation run, not a recovery of the old runtime's completed results.
    state.update(phase='planned',graph=graph.to_dict(),completed_data={},usage_calls=[],
        plan_duration_seconds=0,output_path=str(target/'report.md'),memory_mode='off',
        research_program='native',research_config=config,research_identity=identity,
        reused_plan_source='.mimir/pizza-source-handoff-live-20261023-text/checkpoint.json')
    state['worker_transport']=transport
    _save_state(state,str(target/'checkpoint.json'))
    counter=0
    def factory(**options):
        native=create_swarm_backend(**options);original=native.spawn_restricted
        async def capture(prompt,role='Worker',**settings):
            nonlocal counter
            counter+=1;n=counter
            _write_artifact(target/f'prompt-{n}.txt',prompt)
            _write_artifact(target/f'schema-{n}.json',json.dumps(settings.get('json_schema'),indent=2))
            response=await original(prompt=prompt,role=role,**settings)
            _write_artifact(target/f'response-{n}.txt',response.raw_response)
            return response
        native.spawn_restricted=capture
        return native
    options={'state_file':str(target/'checkpoint.json'),'backend':'codex','model':'gpt-6.1-sol',
        'effort':'low','worker_transport':transport,'memory_mode':'off','worker_factory':factory,
        'progress_format':'events','event_sink':lambda e:print(json.dumps(e,ensure_ascii=True),flush=True)}
    started=time.monotonic();record={}
    try:
        await run_mimir(phase='execute',**options)
        final=await run_mimir(phase='synthesize',**options)
        record.update(calls=len(final['usage_calls']),tokens=sum(c.get('tokens_used') or 0 for c in final['usage_calls']),
            execute_seconds=final['execute_duration_seconds'],synthesis_seconds=final['synthesis_duration_seconds'],
            final_check=final['final_answer_check'],synthesis=final['synthesis_result'],
            baseline_execute_seconds=baseline['execute_duration_seconds'],
            baseline_synthesis_seconds=baseline['synthesis_duration_seconds'])
    finally:
        record['seconds']=round(time.monotonic()-started,3)
        _write_artifact(target/'probe.json',json.dumps(record,ensure_ascii=False,indent=2))
        print(json.dumps(record,ensure_ascii=True),flush=True)


if __name__=='__main__':
    asyncio.run(probe(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'native'))
