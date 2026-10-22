import copy,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'device'))
import bridge,official_queue as oq
class App:
 def __init__(self):self.pending=[];self.calls=[];self.turns=[];self.fail_after_add=False;self.deleted=True
 def call(self,method,p):
  self.calls.append((method,p))
  if method=='thread/turns/list':return {'data':self.turns}
  if method=='thread/queue/list':return {'data':self.pending}
  if method=='thread/queue/add':
   q={'id':'queue-1','clientUserMessageId':p['clientUserMessageId'],'input':p['input']};self.pending.append(q)
   if self.fail_after_add:raise TimeoutError('lost add response')
   return {'queuedSubmission':q}
  if method=='thread/queue/delete':
   if self.deleted:self.pending=[]
   return {'deleted':self.deleted}
  raise AssertionError(method)
class QueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'job.json'
  self.r={'id':'a'*64,'created':int(time.time()*1000),'job':{'id':'a'*64,'action':'send_codex_message','args':{'threadId':'2e8c4d2e-fe11-5b85-bc83-96595bf5485a','message':'ACK only','execution':'headless'}}};self.app=App()
 def tearDown(self):self.tmp.cleanup()
 def enqueue(self):oq.enqueue(bridge,self.r,self.path,self.app)
 def test_queue_is_not_receipt_and_durable_intent(self):
  self.enqueue();r=json.loads(self.path.read_text());self.assertTrue(r['startIntent']);self.assertFalse(r['targetReceived']);self.assertEqual(r['queueId'],'queue-1')
 def test_timeout_recovery_no_second_add(self):
  self.app.fail_after_add=True
  with self.assertRaises(TimeoutError):self.enqueue()
  r=json.loads(self.path.read_text());oq.poll(bridge,r,self.path,self.app);oq.poll(bridge,r,self.path,self.app)
  self.assertEqual(sum(m=='thread/queue/add' for m,p in self.app.calls),1);self.assertFalse(r['targetReceived'])
 def test_same_job_run_reuses_pending_and_then_actual_turn(self):
  self.enqueue()
  class Conn(App):
   def close(self):pass
  self.app.close=lambda:None
  with patch.object(bridge,'checked_app',return_value=self.app):
   bridge.run_job(self.r['job'],self.path);bridge.run_job(self.r['job'],self.path)
  self.assertEqual(sum(m=='thread/queue/add' for m,p in self.app.calls),1)
  self.app.pending=[];self.app.turns=[{'id':'turn-real','status':'completed','items':[{'type':'userMessage','content':oq.payload(self.r)},{'type':'agentMessage','text':'ACK only'}]}]
  with patch.object(bridge,'checked_app',return_value=self.app):r=bridge.run_job(self.r['job'],self.path)
  self.assertEqual(r['state'],'completed');self.assertTrue(r['targetReceived']);self.assertEqual(r['turnId'],'turn-real')
 def test_external_interrupted_without_error_is_not_terminal_failure(self):
  self.enqueue();self.app.pending=[];self.app.turns=[{'id':'still-active','status':'interrupted','error':None,'items':[{'type':'userMessage','content':oq.payload(self.r)}]}]
  oq.poll(bridge,self.r,self.path,self.app);self.assertEqual(self.r['state'],'delivery_unknown');self.assertTrue(self.r['targetReceived']);self.assertNotIn(self.r['state'],bridge.STATES_TERMINAL)
 def test_absent_queue_no_receipt_no_replay(self):
  self.enqueue();self.app.pending=[];oq.poll(bridge,self.r,self.path,self.app)
  self.assertEqual(self.r['state'],'delivery_unknown');self.assertFalse(self.r['targetReceived']);self.assertEqual(sum(m=='thread/queue/add' for m,p in self.app.calls),1)
 def test_timeout_removes_only_owned_item(self):
  self.enqueue();self.app.pending.append({'id':'other','clientUserMessageId':'other','input':[]});self.r['queueDeadline']=0
  oq.poll(bridge,self.r,self.path,self.app)
  self.assertEqual(self.r['state'],'failed');self.assertEqual([p['queuedSubmissionId'] for m,p in self.app.calls if m=='thread/queue/delete'],['queue-1'])
 def test_delete_race_is_unknown_not_cancelled(self):
  self.enqueue();self.r['queueDeadline']=0;self.app.deleted=False;oq.poll(bridge,self.r,self.path,self.app)
  self.assertEqual(self.r['state'],'delivery_unknown')
 def test_foreign_text_with_same_id_is_never_deleted(self):
  self.enqueue();self.app.pending[0]['input']=[{'type':'text','text':'foreign','text_elements':[]}];self.r['queueDeadline']=0
  oq.poll(bridge,self.r,self.path,self.app);self.assertFalse(any(m=='thread/queue/delete' for m,p in self.app.calls))
if __name__=='__main__':unittest.main()
