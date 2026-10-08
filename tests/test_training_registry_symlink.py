import subprocess
import pytest
from instinct_models.training.needle_lora import NeedleLoRAJob,train_needle_lora

def test_planted_registry_link_refuses_before_runner_and_keeps_bytes(tmp_path):
 data=tmp_path/'data';data.write_text('{"query":"q","tools":[],"answers":[]}\n')
 out=tmp_path/'out';out.mkdir();outside=tmp_path/'outside';outside.write_bytes(b'private original\n')
 (out/'registry.jsonl').symlink_to(outside)
 calls=[]
 def runner(cmd,env):
  calls.append(cmd);__import__('pathlib').Path(cmd[-1]).write_bytes(b'fixture');return subprocess.CompletedProcess(cmd,0,'','')
 with pytest.raises(ValueError,match='registry'):train_needle_lora(NeedleLoRAJob('atlas',str(data),str(out)),runner=runner)
 assert not calls and outside.read_bytes()==b'private original\n'

def test_regular_registry_append_still_works(tmp_path):
 data=tmp_path/'data';data.write_text('{}\n');out=tmp_path/'out'
 def runner(cmd,env):
  __import__('pathlib').Path(cmd[-1]).write_bytes(b'fixture');return subprocess.CompletedProcess(cmd,0,'','')
 result=train_needle_lora(NeedleLoRAJob('atlas',str(data),str(out)),runner=runner)
 assert result['tuned_sha256'] and (out/'registry.jsonl').is_file()
