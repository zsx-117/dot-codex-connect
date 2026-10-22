#!/usr/bin/env python3
"""Run original synthetic tests on a disposable source copy, with no network."""
import os, shutil, sys, tempfile, unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def main():
    with tempfile.TemporaryDirectory(prefix='dot-oss-tests-') as tmp:
        stage=Path(tmp).resolve()
        for folder in ['device','tests']:
            shutil.copytree(root/'service'/('connector/src' if folder=='device' else folder),stage/folder,ignore=shutil.ignore_patterns('__pycache__','jobs-v2'))
        os.environ['CODEX_HOME']=str(stage/'fake-codex-home')
        os.environ['DOT_CONNECT_HOME']=str(stage/'fake-connector-home')
        def guard(event,args):
            if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo'):
                raise RuntimeError('Network is forbidden in synthetic tests')
            if event=='subprocess.Popen':
                executable=Path(str(args[0])).resolve()
                if 'codex' in executable.name.lower() and not executable.is_relative_to(Path(tempfile.gettempdir()).resolve()):
                    raise RuntimeError('Real Codex process is forbidden in synthetic tests')
            if event=='open' and isinstance(args[0],(str,bytes)):
                p=Path(os.fsdecode(args[0]))
                if '.codex' in p.parts or p.name in ('auth.json','auth.toml'):
                    raise RuntimeError('Private account/session files are forbidden in synthetic tests')
        sys.addaudithook(guard)
        sys.path.insert(0,str(stage/'device'))
        suite=unittest.defaultTestLoader.discover(str(stage/'tests'),pattern='test_*.py')
        result=unittest.TextTestRunner(verbosity=1).run(suite)
        success=result.wasSuccessful()
    sys.exit(0 if success else 1)

if __name__=='__main__':main()
