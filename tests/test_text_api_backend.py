import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from backend import SwarmResult, create_swarm_backend
from text_api_backend import TextResponsesBackend, HybridSwarmBackend


SCHEMA = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}


class Response:
    status_code = 200
    def __init__(self, data): self.data=data
    def json(self): return self.data


class Client:
    def __init__(self, data): self.data=data; self.calls=[]
    async def post(self, url, **kwargs):
        self.calls.append((url,kwargs))
        return Response(self.data)


def body(text='{"ok":true}', status='completed'):
    return {'model':'gpt-6.1-sol','status':status,'output':[{'type':'message','content':[{'type':'output_text','text':text}]}],
            'usage':{'input_tokens':40,'output_tokens':10,'total_tokens':50,'input_tokens_details':{'cached_tokens':20}}}


def test_minimal_request_preserves_effort_schema_and_usage_without_tools_or_history():
    client=Client(body())
    backend=TextResponsesBackend('gpt-6.1-sol',provider='azure',endpoint='https://example.test/openai/v1',api_key='private',client=client)
    result=asyncio.run(backend.spawn_restricted('task',json_schema=SCHEMA))
    assert result.status=='SUCCESS' and result.tokens_used==50
    assert result.usage_details['cached_input_tokens']==20
    url,settings=client.calls[0]
    assert url=='https://example.test/openai/v1/responses'
    payload=settings['json']
    assert payload['reasoning']=={'effort':'low'} and payload['tools']==[] and payload['store'] is False
    assert payload['text']['format']['schema']==SCHEMA
    assert len(payload['input'])==1 and 'previous_response_id' not in payload


def test_invalid_or_incomplete_outputs_retain_known_usage_without_retry():
    for value in (body('{"ok":"incorrect"}'),body(status='incomplete')):
        client=Client(value)
        backend=TextResponsesBackend('gpt-6.1-sol',provider='openai',api_key='private',client=client)
        result=asyncio.run(backend.spawn_restricted('task',json_schema=SCHEMA))
        assert result.status=='ERROR' and result.tokens_used==50 and len(client.calls)==1
        assert 'private' not in result.raw_response


def test_hybrid_routes_tools_and_text_separately_and_closes_both():
    class Route:
        default_model='gpt-6.1-sol';default_effort='low';max_concurrency=2;execution_identity={}
        def __init__(self): self.calls=[];self.closed=False
        async def spawn(self,*args,**options):self.calls.append('tools');return SwarmResult('a','SUCCESS',{},'{}')
        async def spawn_restricted(self,*args,**options):self.calls.append('text');return SwarmResult('a','SUCCESS',{},'{}')
        async def aclose(self):self.closed=True
    tool,text=Route(),Route();backend=HybridSwarmBackend(tool,text)
    async def run():
        await backend.spawn('retrieve')
        await backend.spawn_restricted('extract')
        await backend.aclose()
    asyncio.run(run())
    assert tool.calls==['tools'] and text.calls==['text'] and tool.closed and text.closed


def test_cancellation_propagates_without_retry_and_releases_call_capacity():
    class Waiting(Client):
        async def post(self,*args,**kwargs):
            await asyncio.Event().wait()
    backend=TextResponsesBackend('gpt-6.1-sol',provider='openai',api_key='private',client=Waiting(body()),max_concurrency=1)
    async def run():
        task=asyncio.create_task(backend.spawn_restricted('task',json_schema=SCHEMA))
        await asyncio.sleep(0)
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
        else: raise AssertionError('Cancellation was swallowed')
        assert not backend.semaphore.locked()
    asyncio.run(run())


def test_default_text_route_never_initializes_tool_runtime():
    # Model access is distinct from tool runtime model aliases.
    for tool in ('codex','agy','claude','opencode'):
        text=TextResponsesBackend('gpt-6.1-sol',provider='openai',api_key='private',client=Client(body()))
        with patch('text_api_backend.TextResponsesBackend',return_value=text), patch('diagnostics.native_environment',return_value=({'provider':'test','config_paths':[]},{})):
            backend=create_swarm_backend(tool,'gpt-6.1-sol',effort='low')
        assert backend.transport=='hybrid' and backend.tool_backend is None
        result=asyncio.run(backend.spawn_restricted('task',json_schema=SCHEMA))
        assert result.status=='SUCCESS' and backend.tool_backend is None
        asyncio.run(backend.aclose())


def test_missing_direct_credentials_does_not_fall_back_to_native():
    from mimir_config import ConfigurationRequired
    with patch('text_api_backend.configured_value',return_value=None):
        try:create_swarm_backend('codex','gpt-6.1-sol')
        except ConfigurationRequired as exc:assert 'OPENAI_API_KEY' in str(exc)
        else:raise AssertionError('Missing API credentials were silently ignored')


def test_opencode_provider_namespace_keeps_the_api_model_and_effort():
    text=TextResponsesBackend('gpt-6.1-sol',provider='openai',api_key='private',client=Client(body()))
    class Tools:
        timeout_seconds=180
        async def check_cli(self):pass
        async def spawn(self,*args,**options):
            assert options['model']=='azure/gpt-6.1-sol' and options['effort']=='low'
            return SwarmResult('file','SUCCESS',{'ok':True},'{"ok":true}')
        async def aclose(self):pass
    backend=HybridSwarmBackend(None,text,tool_factory=Tools,tool_backend_name='opencode',tool_model='azure/gpt-6.1-sol')
    asyncio.run(backend.spawn('read',model='gpt-6.1-sol',effort='low'))
    asyncio.run(backend.aclose())
