#!/usr/bin/env python3
"""Explicit source-mode enrollment. Never generates a key or installs a daemon."""
import argparse, json, os, sys, urllib.parse
from pathlib import Path

def validate(origin,key,home):
    u=urllib.parse.urlsplit(origin)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
        raise ValueError('Use your own HTTPS origin without path, credentials or query')
    if u.hostname.endswith('.invalid'):
        raise ValueError('Replace the example origin before enrollment')
    if not key or len(key)<32 or any(word in key.lower() for word in ('replace','changeme','fixture','example')):
        raise ValueError('Supply an operator-managed device key; none is generated here')
    if not home.is_absolute():raise ValueError('Use an explicit absolute connector state directory')
    if home.exists() and any(home.iterdir()):raise ValueError('Refuse to overwrite existing connector state')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',required=True)
    parser.add_argument('--approve-account-binding',action='store_true',help='Allow account/read to pin this local signed-in account; no chat reads or task sends')
    args=parser.parse_args()
    if not args.approve_account_binding:parser.error('Explicit account-binding approval is required')
    home=Path(args.home).expanduser()
    origin=os.environ.get('DOT_CONNECT_SERVICE','').rstrip('/')
    key=os.environ.get('DOT_DEVICE_TOKEN','')
    validate(origin,key,home)
    os.umask(0o077)
    os.environ['DOT_CONNECT_HOME']=str(home)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'service/connector/src'))
    from connector import identity,configure_tls,cloud
    configure_tls()
    current=identity()  # Reads account identity through public AppServer; never auth files.
    # Verify device credential against the chosen host before persisting local binding.
    cloud('/agent',key,{'op':'heartbeat'})
    from bridge import save
    save(home/'account-binding.json',{'fingerprint':current['fingerprint']})
    save(home/'device.json',{'url':origin,'deviceKey':key,'deviceId':'mac','version':'selfhost-source-1'})
    print('Account binding and source-mode configuration saved; no background service started.')

if __name__=='__main__':
    try:main()
    except Exception:
        print('Enrollment did not complete. Check the origin, account and local state; no credential values are printed.',file=sys.stderr)
        sys.exit(1)
