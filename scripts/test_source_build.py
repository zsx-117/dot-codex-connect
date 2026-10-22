#!/usr/bin/env python3
"""Build twice, compare, unpack to temporary state, and exercise source self-execution."""
import importlib.util,json,os,subprocess,sys,tempfile,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_source',root/'scripts/build-source.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='dot-source-build-') as tmp:
    folder=Path(tmp)
    first=module.build(folder/'first.zip');second=module.build(folder/'second.zip');assert first==second
    with zipfile.ZipFile(folder/'first.zip') as z:z.extractall(folder/'extracted')
    connector=folder/'extracted/dot-codex-connector-source/connector.py'
    env={k:v for k,v in os.environ.items() if not k.startswith(('DOT_','CODEX_'))}
    env.update(DOT_CONNECT_HOME=str(folder/'isolated-state'),CODEX_HOME=str(folder/'fake-codex'))
    result=subprocess.run([sys.executable,str(connector),'self-check'],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,'Source self-check failed; no account access was attempted'
    status=json.loads(result.stdout);assert status['selfExecution'] and status['tlsVerification'] and not status['compiled']
    assert not (folder/'fake-codex').exists()
    assert not list((folder/'isolated-state').glob('*.json'))
    print('PASS deterministic source archive and extracted connector self-execution; no credentials, account reads or daemon')
