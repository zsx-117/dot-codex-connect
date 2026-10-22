"""Only the worker holding the live App Server connection may steer its turn.

The durable journal is the inbox; no new listener, credentials, or owner takeover.
"""
import fcntl,json,time

class Steering:
 def __init__(self,bridge,app,parent):
  self.b=bridge;self.app=app;self.parent=parent;self.children=[]
 def poll(self):
  b=self.b;tid=self.parent['job']['args']['threadId'];turn_id=self.parent.get('turnId')
  if not turn_id or not self.app.possibly_running:return
  for path in b.JOURNAL.glob('*.json'):
   try:r=json.loads(path.read_text())
   except (ValueError,OSError):continue
   if not isinstance(r,dict) or not r.get('id') or not isinstance(r.get('job'),dict):continue
   if r['id']==self.parent['id'] or r['job'].get('action')!='send_codex_message' or r['job'].get('args',{}).get('threadId')!=tid:continue
   if r.get('startIntent') or r.get('state') in b.STATES_TERMINAL:continue
   lock=open(str(path)+'.lock','a')
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:lock.close();continue
   try:
    r=json.loads(path.read_text())
    if r.get('startIntent') or r.get('state') in b.STATES_TERMINAL:continue
    if b.expired_unsent(r,path):continue
    if r['job']['args'].get('execution')!='headless':
     b.update(r,path,'blocked_capability',reason='Desktop tools cannot be inherited by this connection.',targetReceived=False);continue
    binding=json.loads((b.ROOT/'account-binding.json').read_text())
    if b.fingerprint(self.app)!=binding['fingerprint']:raise ValueError('Account binding changed; steering refused')
    evidence={'classification':'plugin_owned_active_turn','ownerVerified':True,'ownerJobId':self.parent['id'],'observedTurnId':turn_id,'observedAt':int(time.time()*1000)}
    b.update(r,path,'submitting',startIntent=True,deliveryMode='steer',expectedTurnId=turn_id,writerEvidence=evidence,targetReceived=False,reason='steer_intent_persisted')
    response=self.app.call('turn/steer',{'threadId':tid,'expectedTurnId':turn_id,'clientUserMessageId':r['id'],'input':[{'type':'text','text':'[dot-request:'+r['id']+']\n'+r['job']['args']['message']}]})
    if response.get('turnId')!=turn_id:raise ValueError('Unexpected steering turn ID; outcome unknown')
    b.update(r,path,'submitting',turnId=turn_id,steerAccepted=True,reason='steer_accepted_waiting_for_target_item',targetReceived=False,sharedTurnReply=True)
    self.children.append((path,r,lock));lock=None
   except b.RpcError as exc:
    b.update(r,path,'failed',reason='explicit_steer_rejection',error=exc.error,retryAutomatically=False,targetReceived=False)
   except Exception as exc:
    b.update(r,path,'delivery_unknown' if r.get('startIntent') else 'failed',reason=type(exc).__name__,retryAutomatically=False)
   finally:
    if lock:lock.close()
 def observe(self,event):
  p=event.get('params',{});item=p.get('item',{})
  if p.get('threadId')!=self.parent['job']['args']['threadId'] or p.get('turnId')!=self.parent.get('turnId'):return
  if event.get('method')!='item/completed' or item.get('type')!='userMessage':return
  texts=[c.get('text','') for c in item.get('content',[]) if c.get('type')=='text']
  for path,r,_ in self.children:
   if any('[dot-request:'+r['id']+']' in text for text in texts):
    self.b.update(r,path,'executing',targetReceived=True,reason='matching_user_item_observed',receiptItemId=item.get('id'))
 def finish(self):
  for path,r,_ in self.children:
   try:self.b.reconcile(r,path,self.app)
   except Exception as exc:self.b.update(r,path,'delivery_unknown',reason=type(exc).__name__,retryAutomatically=False)
 def close(self):
  for _,_,lock in self.children:lock.close()
