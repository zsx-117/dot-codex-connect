#!/usr/bin/env python3
"""Build a deterministic, inspectable Python connector source archive, not a signed App."""
import argparse,hashlib,json,zipfile
from pathlib import Path

def build(output):
    root=Path(__file__).resolve().parents[1]
    files={p.name:p.read_bytes() for p in sorted((root/'service/connector/src').glob('*.py'))}
    files['SOURCE-LICENSE.txt']=(root/'LICENSE').read_bytes()
    files['RUN.txt']=b'Python 3.12+ required. Run: python3 connector.py version\nFor isolated source self-check: DOT_CONNECT_HOME=<private-empty-directory> python3 connector.py self-check\nThis is source, not a signed/notarized macOS App. See the full repository self-hosting documentation for explicit enrollment.\n'
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    files['SHA256.json']=(json.dumps(hashes,sort_keys=True,indent=2)+'\n').encode()
    output=Path(output)
    if output.exists():raise ValueError('Refuse to overwrite an existing artifact')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo('dot-codex-connector-source/'+name,date_time=(2026,1,1,0,0,0));info.external_attr=0o100644<<16
            z.writestr(info,data)
    return hashlib.sha256(output.read_bytes()).hexdigest()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    print(build(parser.parse_args().output))
