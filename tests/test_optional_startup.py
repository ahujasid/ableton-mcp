import subprocess
import sys
from pathlib import Path


def test_core_import_does_not_require_scientific_extras():
    root=str(Path(__file__).resolve().parents[1])
    code='''
import sys, importlib.abc
sys.path.insert(0, ROOT)
class NoExtras(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split('.')[0] in ('numpy','scipy','soundfile'):
            raise ImportError('optional extra intentionally absent')
sys.meta_path.insert(0, NoExtras())
import MCP_Server.server
print('core import OK')
'''.replace('ROOT',repr(root))
    result=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert 'core import OK' in result.stdout
