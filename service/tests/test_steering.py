import json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'device'))
import bridge
from steering import Steering

class FakeOwner:
 def __init__(self):self.possibly_running=True;self.calls=[];self.error=None;self.items=[]
 def call(self,method,args):
  self.calls.append((method,args))
  if method=='turn/steer':
   if self.error:raise self.error
   return {'turnId':'active'}
  return {'data':[{'id':'active','status':'completed','items':self.items}]}

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  (self.root/'account-binding.json').write_text(json.dumps({'fingerprint':'bound'}))
  self.job={'id':'b'*64,'action':'send_codex_message','args':{'threadId':'target','execution':'headless','message':'ACK'}}
  self.path=self.root/(self.job['id']+'.json')
  bridge.save(self.path,{'id':self.job['id'],'job':self.job,'created':int(time.time()*1000),'state':'claimed'})
  self.owner=FakeOwner();self.parent={'id':'a'*64,'job':{'args':{'threadId':'target'}},'turnId':'active'}
  self.patches=[patch.object(bridge,'JOURNAL',self.root),patch.object(bridge,'ROOT',self.root),patch.object(bridge,'fingerprint',return_value='bound')]
  for p in self.patches:p.start()
  self.steering=Steering(bridge,self.owner,self.parent)
 def tearDown(self):
  self.steering.close()
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def record(self):return json.loads(self.path.read_text())
 def test_accepted_is_not_received_and_same_id_not_steered_twice(self):
  self.steering.poll();self.steering.poll()
  r=self.record();self.assertFalse(r['targetReceived']);self.assertTrue(r['steerAccepted'])
  self.assertEqual(len(self.owner.calls),1);self.assertEqual(self.owner.calls[0][1]['expectedTurnId'],'active')
  self.owner.items=[{'type':'userMessage','content':[{'type':'text','text':'[dot-request:'+self.job['id']+'] ACK'}]},{'type':'agentMessage','text':'ACTUAL ACK'}]
  self.steering.finish();r=self.record();self.assertTrue(r['targetReceived']);self.assertEqual(r['state'],'completed')
 def test_missing_response_never_blindly_resends(self):
  self.owner.error=TimeoutError();self.steering.poll();self.steering.poll()
  self.assertEqual(self.record()['state'],'delivery_unknown');self.assertEqual(len(self.owner.calls),1)
 def test_explicit_rejection_is_terminal_and_never_starts_replacement(self):
  self.owner.error=bridge.RpcError({'code':-32600,'message':'no active turn'})
  self.steering.poll();self.steering.poll()
  self.assertEqual(self.record()['state'],'failed');self.assertEqual([m for m,_ in self.owner.calls],['turn/steer'])

if __name__=='__main__':unittest.main()
