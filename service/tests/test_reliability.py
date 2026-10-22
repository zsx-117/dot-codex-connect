import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'device'))
import bridge
from transport import RpcError
from webhooks import public_addresses
class Fake:
 def __init__(self,busy=False,running=False):self.busy=busy;self.running=running;self.started=0;self.closed=0;self.possibly_running=False;self.queued=0;self.methods=[]
 def call(self,method,p):
  self.methods.append(method)
  if method=='thread/queue/list':return {'data':[]}
  if method=='thread/queue/add':self.queued+=1;return {'queuedSubmission':{'id':'q1'}}
  if method=='thread/turns/list':return {'data':[{'id':'existing','status':'inProgress','items':[]}] if self.running else []}
  if method=='thread/resume' and self.busy:raise RpcError({'code':-32600,'message':'already has an active writer'})
  if method=='turn/start':self.started+=1;return {'turn':{'id':'new-turn','status':'inProgress'}}
  return {}
 def event(self,timeout):return {'method':'turn/completed','params':{'threadId':'d23161f9-e454-5928-8233-3dabb2ed69e9','turn':{'id':'new-turn','status':'completed'}}}
 def close(self):self.closed+=1
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.json';self.job={'id':'a'*64,'action':'send_codex_message','requestId':'test-stable-1','args':{'threadId':'d23161f9-e454-5928-8233-3dabb2ed69e9','message':'ACK','execution':'headless'}}
 def tearDown(self):self.tmp.cleanup()
 def runfake(self,f):
  with patch.object(bridge,'checked_app',return_value=f),patch.object(bridge,'JOURNAL',Path(self.tmp.name)):return bridge.run_job(self.job,self.path)
 def test_active_writer_unknown_owner_not_sent(self):
  f=Fake(busy=True);r=self.runfake(f);self.assertEqual(r['state'],'submitting');self.assertEqual(f.started,0);self.assertEqual(f.queued,1);self.assertFalse(r['targetReceived']);self.assertTrue(r['startIntent'])
 def test_running_task_never_interrupted(self):
  f=Fake(running=True);r=self.runfake(f);self.assertEqual(r['deliveryMode'],'official_queue');self.assertEqual(f.started,0);self.assertEqual(f.queued,1);self.assertNotIn('thread/resume',f.methods);self.assertNotIn('turn/interrupt',f.methods)
 def test_same_request_delivered_once(self):
  f=Fake();self.assertEqual(self.runfake(f)['state'],'completed');self.assertEqual(self.runfake(f)['state'],'completed');self.assertEqual(f.started,1)
 def test_unknown_not_resent_after_restart(self):
  bridge.save(self.path,{'id':self.job['id'],'job':self.job,'startIntent':True,'state':'submitting','revision':1});f=Fake();r=self.runfake(f);self.assertEqual(r['state'],'delivery_unknown');self.assertEqual(f.started,0)
 def test_desktop_gated_before_turn(self):
  self.job['args']['execution']='desktop_required';f=Fake();self.assertEqual(self.runfake(f)['state'],'blocked_capability');self.assertEqual(f.started,0)
 def test_disconnected_delivery_reconciles_without_send(self):
  bridge.save(self.path,{'id':self.job['id'],'job':self.job,'startIntent':True,'state':'delivery_unknown','revision':1})
  f=Fake();f.call=lambda m,p:{'data':[{'id':'recovered-turn','status':'completed','items':[{'type':'userMessage','content':[{'type':'text','text':'[dot-request:'+self.job['id']+'] ACK'}]},{'type':'agentMessage','text':'ACTUAL ACK'}]}]}
  r=self.runfake(f);self.assertEqual(r['state'],'completed');self.assertEqual(r['turnId'],'recovered-turn');self.assertEqual(r['messages'],['ACTUAL ACK']);self.assertEqual(f.started,0)
 def test_callback_private_addresses_blocked(self):
  with patch('socket.getaddrinfo',return_value=[(None,None,None,None,('127.0.0.1',443))]):
   with self.assertRaises(ValueError):public_addresses('example.test')
 def test_fake_ip_dns_does_not_call_an_embedded_external_resolver(self):
  with patch('socket.getaddrinfo',return_value=[(None,None,None,None,('198.18.0.1',443))]), patch('urllib.request.urlopen',side_effect=AssertionError('must not query an external resolver')):
   with self.assertRaises(ValueError):public_addresses('example.test')
 def test_expired_writer_never_retries_or_opens_connection(self):
  bridge.save(self.path,{'id':self.job['id'],'job':self.job,'created':1,'state':'waiting_writer','revision':1})
  with patch.object(bridge,'checked_app',side_effect=AssertionError('must not open a writer')):
   r=bridge.run_job(self.job,self.path)
   self.assertEqual(r['state'],'failed');self.assertEqual(r['error']['code'],'WRITER_WAIT_EXPIRED')
   self.assertFalse(r['targetReceived']);self.assertEqual(bridge.run_job(self.job,self.path),r)
 def test_steer_turn_id_without_marker_is_not_receipt(self):
  bridge.save(self.path,{'id':self.job['id'],'job':self.job,'startIntent':True,'deliveryMode':'steer','turnId':'existing','state':'submitting','revision':1})
  f=Fake();f.call=lambda m,p:{'data':[{'id':'existing','status':'completed','items':[]}]}
  r=self.runfake(f);self.assertEqual(r['state'],'delivery_unknown');self.assertEqual(f.started,0)
if __name__=='__main__':unittest.main()
