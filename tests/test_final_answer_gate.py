"""Final checker failure prevents artifact publication and learning."""
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import engine
from backend import SwarmResult, WorkerFailure
from post_worker import check_final_answer
from test_engine_policy import FixtureBackend


@pytest.mark.parametrize('malformed',[False,True])
def test_failed_or_invalid_final_check_cannot_publish(tmp_path,malformed):
    class Worker(FixtureBackend):
        async def spawn(self,prompt,role='Worker',**options):
            if role=='Mimir-Final-Checker':
                self.calls.append({'role':role,'prompt':prompt})
                value={} if malformed else {'verdict':'FAIL','issues':['Unsupported recommendation']}
                return SwarmResult(role,'SUCCESS',value,json.dumps(value))
            return await super().spawn(prompt,role,**options)
    async def run():
        path=tmp_path/'state.json'; report=tmp_path/'report.md'
        options={'backend':'codex','model':'fixture','effort':'low','mode':'review',
                 'state_file':str(path),'output_path':str(report),'worker_factory':lambda **kw:Worker(),
                 'memory_mode':'off','progress_format':'events'}
        with patch.object(engine.JarvisMemory, 'record_learning') as learning:
            with pytest.raises(Exception):
                await engine.run_mimir(goal='Review evidence',**options)
            learning.assert_not_called()
        state=json.loads(path.read_text(encoding='utf-8'))
        assert state['rejected_synthesis']['result']['answer']
        assert state['phase']!='synthesized'
        assert not report.exists() and not report.with_suffix('.json').exists()
    asyncio.run(run())


def test_contradictory_pass_is_rejected():
    class Worker:
        default_model='agreed';default_effort='low'
        async def spawn(self,**options):
            return SwarmResult('Mimir-Final-Checker','SUCCESS',{'verdict':'PASS','issues':['Missing value']},'raw')
    with pytest.raises(ValueError,match='contradictory'):
        asyncio.run(check_final_answer(Worker(),{}, {'answer':'test','limitations':[]}))
