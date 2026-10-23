"""Frozen source binding retains exact text, provenance and task limits."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source_binding import bind_captured_sources
from source_store import SourceStore
from task_graph import TaskNode
from mimir_config import ConfigurationRequired


def record(name='fixture'):
    text='L01 Yield: four balls.'
    return {'id':name,'locator':'source.txt','retrieved_at':'2026-10-23T00:00:00Z',
            'retrieval_type':'local_file','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}


def test_only_named_source_bound_with_frozen_identity_and_status():
    node=TaskNode('yield','Atomic-Worker','yield','prompt',input_artifacts={
        'task_contract':{'inputs':['fixture: L01'],'max_input_items':1}})
    config={'sources':[record(),record('unrelated')],'source_statuses':{'fixture':'synthetic_fixture'}}
    bind_captured_sources(node,config)
    sources=node.input_artifacts['supplied_sources']
    assert len(sources)==1 and sources[0]['text']==record()['text']
    assert sources[0]['status']=='synthetic_fixture'
    assert sources[0]['retrieved_at']==record()['retrieved_at']
    bind_captured_sources(node,config)
    assert len(sources)==1
    changed=deepcopy(config);changed['source_statuses']['fixture']='retrieved'
    with pytest.raises(ConfigurationRequired,match='conflicts'):
        bind_captured_sources(node,changed)


def test_manifest_accepts_explicit_fixture_status_without_changing_capture_record(tmp_path):
    source=tmp_path/'source.txt';source.write_text('L01 Yield: four balls.',encoding='utf-8')
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'sources':[
        {'id':'fixture','path':'source.txt','status':'synthetic_fixture'}]}),encoding='utf-8')
    store=SourceStore.capture(manifest)
    assert store.records['fixture']['text']==source.read_text()
    assert set(store.records['fixture'])==set(record())


def test_input_limit_and_source_identity_cannot_be_bypassed():
    node=TaskNode('yield','Atomic-Worker','yield','prompt',input_artifacts={
        'task_contract':{'inputs':['fixture and other'],'max_input_items':1}})
    with pytest.raises(ConfigurationRequired,match='input limit'):
        bind_captured_sources(node,{'sources':[record(),record('other')]})
    corrupted=record();corrupted['text']='Changed'
    with pytest.raises(ValueError,match='identity'):
        bind_captured_sources(node,{'sources':[corrupted]})
