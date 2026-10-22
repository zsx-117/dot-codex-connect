"""Open-source foreground connector. Enrollment is explicit via selfhost/configure_mac.py."""
import argparse,hashlib,json,os,plistlib,shutil,ssl,subprocess,sys,time,urllib.request,urllib.error,urllib.parse,webbrowser
from pathlib import Path

VERSION='0.3.1+oss.1'
# Open-source preparation: no hosted default; use the operator-selected origin.
SERVICE=os.environ.get('DOT_CONNECT_SERVICE','https://connect.example.invalid').rstrip('/')
ORIGIN=SERVICE
LABEL='com.dotcodexconnect.connector'

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def configure_tls():
 # Public CA certificates travel with the distribution; verification is retained.
 context=ssl.create_default_context()  # System CA store; certificate verification remains enabled.
 urllib.request.install_opener(urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=context)))

def cloud(path,key=None,data=None):
 headers={'accept':'application/json','User-Agent':'DotCodexConnect/'+VERSION}
 if key:headers['x-bridge-device-key']=key
 if data is not None:headers['content-type']='application/json'
 request=urllib.request.Request(ORIGIN+path,headers=headers,data=json.dumps(data).encode() if data is not None else None,method='POST' if data is not None else 'GET')
 try:
  with urllib.request.urlopen(request,timeout=15) as response:return json.load(response)
 except urllib.error.HTTPError as error:
  try:value=json.loads(error.read(4096));code=value.get('error','setup_request_rejected')
  except Exception:code='setup_request_rejected'
  if not isinstance(code,str) or not code.replace('_','').isalnum():code='setup_request_rejected'
  raise ValueError(code) from None

def identity():
 from transport import AppServer
 from bridge import fingerprint
 app=AppServer(rpc_timeout=6)
 try:
  account=app.call('account/read',{'refreshToken':False}).get('account') or {}
  if account.get('type')!='chatgpt' or not account.get('email'):raise ValueError('sign_in_to_Codex_on_this_Mac_first')
  return {'emailHash':hashlib.sha256(account['email'].strip().lower().encode()).hexdigest(),'fingerprint':fingerprint(app)}
 finally:app.close()

def main():
 global ORIGIN,LABEL
 parser=argparse.ArgumentParser(prog='DotCodexConnect')
 parser.add_argument('action',nargs='?',default='version',choices=['run','health','status','worker','version','self-check'])
 parser.add_argument('value',nargs='?');parser.add_argument('--home');parser.add_argument('--sandbox',action='store_true',help=argparse.SUPPRESS)
 args=parser.parse_args()
 if args.sandbox:os.environ['DOT_CONNECTOR_SANDBOX']='1'
 if os.environ.get('DOT_CONNECTOR_SANDBOX')=='1':
  ORIGIN=SERVICE+'/sandbox';LABEL+='-sandbox'
  if not args.home and not os.environ.get('DOT_CONNECT_HOME'):os.environ['DOT_CONNECT_HOME']=str(Path.home()/'Library/Application Support/DotCodexConnect/Sandbox')
 if args.home:os.environ['DOT_CONNECT_HOME']=str(Path(args.home).expanduser().resolve())
 configure_tls()
 if args.action=='version':print(VERSION);return
 if args.action=='self-check':
  from runtime import child_command
  result=subprocess.run(child_command('version'),capture_output=True,text=True,timeout=10,check=True)
  if result.stdout.strip()!=VERSION:raise ValueError('self_execution_failed')
  compiled=hasattr(sys.modules.get('__main__'),'__compiled__')
  print(json.dumps({'version':VERSION,'selfExecution':True,'tlsVerification':True,'compiled':compiled,'sourceFilesRequired':not compiled}));return
 from bridge import ROOT,health_check,run_job
 if args.action=='run':
  from agent import run
  run()
 elif args.action=='health':print(json.dumps(health_check()))
 elif args.action=='worker':
  path=Path(args.value).resolve()
  if path.parent!=ROOT/'jobs-v2' or path.suffix!='.json':raise ValueError('invalid_owned_job_path')
  run_job(json.loads(path.read_text())['job'])
 else:
  print(json.dumps({'version':VERSION,'configured':(ROOT/'device.json').exists(),'accountVerified':health_check().get('accountVerified',False)}))

if __name__=='__main__':
 try:main()
 except KeyboardInterrupt:print('Stopped waiting. Reopen setup to check the same request.');sys.exit(130)
 except Exception as error:
  from reliability import BridgeFault
  import re
  message=error.safe_message if isinstance(error,BridgeFault) else str(error) if isinstance(error,ValueError) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{1,119}',str(error)) else type(error).__name__
  print('Connection needs attention: '+message,file=sys.stderr);sys.exit(1)
