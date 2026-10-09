import subprocess
import tempfile
import unittest
from pathlib import Path
from instinct_models.training.needle_lora import NeedleLoRAJob,train_needle_lora

def test_planted_registry_link_refuses_before_runner_and_keeps_bytes(tmp_path):
 data=tmp_path/'data';data.write_text('{"query":"q","tools":[],"answers":[]}\n')
 out=tmp_path/'out';out.mkdir();outside=tmp_path/'outside';outside.write_bytes(b'private original\n')
 (out/'registry.jsonl').symlink_to(outside)
 calls=[]
 def runner(cmd,env):
  calls.append(cmd);__import__('pathlib').Path(cmd[-1]).write_bytes(b'fixture');return subprocess.CompletedProcess(cmd,0,'','')
 try:train_needle_lora(NeedleLoRAJob('atlas',str(data),str(out)),runner=runner)
 except ValueError as e:assert 'registry' in str(e)
 else:raise AssertionError('no refusal')
 assert not calls and outside.read_bytes()==b'private original\n'

def test_regular_registry_append_still_works(tmp_path):
 data=tmp_path/'data';data.write_text('{}\n');out=tmp_path/'out'
 def runner(cmd,env):
  __import__('pathlib').Path(cmd[-1]).write_bytes(b'fixture');return subprocess.CompletedProcess(cmd,0,'','')
 result=train_needle_lora(NeedleLoRAJob('atlas',str(data),str(out)),runner=runner)
 assert result['tuned_sha256'] and (out/'registry.jsonl').is_file()

def test_late_registry_fifo_refuses_without_hanging(tmp_path):
 import os,sys
 if not hasattr(os,'mkfifo'):raise unittest.SkipTest('POSIX FIFO only')
 script=r'''
import os,subprocess
from pathlib import Path
from instinct_models.training.needle_lora import NeedleLoRAJob,train_needle_lora
root=Path(__import__('sys').argv[1]);data=root/'data';data.write_text('{}\n');out=root/'out'
def runner(cmd,env):
 Path(cmd[-1]).write_bytes(b'fixture')
 if cmd[1]=='build':os.mkfifo(out/'registry.jsonl')
 return subprocess.CompletedProcess(cmd,0,'','')
try:train_needle_lora(NeedleLoRAJob('atlas',str(data),str(out)),runner=runner)
except (ValueError,OSError):print('refused');raise SystemExit(0)
raise SystemExit(9)
'''
 p=subprocess.run([sys.executable,'-c',script,str(tmp_path)],capture_output=True,text=True,timeout=2)
 assert p.returncode==0 and 'refused' in p.stdout


class RegistryGuardTests(unittest.TestCase):
    def _run(self, fn):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))

    def test_planted_link(self):
        self._run(test_planted_registry_link_refuses_before_runner_and_keeps_bytes)

    def test_regular_append(self):
        self._run(test_regular_registry_append_still_works)

    def test_late_fifo(self):
        self._run(test_late_registry_fifo_refuses_without_hanging)
