"""Public experimental queue fallback. No owner takeover and never replay an add.

Codex 0.162.0-alpha.2 does NOT deduplicate clientUserMessageId on queue/add.
The bridge job lock plus fsynced startIntent is therefore the authority.
"""
import time

def payload(record):
 return [{'type':'text','text':'[dot-request:'+record['id']+']\n'+record['job']['args']['message']}]

def owned_pending(app,record):
 cursor=None;found=[];tid=record['job']['args']['threadId']
 for _ in range(100):
  params={'threadId':tid,'limit':100}
  if cursor:params['cursor']=cursor
  page=app.call('thread/queue/list',params)
  for item in page['data']:
   # A client id alone is insufficient: verify the exact bridge-owned text too.
   if item.get('clientUserMessageId')==record['id'] and item.get('input')==payload(record):found.append(item)
  cursor=page.get('nextCursor')
  if not cursor:return found
 raise RuntimeError('Queue pagination limit reached; no submission attempted')

def enqueue(b,record,path,app):
 # Persist BEFORE the mutation. Any lost response subsequently becomes read-only recovery.
 existing=owned_pending(app,record)
 b.update(record,path,'submitting',startIntent=True,deliveryMode='official_queue',queueDeadline=int(time.time()*1000)+b.WRITER_WAIT_MS,queueAccepted=bool(existing),targetReceived=False,reason='official_queue_intent_persisted',retryAutomatically=False)
 if existing:
  record['queueId']=existing[0]['id']
  return poll(b,record,path,app)
 try:
  result=app.call('thread/queue/add',{'threadId':record['job']['args']['threadId'],'clientUserMessageId':record['id'],'input':payload(record)})['queuedSubmission']
 except b.RpcError as exc:
  b.update(record,path,'failed',reason='official_queue_explicit_rejection',error=exc.error,targetReceived=False,retryAutomatically=False)
  return
 b.update(record,path,'submitting',queueId=result['id'],queueAccepted=True,reason='official_queue_accepted_not_target_receipt',retryAt=int(time.time()*1000)+15000,retryAutomatically=False,targetReceived=False)

def poll(b,record,path,app):
 # A matching target user item, never queue disappearance, establishes receipt.
 if b.reconcile(record,path,app,missing_update=False):return
 pending=owned_pending(app,record);now=int(time.time()*1000)
 if len(pending)>1:
  b.update(record,path,'delivery_unknown',reason='duplicate_queue_items_observed_no_resend',queueIds=[i['id'] for i in pending],retryAutomatically=False,retryAt=now+60000)
  return
 if pending:
  item=pending[0]
  if now>=record['queueDeadline']:
   # Deletes ONLY this plugin's verified pending item, never an active turn or writer.
   deleted=app.call('thread/queue/delete',{'threadId':record['job']['args']['threadId'],'queuedSubmissionId':item['id']}).get('deleted')
   if b.reconcile(record,path,app,missing_update=False):return
   if deleted:
    b.update(record,path,'failed',reason='official_queue_deadline_expired_removed_own_pending_item',error={'code':'QUEUE_WAIT_EXPIRED','message':'Pending message was removed after five minutes without target receipt. No task interrupted.'},queueId=item['id'],queueRemoved=True,targetReceived=False,retryAutomatically=False)
    return
   b.update(record,path,'delivery_unknown',reason='queue_delete_raced_with_dispatch_check_target_history',retryAutomatically=False,retryAt=now+60000)
   return
  b.update(record,path,'submitting',queueId=item['id'],queueAccepted=True,targetReceived=False,reason='official_queue_waiting_for_existing_owner_not_steering',retryAt=now+15000,retryAutomatically=False)
  return
 b.update(record,path,'delivery_unknown',reason='queue_absent_target_receipt_unconfirmed_no_resend',queueOutcomeTimedOut=now>=record['queueDeadline'],retryAt=now+60000,retryAutomatically=False)
