#!/usr/bin/env python3
"""Outbound worker. Durable subprocess jobs outlive supervisor/network interruptions."""
import concurrent.futures,fcntl,json,os,subprocess,sys,time,urllib.request
from bridge import ROOT,JOURNAL,save,STATES_TERMINAL
from reliability import VERSION,health_probe,error_info,retry_delay,delivery_authorized,log
from webhooks import send
from runtime import child_command
CONFIG=ROOT/'device.json'
def rpc(config,data):
 headers={'Content-Type':'application/json','User-Agent':'DotCodexConnect/'+VERSION,'x-bridge-device-key':config['deviceKey']}
 req=urllib.request.Request(config['url']+'/agent',data=json.dumps(data,ensure_ascii=False).encode(),method='POST',headers=headers)
 with urllib.request.urlopen(req,timeout=25) as response:return json.load(response)
def locked(path):
 with open(str(path)+'.lock','a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);return False
  except BlockingIOError:return True

def launch(record,path):
 # Own child execution is deliberately not killed when this supervisor restarts.
 return subprocess.Popen(child_command('worker',str(path)),cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

def sync_batch(records,config,synced,max_records=6,time_budget=8):
 """Bound replay work so old journals cannot starve the existing heartbeat."""
 started=time.monotonic();count=0
 # After reconnect, replay must not put freshly completed replies behind the
 # entire old journal backlog. Unchanged records still fill the spare batch.
 for path,record in sorted(records,key=lambda pair:pair[1].get('updated',pair[1].get('created',0)),reverse=True):
  if count>=max_records or time.monotonic()-started>=time_budget:break
  if record.get('revision',0)<=synced.get(record['id'],-1) or record.get('state') in ('claimed',None):continue
  rpc(config,{'op':'sync','record':record})
  synced[record['id']]=record['revision'];count+=1
 return count

def run_locked():
 config=json.loads(CONFIG.read_text());synced={};last_recovery=0;reconciled={};health={'accountVerified':False,'code':'STARTING','deliveryPaused':True,'version':VERSION};callback=None
 probe=None;next_probe=0;probe_failures=0;cloud_failures=0;launching={};last_tick=time.time();last_health_code=None
 log('supervisor_started',version=VERSION,pid=os.getpid())
 # Health and webhook work have separate slots. A probe cannot starve heartbeat.
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  while True:
   try:
    now=time.time();clock=time.monotonic()
    if now-last_tick>60:
     log('supervisor_loop_gap',gapSeconds=int(now-last_tick));next_probe=0
    last_tick=now
    if probe is not None and probe.done():
     health=probe.result();probe=None
     probe_failures=0 if health['accountVerified'] else probe_failures+1
     next_probe=clock+(30 if health['accountVerified'] else retry_delay(probe_failures,base=10,cap=300))
     health.update({'consecutiveProbeFailures':probe_failures,'healthRecoveryNeedsAttention':probe_failures>=5 or health.get('requiresUserAction',False),'nextProbeAt':int((now+max(0,next_probe-clock))*1000),'healthFailurePushAvailable':False,'failureNotification':'Existing terminal-job events; global health changes are visible in connection status.'})
     if health.get('code')!=last_health_code:
      log('health_changed',code=health.get('code'),accountVerified=health['accountVerified'],requiresUserAction=health.get('requiresUserAction',False),probeDurationMs=health.get('probeDurationMs'))
      last_health_code=health.get('code')
     save(ROOT/'health-state.json',health)
    if probe is None and clock>=next_probe:probe=pool.submit(health_probe,ROOT,sys.executable)
    if health['accountVerified'] and not delivery_authorized(health,now):
     health={**health,'accountVerified':False,'code':'HEALTH_CHECK_STALE','deliveryPaused':True};next_probe=0
     log('health_stale_delivery_paused')
    rpc(config,{'op':'heartbeat','health':health})
    if cloud_failures:
     log('cloud_transport_recovered',failedAttempts=cloud_failures);cloud_failures=0
     health.pop('cloudTransportError',None);health['cloudTransportFailedAttempts']=0;health['cloudRecoveryNeedsAttention']=False
    if callback and callback.done():rpc(config,callback.result());callback=None
    # Do not consume webhook attempts when account verification is paused.
    if not callback and delivery_authorized(health,time.time()):
     task=rpc(config,{'op':'callback'}).get('task')
     if task and health['accountVerified']:callback=pool.submit(send,task)
    if not delivery_authorized(health,time.time()):time.sleep(3);continue
    if now-last_recovery>30:
     for job in rpc(config,{'op':'recover'}).get('jobs',[]):
      path=JOURNAL/(job['id']+'.json')
      if not path.exists():
       # Cloud claimed but local journal absent: conservatively require reconciliation.
       save(path,{'id':job['id'],'job':job,'state':'delivery_unknown' if job['action']=='send_codex_message' else 'claimed','startIntent':job['action']=='send_codex_message','revision':1,'reason':'Missing local journal after claim; no automatic resend','created':int(now*1000)})
     last_recovery=now
    records=[]
    for path in JOURNAL.glob('*.json'):
     try:record=json.loads(path.read_text())
     except (ValueError,FileNotFoundError):continue
     records.append((path,record))
    count=sync_batch(records,config,synced)
    if count:log('journal_sync_batch_completed',records=count)
    if not delivery_authorized(health,time.time()):next_probe=0;continue
    launching={key:proc for key,proc in launching.items() if proc.poll() is None}
    active=[(p,r) for p,r in records if locked(p) or r['id'] in launching];busy_threads={r['job']['args'].get('threadId') for p,r in active}
    slots=4-len(active)
    for path,record in records:
     if slots<=0:break
     if locked(path) or record['id'] in launching or record.get('state') in STATES_TERMINAL:continue
     if record['job']['args'].get('threadId') in busy_threads:continue
     due=record.get('retryAt',0)/1000
     if now<due:continue
     if record.get('state') in ('delivery_unknown','executing','target_received','needs_desktop','awaiting_approval','needs_input') and now-reconciled.get(record['id'],0)<60:continue
     reconciled[record['id']]=now
     launching[record['id']]=launch(record,path);slots-=1;busy_threads.add(record['job']['args'].get('threadId'))
    if slots>0:
     job=rpc(config,{'op':'poll','version':2}).get('job')
     if job:
      path=JOURNAL/(job['id']+'.json')
      if not path.exists():save(path,{'id':job['id'],'job':job,'state':'claimed','revision':0,'created':int(now*1000)})
      # The next loop starts it after serializing against jobs on the same thread.
   except Exception as exc:
    info=error_info(exc,layer='cloud_transport');cloud_failures+=1;last_recovery=0
    delay=retry_delay(cloud_failures,cap=60) if info.get('retryable') else 300
    health.update({'cloudTransportError':info,'cloudTransportFailedAttempts':cloud_failures,'cloudRecoveryNeedsAttention':cloud_failures>=5 or info['requiresUserAction']})
    save(ROOT/'health-state.json',health)
    log('supervisor_retry',code=info['code'],errorClass=info['errorClass'],httpStatus=info.get('httpStatus'),retryInSeconds=delay,requiresUserAction=info['requiresUserAction'])
    time.sleep(delay);continue
   time.sleep(3)
def run():
 with open(ROOT/'agent.lock','a') as singleton:
  fcntl.flock(singleton,fcntl.LOCK_EX|fcntl.LOCK_NB)
  run_locked()
if __name__=='__main__':run()
