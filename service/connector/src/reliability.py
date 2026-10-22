"""Bounded recovery policy. Never logs exception text or changes account access."""
import datetime,errno,json,queue,socket,ssl,time,urllib.error

VERSION='0.3.1+oss.1'
MAX_UNSENT_RETRIES=5
HEALTH_PROBE_SECONDS=20
HEALTH_RPC_SECONDS=6
HEALTH_FRESH_SECONDS=75

class BridgeFault(ValueError):
 def __init__(self,code,message,retryable=False,user_action=False):
  self.code=code;self.safe_message=message;self.retryable=retryable;self.user_action=user_action
  super().__init__(message)

def error_info(exc,layer='app_server'):
 """Only fixed classifications and numeric protocol codes can leave this process."""
 if isinstance(exc,BridgeFault):
  return {'code':exc.code,'message':exc.safe_message,'retryable':exc.retryable,'requiresUserAction':exc.user_action,'errorClass':type(exc).__name__,'layer':layer}
 code='UNCLASSIFIED_ERROR';message='Operation failed; no automatic resend.';retryable=False;user_action=False;extra={}
 if isinstance(exc,urllib.error.HTTPError):
  extra['httpStatus']=exc.code
  if exc.code in (401,403):code='SERVICE_AUTH_REJECTED';message='Existing service authorization was rejected; explicit authorization repair required.';user_action=True
  elif exc.code==429 or 500<=exc.code<600:code='SERVICE_TEMPORARILY_UNAVAILABLE';message='Existing service is temporarily unavailable.';retryable=True
  else:code='SERVICE_REQUEST_REJECTED';message='Existing service rejected the request.'
 elif isinstance(exc,urllib.error.URLError):
  return error_info(exc.reason if isinstance(exc.reason,BaseException) else OSError(),layer='cloud_transport')
 elif isinstance(exc,socket.gaierror):code='DNS_RESOLUTION_FAILED';message='DNS resolution failed.';retryable=True
 elif isinstance(exc,ssl.SSLCertVerificationError):code='TLS_VERIFICATION_FAILED';message='TLS verification failed; verification remains enforced.';user_action=True
 elif isinstance(exc,(TimeoutError,queue.Empty)):
  code='CLOUD_TIMEOUT' if layer=='cloud_transport' else 'APP_SERVER_TIMEOUT';message='Operation did not return before its bounded timeout.';retryable=True
 elif type(exc).__name__=='Disconnected' or isinstance(exc,(BrokenPipeError,ConnectionError)):
  code='CLOUD_DISCONNECTED' if layer=='cloud_transport' else 'APP_SERVER_DISCONNECTED';message='The existing transport disconnected.';retryable=True
 elif isinstance(exc,PermissionError) or isinstance(exc,OSError) and exc.errno in (errno.EPERM,errno.EACCES):
  code='FILESYSTEM_ACCESS_DENIED';message='Existing filesystem access was denied; user action is required.';user_action=True
 elif isinstance(exc,FileNotFoundError):code='REQUIRED_LOCAL_FILE_MISSING';message='A required local file is missing; configuration was not recreated.';user_action=True
 elif hasattr(exc,'error') and isinstance(exc.error,dict):
  rpc=exc.error;extra['rpcCode']=rpc.get('code') if isinstance(rpc.get('code'),int) else None
  # Inspect solely to classify. Never copy the response message into diagnostics.
  text=str(rpc.get('message','')).lower()
  if 'active writer' in text:code='WRITER_BUSY';message='The existing writer remains in control.';retryable=True
  elif any(x in text for x in ['unauthorized','authentication','login required','token expired']):code='APP_SERVER_AUTH_REJECTED';message='App Server account authorization was rejected.';user_action=True
  else:code='APP_SERVER_RPC_REJECTED';message='App Server explicitly rejected the operation.'
 elif isinstance(exc,OSError) and layer=='cloud_transport':code='CLOUD_TRANSPORT_ERROR';message='The existing network transport failed.';retryable=True
 return {'code':code,'message':message,'retryable':retryable,'requiresUserAction':user_action,'errorClass':type(exc).__name__,'layer':layer,**extra}

def retry_delay(attempt,base=3,cap=60):
 return min(cap,base*2**min(12,max(0,int(attempt)-1)))

def may_retry_unsent(record,info):
 return bool(info.get('retryable') and not record.get('startIntent') and not record.get('targetReceived') and not record.get('turnId') and record.get('retryAttempts',0)<MAX_UNSENT_RETRIES)

def delivery_authorized(health,now):
 age=now*1000-health.get('checkedAt',0)
 return health.get('accountVerified') is True and -1000<=age<=HEALTH_FRESH_SECONDS*1000

def log(event,**fields):
 # Callers supply classifications/counters only, never prompts, URLs or raw errors.
 print(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'event':event,**fields},ensure_ascii=False),flush=True)

def health_probe(root,executable,runner=None):
 """A disposable read-only probe; timeout kills only this probe, never a worker."""
 import subprocess
 runner=runner or subprocess.run
 started=time.monotonic()
 try:
  from runtime import child_command
  result=runner(child_command('health'),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=HEALTH_PROBE_SECONDS,start_new_session=True)
  if result.returncode!=0:raise BridgeFault('HEALTH_PROBE_FAILED','The isolated health probe did not finish successfully.',retryable=True)
  health=json.loads(result.stdout)
  if not isinstance(health,dict) or type(health.get('accountVerified')) is not bool:raise ValueError()
 except subprocess.TimeoutExpired:
  health={'accountVerified':False,**error_info(BridgeFault('HEALTH_PROBE_TIMEOUT','The isolated local health probe timed out before verified account health could be obtained.',retryable=True),layer='local_health')}
 except (ValueError,TypeError):
  health={'accountVerified':False,**error_info(BridgeFault('HEALTH_PROBE_INVALID_RESPONSE','The health probe returned an invalid response.',retryable=True))}
 except Exception as exc:
  health={'accountVerified':False,**error_info(exc)}
 return {**health,'version':VERSION,'checkedAt':int(time.time()*1000),'probeDurationMs':int((time.monotonic()-started)*1000),'deliveryPaused':not health['accountVerified']}
