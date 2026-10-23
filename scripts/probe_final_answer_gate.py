"""Fresh final checks on qualified fixture synthesis and a blinded corruption."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from random import Random

from backend import create_swarm_backend
from engine import _write_artifact
from post_worker import check_final_answer
from probe_post_worker import CaptureBroker


async def probe(target):
    target=Path(target); target.mkdir(parents=True,exist_ok=False)
    saved=json.loads(Path('.mimir/post-worker-repeated-20261023/results.json').read_text(encoding='utf-8'))
    candidates=[{'origin':'qualified','assembled':deepcopy(saved['synthesis'])},
                {'origin':'unsupported','assembled':deepcopy(saved['synthesis'])}]
    candidates[1]['assembled']['answer']='This is the best authentic Neapolitan dough recipe.\n'+candidates[1]['assembled']['answer']+'\nFinal-proof temperature: 25 C.'
    Random(740274).shuffle(candidates)
    native=create_swarm_backend('codex','gpt-6.1-sol',max_concurrency=1,effort='low',timeout_seconds=180,worker_transport='native')
    broker=CaptureBroker(native,budget={'max_attempts':2,'max_seconds':120},journal=target/'operations.jsonl');broker.target=target
    started=time.monotonic();record={'synthetic_fixture':True,'checks':[]}
    try:
        for candidate in candidates:
            verdict=await check_final_answer(broker,saved['synthesis_context'],candidate['assembled'])
            record['checks'].append({'origin':candidate['origin'],'assembled':candidate['assembled'],'check':verdict})
            print(json.dumps({'origin':candidate['origin'],'check':verdict}),flush=True)
        assert {c['origin']:c['check']['verdict'] for c in record['checks']}=={'qualified':'PASS','unsupported':'FAIL'}
    finally:
        await broker.aclose()
        record.update(seconds=round(time.monotonic()-started,3),usage_calls=broker.usage_calls,
                      tokens=sum(c.get('tokens_used') or 0 for c in broker.usage_calls))
        _write_artifact(target/'results.json',json.dumps(record,ensure_ascii=False,indent=2))
        print(json.dumps({'seconds':record['seconds'],'tokens':record['tokens']}),flush=True)


if __name__=='__main__':
    asyncio.run(probe(sys.argv[1]))
