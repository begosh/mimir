"""Provenance, coverage and checker boundaries across the worker handoff."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from post_worker import synthesis_context, synthesize, check_results


def test_registry_merges_worker_locators_without_promoting_supplied_source():
    state = {'goal':'Dough recipe', 'task_brief':{'constraints':['Dough only'], 'components':['ingredients','method']},
             'component_coverage':{'ingredients':'NOT RUN'},
             'source_registry':[{'id':'fixture','locator':'fixture','status':'synthetic_fixture'}],
             'completed_data':{f't{i}':{'role':'Atomic-Worker','result':{'answer':'step', 'gaps':[],
                'sources':[{'id':'fixture','locator':f'fixture:L0{i}', 'support_excerpt':f'line {i}'}]}}
                               for i in (1,2)}}
    context = synthesis_context(state)
    assert context['scope'] == ['Dough only']
    assert context['coverage']['components'] == {'ingredients':'NOT RUN','t1':'RETURNED','t2':'RETURNED'}
    assert len(context['sources']) == 1
    assert context['sources'][0]['status'] == 'synthetic_fixture'
    assert context['sources'][0]['locators'] == ['fixture','fixture:L01','fixture:L02']
    state.pop('source_registry')
    assert synthesis_context(state)['sources'][0]['status'] == 'unverified'


def test_conflicting_provenance_stays_unverified():
    state={'source_registry':[{'id':'x','status':'synthetic_fixture'}, {'id':'x','status':'retrieved'}]}
    assert synthesis_context(state)['sources'][0]['status']=='unverified'


def test_checker_rejects_duplicate_ids_and_uses_direct_schema():
    class Fake:
        default_model='agreed'; default_effort='low'
        async def spawn_restricted(self, **options):
            assert options['json_schema']['required'] == ['checks']
            assert 'answer together with gaps' in options['prompt']
            data={'checks':[{'id':'a','verdict':'PASS','issues':[]}]*2}
            return SimpleNamespace(status='SUCCESS',data=data,raw_response=json.dumps(data))
    with pytest.raises(ValueError,match='duplicated'):
        asyncio.run(check_results(Fake(),{'candidates':[{'id':'a'},{'id':'b'}]}))


def test_synthesizer_passes_scope_and_does_not_substitute_untrusted_placeholders():
    class Fake:
        default_model='agreed'; default_effort='low'
        async def spawn_restricted(self, **options):
            assert options['role']=='Mimir-Synthesizer'
            assert options['json_schema']['required']==['answer','limitations']
            assert 'GEPA' not in options['prompt']
            assert '{{scope}}' in options['prompt']  # injected source value remains data
            return SimpleNamespace(status='SUCCESS',data={'answer':'Supported step','limitations':['Synthetic fixture']})
    context=synthesis_context({'goal':'{{scope}}','scope_rules':['Dough only']})
    result,_=asyncio.run(synthesize(Fake(),context))
    assert result['limitations']==['Synthetic fixture']
