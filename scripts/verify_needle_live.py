"""Explicit live smoke, not part of the offline suite. Anonymous pinned HF downloads."""
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['NEEDLE_TELEMETRY']='0';os.environ['DO_NOT_TRACK']='1'
from huggingface_hub import HfApi, hf_hub_download
from needle.agent import fetch
from instinct_models import Router, Task
from instinct_models.providers import NeedleLocal
REV='27c0a9a5b3ca835e0b7dbeaccf555df03dac493d'
REPO='Cactus-Compute/needle3'
info=HfApi().model_info(REPO,revision=REV,files_metadata=True)
assert info.sha==REV
engine='python/cactus_needle-3.0.2-py3-none-manylinux2014_x86_64.whl'
files={f.rfilename:f for f in info.siblings}
assert engine in files
cache=Path(fetch.cache_dir(3));cache.mkdir(parents=True,exist_ok=True)
for name in (engine,'needle3.cact'):
    src=Path(hf_hub_download(REPO,name,revision=REV))
    digest=hashlib.sha256(src.read_bytes()).hexdigest()
    assert digest==files[name].lfs.sha256
    print(json.dumps({'file':name,'revision':REV,'bytes':src.stat().st_size,'sha256':digest}),flush=True)
    if name==engine:
        with zipfile.ZipFile(src) as z: (cache/'libneedle.so').write_bytes(z.read('needle/libneedle3.so'))
    else: (cache/'needle3.cact').write_bytes(src.read_bytes())
# Prohibit silent fallback in acceptance: provider uses actual Needle class with generation=3.
import needle
p=NeedleLocal(factory=lambda **kw: needle.Needle(generation=3,**kw))
tools=[{'name':'get_weather','description':'Get the current weather in a city','parameters':{'type':'object','properties':{'city':{'type':'string'}},'required':['city']}}]
print('ENV:',sys.version.split()[0],platform.platform(),'cactus-needle',importlib.metadata.version('cactus-needle'),'engine',fetch.ENGINE_VERSIONS[3],flush=True)
start=time.monotonic()
result=p.chat([{'role':'user','content':"what's the weather in Lagos right now?"}],tools=tools)
print('REAL TOOL CALL:',json.dumps({'provider':result.provider,'model':result.model,'tool_calls':result.tool_calls,'confidence':result.raw.get('confidence'),'elapsed_s':round(time.monotonic()-start,3)}),flush=True)
assert result.tool_calls==[{'name':'get_weather','arguments':{'city':'Lagos'}}]
out=Router([p]).run(Task([{'role':'user','content':'Hello, how are you?'}],tools=tools,private=True))
print('REAL NO-CALL:',json.dumps({'ok':out.ok,'attempts':[[a.provider,a.outcome,a.detail] for a in out.attempts]}),flush=True)
assert not out.ok and out.attempts[-1].outcome=='escalated'
# Also prove default production factory loads the same engine rather than the acceptance factory only.
r=Router([NeedleLocal()]).run(Task([{'role':'user','content':"what's the weather in Lagos right now?"}],tools=tools,private=True))
assert r.ok and r.result.tool_calls==result.tool_calls
print('DEFAULT PRODUCTION ROUTER:',json.dumps({'ok':r.ok,'tool_calls':r.result.tool_calls,'engine':fetch.ENGINE_VERSIONS[3]}),flush=True)
