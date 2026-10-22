#!/usr/bin/env python3
"""Durable, account-bound local adapter for the public Codex App Server API."""
import argparse,fcntl,hashlib,json,os,queue,re,sys,time
from pathlib import Path
from transport import AppServer,RpcError,Disconnected
from reliability import BridgeFault,VERSION,HEALTH_RPC_SECONDS,error_info,may_retry_unsent,retry_delay
from interactions import request_interaction
from runtime import DATA
ROOT=DATA
JOURNAL=ROOT/'jobs-v2';JOURNAL.mkdir(mode=0o700,exist_ok=True)
CAPABILITIES={'environment':'standalone_app_server','desktopBrowser':False,'desktopComputerUse':False,'desktopApprovalUI':False,'desktopToolInheritance':False,'headlessTurns':True,'writerOwnerInspection':False}
SCOPE={'deviceId':'mac','deviceName':'授权的本机 Mac','supported':'This Codex home on this Mac, current and future persisted chats, archived filter supported','unsupported':['cloud-only chats','other devices not enrolled','ephemeral chats not persisted','per-thread historical account ownership cannot be independently proven by local API'],'accountIsolation':'Pinned signed-in account fingerprint; stop on account change; only specifically requested chat content is read.'}
STATES_TERMINAL={'completed','failed','blocked_capability','cancelled'}
WRITER_WAIT_MS=300000
CAPABILITIES.update({'sameConnectionSteering':True,'desktopOwnerRouting':'official_queue_fallback','externalActiveTurnSteering':False,'queueAcceptedIsReceipt':False,'writerWaitLimitMs':WRITER_WAIT_MS})
def expired_unsent(record,path):
 if record.get('startIntent') or record.get('targetReceived') or record.get('turnId') or record['job']['action']!='send_codex_message':return False
 deadline=record.setdefault('writerDeadline',record.get('created',int(time.time()*1000))+WRITER_WAIT_MS)
 if int(time.time()*1000)<deadline:return False
 record.setdefault('writerEvidence',{'classification':'owner_unknown','ownerVerified':False,'connectedVersusStale':'not_identifiable_by_available_API','lastReason':record.get('reason'),'lastRpcError':record.get('rpcError')})
 writer=record.get('state')=='waiting_writer' or record.get('writerEvidence',{}).get('observedTurnId') is not None
 update(record,path,'failed',reason='writer_wait_expired' if writer else 'unsent_delivery_deadline_expired',error={'code':'WRITER_WAIT_EXPIRED' if writer else 'UNSENT_DELIVERY_DEADLINE_EXPIRED','message':'No delivery before the five-minute deadline. No lock released, no task interrupted. This request will not be retried.'},retryAutomatically=False,targetReceived=False)
 return True
def waiting(record,path,reason,recent=None,**fields):
 recent=(recent or [{}])[0]
 evidence={'classification':'active_turn_observed' if recent.get('status')=='inProgress' else 'owner_unknown','observedTurnId':recent.get('id'),'observedTurnStatus':recent.get('status'),'ownerVerified':False,'connectedVersusStale':'not_identifiable_by_available_API','observedAt':int(time.time()*1000)}
 record['writerEvidence']=evidence
 if expired_unsent(record,path):return
 update(record,path,'waiting_writer',reason=reason,retryAt=int(time.time()*1000)+30000,retryAutomatically=True,targetReceived=False,**fields)
def save(path,value):
 temp=path.with_name(path.name+'.tmp');fd=os.open(temp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
 os.replace(temp,path)
 fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def fingerprint(app):
 a=app.call('account/read',{'refreshToken':False});account=a.get('account') or {};routing=a.get('workspaceRouting') or {}
 if account.get('type')!='chatgpt':raise BridgeFault('CHATGPT_LOGIN_REQUIRED','The enrolled ChatGPT login is unavailable; user login is required.',user_action=True)
 key=routing.get('chatgptAccountId')
 if not key:raise BridgeFault('ACCOUNT_IDENTITY_UNAVAILABLE','Account routing identity is unavailable; delivery remains paused.',retryable=True)
 return hashlib.sha256(('dot-account-v2\0'+key+'\0'+account.get('email','')).encode()).hexdigest()
def checked_app(rpc_timeout=40,experimental=False):
 app=AppServer(rpc_timeout=rpc_timeout,experimental=experimental)
 try:
  try:binding=json.loads((ROOT/'account-binding.json').read_text())
  except FileNotFoundError:raise BridgeFault('ACCOUNT_BINDING_MISSING','The existing account binding is missing; it was not recreated.',user_action=True) from None
  except PermissionError:raise BridgeFault('ACCOUNT_BINDING_ACCESS_DENIED','Existing account binding access is denied; delivery remains paused.',user_action=True) from None
  except ValueError:raise BridgeFault('ACCOUNT_BINDING_INVALID','The existing account binding is invalid; explicit repair is required.',user_action=True) from None
  if not isinstance(binding,dict) or not isinstance(binding.get('fingerprint'),str):raise BridgeFault('ACCOUNT_BINDING_INVALID','The existing account binding is invalid; explicit repair is required.',user_action=True)
  if fingerprint(app)!=binding['fingerprint']:raise BridgeFault('ACCOUNT_BINDING_MISMATCH','The signed-in account differs from the enrolled account; explicit re-enrollment is required.',user_action=True)
  return app
 except BaseException:app.close();raise
def thread_id(value):
 if not isinstance(value,str) or not re.fullmatch(r'[0-9a-f-]{36}',value):raise ValueError('Invalid thread ID')
 return value

def metadata(t):return {'id':t['id'],'title':t.get('name'),'titleAvailable':t.get('name') is not None,'deviceId':'mac','deviceName':SCOPE['deviceName'],'status':t.get('status'),'statusAuthority':'local App Server view; notLoaded does NOT mean writable','writer':'unknown','source':t.get('source'),'updatedAt':t.get('updatedAt')}
def list_threads(args,app=None):
 own=app is None;app=app or checked_app()
 try:
  p={'limit':min(100,max(1,int(args.get('limit',30)))),'sortKey':'updated_at','sortDirection':'desc','modelProviders':[],'archived':bool(args.get('archived',False)),'sourceKinds':['cli','vscode','exec','appServer','subAgent','subAgentReview','subAgentCompact','subAgentThreadSpawn','subAgentOther','unknown']}
  if args.get('cursor'):p['cursor']=args['cursor']
  if args.get('query'):p['searchTerm']=args['query']
  r=app.call('thread/list',p)
  return {'chats':[metadata(t) for t in r['data']],'nextCursor':r.get('nextCursor'),'archived':p['archived'],'scope':SCOPE}
 finally:
  if own:app.close()
def read_thread(args,app=None):
 own=app is None;app=app or checked_app();tid=thread_id(args['threadId'])
 try:
  t=app.call('thread/read',{'threadId':tid,'includeTurns':False})['thread']
  p={'threadId':tid,'limit':min(10,max(1,int(args.get('limit',3)))),'sortDirection':'desc','itemsView':'full'}
  if args.get('cursor'):p['cursor']=args['cursor']
  r=app.call('thread/turns/list',p)
  turns=[]
  for turn in r['data']:
   msgs=[]
   for item in turn.get('items',[]):
    if item.get('type')=='agentMessage':msgs.append({'type':'agentMessage','text':item.get('text','')})
    if item.get('type')=='userMessage':msgs.append({'type':'userMessage','text':'\n'.join(c.get('text','') for c in item.get('content',[]) if c.get('type')=='text')})
   turns.append({'id':turn['id'],'status':turn.get('status'),'error':turn.get('error'),'messages':msgs})
  return {'chat':metadata(t),'turns':turns,'nextCursor':r.get('nextCursor'),'scope':SCOPE}
 finally:
  if own:app.close()
def update(record,path,status,**fields):
 record.update(fields);record['state']=status;record['updated']=int(time.time()*1000);record['revision']=record.get('revision',0)+1
 record.setdefault('history',[]).append({'state':status,'at':record['updated'],'turnId':record.get('turnId'),'reason':record.get('reason')})
 record['history']=record['history'][-100:];save(path,record)
def turn_text(turn):return [i.get('text','') for i in turn.get('items',[]) if i.get('type')=='agentMessage']
def reconcile(record,path,app,missing_update=True):
 """Read-only recovery. Absence is NOT evidence of failed delivery; never resend."""
 args=record['job']['args'];tid=args['threadId'];cursor=None;marker='[dot-request:'+record['id']+']';found=None
 for _ in range(100):
  p={'threadId':tid,'limit':25,'sortDirection':'desc','itemsView':'full'}
  if cursor:p['cursor']=cursor
  page=app.call('thread/turns/list',p)
  for t in page['data']:
   if record.get('deliveryMode')!='steer' and t['id']==record.get('turnId'):found=t;break
   for i in t.get('items',[]):
    if i.get('type')=='userMessage' and any(marker in c.get('text','') for c in i.get('content',[]) if c.get('type')=='text'):found=t;break
   if found:break
  if found:break
  cursor=page.get('nextCursor')
  if not cursor:break
 if found:
  if record.get('deliveryMode')=='official_queue' and found.get('status')=='interrupted' and not found.get('error'):
   update(record,path,'delivery_unknown',turnId=found['id'],targetReceived=True,messages=turn_text(found),observedTurnStatus='interrupted',reason='external_reader_status_unconfirmed_owner_may_still_be_running',retryAutomatically=False,retryAt=int(time.time()*1000)+60000)
   return True
  state='completed' if found.get('status')=='completed' else 'failed' if found.get('status') in ('failed','interrupted') else 'executing'
  update(record,path,state,turnId=found['id'],targetReceived=True,messages=turn_text(found),error=found.get('error'),reason='reconciled_from_target_history')
  return True
 if missing_update:update(record,path,'delivery_unknown',reason='No matching persisted turn found; absence is inconclusive. Automatic resend disabled.',retryAutomatically=False)
 return False

def run_job(job,path=None):
 path=path or JOURNAL/(job['id']+'.json')
 # Same-request recovery joins the existing durable record, without another RPC
 # connection or a second worker waiting for the entire task to finish.
 lock=open(str(path)+'.lock','a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  lock.close()
  try:existing=json.loads(path.read_text())
  except FileNotFoundError:existing={'id':job['id'],'state':'delivery_unknown','targetReceived':False,'reason':'worker_in_flight_journal_not_yet_written'}
  if existing.get('job') is not None and existing['job']!=job:raise ValueError('Local requestId payload conflict')
  return {**existing,'observation':{'kind':'worker_in_flight','coalesced':True,'queryOnly':True,'stateAuthority':'existing durable journal'}}
 try:
  record=json.loads(path.read_text()) if path.exists() else {'id':job['id'],'job':job,'created':int(time.time()*1000),'revision':0,'targetReceived':False}
  # A conflicting retry cannot modify the rightful request's journal, even if
  # its writer has just finished. Validate outside the execution-error handler.
  if record['job']!=job:raise ValueError('Local requestId payload conflict')
 except BaseException:lock.close();raise
 app=None;steering=None
 try:
  if record.get('state') in STATES_TERMINAL:return record
  if expired_unsent(record,path):return record
  app=checked_app(experimental=True);args=job['args'];action=job['action']
  if record.get('deliveryMode')=='official_queue':
   from official_queue import poll
   poll(sys.modules[__name__],record,path,app);return record
  if record.get('startIntent') or record.get('targetReceived') or record.get('turnId'):
   reconcile(record,path,app);return record
  update(record,path,'received',bridgeReceived=True,capabilities=CAPABILITIES,error=None,reason=None,retryAt=0,retryAutomatically=False)
  if action=='list_codex_threads':
   update(record,path,'completed',result=list_threads(args,app));return record
  if action=='read_codex_thread':
   update(record,path,'completed',result=read_thread(args,app));return record
  if action=='send_dot_message':
   # Verify source chat metadata, but do not bulk-read the source conversation.
   t=app.call('thread/read',{'threadId':thread_id(args['sourceThreadId']),'includeTurns':False})['thread']
   source_turn=None;reply_to=args.get('inReplyTo')
   # Correlate only this specifically authorized source chat and this exact tool request.
   page=app.call('thread/turns/list',{'threadId':t['id'],'limit':3,'itemsView':'full','sortDirection':'desc'})
   for candidate in page['data']:
    for item in candidate.get('items',[]):
     call_args=item.get('arguments',{})
     if isinstance(call_args,str):
      try:call_args=json.loads(call_args)
      except ValueError:call_args={}
     if item.get('type')=='mcpToolCall' and str(item.get('tool','')).endswith('send_dot_message') and isinstance(call_args,dict) and call_args.get('requestId')==job.get('requestId'):
      source_turn=candidate['id']
      if not reply_to:
       text=' '.join(c.get('text','') for i in candidate.get('items',[]) if i.get('type')=='userMessage' for c in i.get('content',[]) if c.get('type')=='text')
       marker=re.search(r'\[dot-request:([a-f0-9]{64})\]',text)
       if marker:reply_to=marker.group(1)
      break
    if source_turn:break
   update(record,path,'completed',result={'source':metadata(t),'message':args['message'],'inReplyTo':reply_to,'sourceTurnId':source_turn or args.get('sourceTurnId'),'sourceTurnIdVerified':source_turn is not None,'dotReceipt':'awaiting_event_ack'});return record
  if action!='send_codex_message':raise ValueError('Unknown action')
  tid=thread_id(args['threadId'])
  if args.get('execution','headless')!='headless':
   update(record,path,'blocked_capability',reason='Official standalone App Server cannot inherit the desktop browser/computer-use/approval tools. Message was not sent.',targetReceived=False);return record
  recent=app.call('thread/turns/list',{'threadId':tid,'limit':1,'itemsView':'notLoaded'})['data']
  if recent and recent[0].get('status')=='inProgress':
   record['writerEvidence']={'classification':'active_turn_observed','observedTurnId':recent[0]['id'],'ownerVerified':False}
   from official_queue import enqueue
   enqueue(sys.modules[__name__],record,path,app);return record
  try:app.call('thread/resume',{'threadId':tid,'excludeTurns':True})
  except RpcError as exc:
   if 'active writer' in str(exc).lower():
    record['writerEvidence']={'classification':'owner_unknown','ownerVerified':False,'connectedVersusStale':'not_identifiable_by_available_API','rpcError':exc.error}
    from official_queue import enqueue
    enqueue(sys.modules[__name__],record,path,app);return record
   raise
  # Recheck after taking only our own writer. Never steer an existing running task.
  recent=app.call('thread/turns/list',{'threadId':tid,'limit':1,'itemsView':'notLoaded'})['data']
  if recent and recent[0].get('status')=='inProgress':
   waiting(record,path,'running_turn_after_resume',recent);return record
  update(record,path,'submitting',startIntent=True,reason=None)
  app.possibly_running=True
  try:
   response=app.call('turn/start',{'threadId':tid,'clientUserMessageId':job['id'],'input':[{'type':'text','text':'[dot-request:'+job['id']+']\n'+args['message']}]})
   turn=response['turn'];update(record,path,'target_received',turnId=turn['id'],targetReceived=True,reason=None)
   if turn.get('status')=='inProgress':update(record,path,'executing')
  except RpcError as exc:
   # Explicit rejection: no turn was accepted. Busy start can be retried safely.
   app.possibly_running=False
   if 'active writer' in str(exc).lower():
    record['startIntent']=False
    waiting(record,path,'writer_rejected_turn_start',recent,rpcError=exc.error);return record
   update(record,path,'failed',error=exc.error,reason='explicit_turn_start_rejection');return record
  except (queue.Empty,TimeoutError):
   update(record,path,'delivery_unknown',reason='turn/start response missing; waiting on the same connection, not resending',retryAutomatically=False)
  from steering import Steering
  steering=Steering(sys.modules[__name__],app,record)
  messages=[]
  while True:
   steering.poll()
   try:event=app.event(2)
   except queue.Empty:continue  # No task-duration timeout; preserve our active connection.
   if 'id' in event and 'method' in event:
    p=event.get('params',{});interaction=request_interaction(event['method'])
    scoped=p.get('threadId')==tid and (not p.get('turnId') or p['turnId']==record.get('turnId'))
    if scoped:update(record,path,interaction['pendingState'],interaction={**interaction,'status':'pending','requestedAt':int(time.time()*1000)},requiresUserAction=True)
    # Keep the existing refusal: no approval, input fabrication or dynamic tool
    # execution is added. An unavailable interaction is not indefinitely pending.
    app.write({'id':event['id'],'error':{'code':-32601,'message':'Desktop interaction unavailable in standalone bridge. No action approved.'}})
    if scoped:update(record,path,'needs_desktop',reason=interaction['method'],interaction={**interaction,'status':'unavailable','response':'unsupported_no_action_approved'},requiresUserAction=True)
    continue
   p=event.get('params',{});method=event.get('method');turn=p.get('turn',{})
   if p.get('threadId')!=tid:continue
   if method in ('turn/started','item/completed','turn/completed'):
    # Both identities must agree before any task or shared-turn receipt changes.
    if p.get('turnId') and turn.get('id') and p['turnId']!=turn['id']:continue
    observed_turn=p.get('turnId') or turn.get('id')
    if not observed_turn:continue
    if record.get('turnId') and observed_turn!=record['turnId']:continue
    if not record.get('turnId'):
     # A lost start response needs our exact message marker, not simply the
     # next turn on this thread. Never adopt another client's turn.
     items=turn.get('items',[])+([p['item']] if p.get('item') else [])
     marker='[dot-request:'+record['id']+']'
     if not any(i.get('type')=='userMessage' and any(marker in c.get('text','') for c in i.get('content',[]) if c.get('type')=='text') for i in items):continue
     update(record,path,'target_received',turnId=observed_turn,targetReceived=True,reason='matching_user_item_observed_after_missing_start_response')
   steering.observe(event)
   if method=='thread/status/changed' and p.get('status',{}).get('type')=='active':
    flags=p['status'].get('activeFlags',[])
    if 'waitingOnApproval' in flags and record.get('interaction',{}).get('status')!='unavailable':
     update(record,path,'awaiting_approval',reason='observed_waiting_on_approval',requiresUserAction=True)
    # Idle/notLoaded flags never establish writable ownership or completion.
    elif not flags and record.get('state') in ('awaiting_approval','needs_input','needs_desktop'):
     update(record,path,'executing',reason='observed_active_without_wait_flags',requiresUserAction=False)
   if method=='turn/started':update(record,path,'executing',targetReceived=True,turnId=observed_turn)
   if p.get('turnId') and record.get('turnId') and p['turnId']!=record['turnId']:continue
   if method=='item/completed' and p.get('item',{}).get('type')=='agentMessage':
    messages.append(p['item'].get('text',''));update(record,path,record['state'],messages=messages)
   if method=='turn/completed' and (not record.get('turnId') or turn.get('id')==record['turnId']):
    app.possibly_running=False
    steering.finish()
    # The verified terminal snapshot can recover missed item notifications.
    # Use its ordered replies once, rather than appending duplicate stream text.
    completed_messages=turn_text(turn)
    if any(completed_messages):messages=completed_messages
    state='completed' if turn.get('status')=='completed' else 'failed'
    update(record,path,state,targetReceived=True,turnId=turn.get('id'),messages=messages,error=turn.get('error'),requiresUserAction=False);return record
 except Exception as exc:
  record=locals().get('record',{'id':job['id'],'job':job})
  info=error_info(exc)
  if record.get('startIntent') or record.get('targetReceived') or record.get('turnId'):
   update(record,path,'delivery_unknown',reason='reconciliation_required',error=info,retryAutomatically=False)
  elif may_retry_unsent(record,info):
   attempts=record.get('retryAttempts',0)+1
   update(record,path,'received',reason='retryable_pre_delivery_failure',error=info,retryAttempts=attempts,retryAt=int(time.time()*1000)+retry_delay(attempts)*1000,retryAutomatically=True,targetReceived=False)
  else:update(record,path,'failed',reason='pre_delivery_recovery_exhausted' if record.get('retryAttempts') else 'pre_delivery_failure',error=info,retryAutomatically=False,targetReceived=False)
  return record
 finally:
  if steering:steering.close()
  if app:app.close()
  lock.close()

def health_check():
 app=None
 try:
  app=checked_app(rpc_timeout=HEALTH_RPC_SECONDS)
  return {'accountVerified':True,'code':'HEALTHY','reason':'Enrolled account verified.','version':VERSION,'retryable':False,'requiresUserAction':False,'codexExecutable':{'source':app.executable.source,'version':app.executable.version}}
 except Exception as exc:
  info=error_info(exc)
  return {'accountVerified':False,**info,'reason':info['message'],'version':VERSION}
 finally:
  if app:app.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['worker','list','read','health']);p.add_argument('value',nargs='?');a=p.parse_args()
 if a.action=='worker':run_job(json.loads(Path(a.value).read_text())['job'])
 elif a.action=='list':print(json.dumps(list_threads({}),ensure_ascii=False))
 elif a.action=='health':print(json.dumps(health_check(),ensure_ascii=False))
 else:print(json.dumps(read_thread({'threadId':a.value}),ensure_ascii=False))
