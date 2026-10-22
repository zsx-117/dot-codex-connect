import assert from 'node:assert/strict';
import {test} from 'node:test';
import {taskView} from '../lib/task-state.ts';
import {waitForJob} from '../lib/wait.ts';
import {receiptLayers} from '../lib/receipts.ts';

const received={targetReceived:true,turnId:'actual-fixture-turn',messages:['ACTUAL FIXTURE REPLY']};
test('Acceptance, queue storage and webhook receipt are never execution completion',()=>{
 for(const state of ['queued','received','waiting_writer','submitting','target_received','executing']){
  assert.equal(taskView('send_codex_message',state,{...received,queueAccepted:true,steerAccepted:true}).targetExecutionCompleted,false,state);
 }
 assert.equal(taskView('send_codex_message','completed',null).state,'completion_unverified');
 assert.equal(taskView('send_codex_message','completed',{turnId:'declared-only'}).targetExecutionCompleted,false);
 assert.equal(taskView('send_codex_message','completed',received).targetExecutionCompleted,true);
 assert.equal(receiptLayers('send_codex_message','submitting',{},[{webhookReceivedAt:1}]).targetExecutionCompleted,false);
 assert.equal(taskView('send_dot_message','completed',null).completionEvidence,null);
 assert.equal(taskView('send_dot_message','completed',null,true).completionEvidence,'recipient_ack');
});
test('Approval and input waits are separate from unsupported interactions and terminal results',()=>{
 for(const state of ['awaiting_approval','needs_input','delivery_unknown','blocked_capability'])assert.equal(taskView('send_codex_message',state,received).needsAttention,true);
 const approval=taskView('send_codex_message','needs_desktop',{...received,interaction:{kind:'approval',status:'unavailable'}});
 assert.equal(approval.title,'Approval unavailable on this connection');assert.equal(approval.canWait,false);
 assert.equal(taskView('send_codex_message','failed',received).targetExecutionCompleted,false);
 assert.equal(taskView('send_codex_message','completed',{...received,interaction:{kind:'desktop_tool',status:'unavailable'}}).completionEvidence,'target_turn');
});
test('A bounded wait times out without changing or cancelling the task',async()=>{
 let reads=0;const record=Object.freeze({jobId:'fixture-job',status:'executing',taskView:taskView('send_codex_message','executing',received)});
 const result=await waitForJob(async()=>{reads++;return record;},15);
 assert.equal(result.wait.state,'still_pending');assert.equal(result.wait.taskUnaffected,true);assert.ok(reads>=1);
 assert.equal(record.status,'executing');assert.equal(record.taskView.targetExecutionCompleted,false);
});
test('Disconnect/cancellation ends only the wait, and the same job can later report its reply',async()=>{
 const controller=new AbortController();let reads=0;
 const running={jobId:'fixture-job',status:'executing',taskView:taskView('send_codex_message','executing',received)};
 const wait=waitForJob(async()=>{reads++;return running;},10000,controller.signal);
 setTimeout(()=>controller.abort(),10);
 const result=await wait;assert.equal(result.wait.state,'wait_cancelled');assert.equal(reads,1);assert.equal(running.status,'executing');
 const final={...running,status:'completed',record:received,taskView:taskView('send_codex_message','completed',received)};
 const recovered=await waitForJob(async()=>final,0);
 assert.equal(recovered.jobId,result.jobId);assert.deepEqual(recovered.record.messages,['ACTUAL FIXTURE REPLY']);assert.equal(recovered.wait.state,'state_available');
});
test('A wait returns actionable input/approval/unknown states without spinning',async()=>{
 for(const status of ['awaiting_approval','needs_input','needs_desktop','delivery_unknown','failed']){
  let reads=0;const value={status,taskView:taskView('send_codex_message',status,received)};
  const result=await waitForJob(async()=>{reads++;return value;},10000);assert.equal(reads,1);assert.equal(result.wait.state,'state_available');
 }
 for(const waitMs of [-1,1.5,10001,'5000'])await assert.rejects(waitForJob(async()=>({}),waitMs),/integer/);
});
test('Stopping a wait interrupts a blocked lookup without touching the task',async()=>{
 const controller=new AbortController();let resolveLookup;
 const running=Object.freeze({status:'executing',taskView:{canWait:true}});
 const started=performance.now();
 const waiting=waitForJob(()=>new Promise(resolve=>{resolveLookup=resolve;}),10000,controller.signal);
 setTimeout(()=>controller.abort(),10);
 const value=await waiting;
 assert.equal(value.wait.state,'wait_cancelled');assert.equal(value.wait.resultAvailable,false);
 assert.equal(value.wait.lookupPending,true);assert.ok(performance.now()-started<250);
 assert.equal(running.status,'executing');resolveLookup(running);
});
test('Lookup latency is inside the wait deadline and late errors are handled',async()=>{
 let rejectLookup,reads=0;const started=performance.now();
 const value=await waitForJob(()=>{reads++;return new Promise((_,reject)=>{rejectLookup=reject;});},30);
 assert.equal(value.wait.state,'still_pending');assert.equal(value.wait.resultAvailable,false);
 assert.equal(value.wait.taskUnaffected,true);assert.equal(reads,1);
 assert.ok(performance.now()-started<250);rejectLookup(new Error('late isolated lookup error'));
 await new Promise(resolve=>setTimeout(resolve,0));
});
test('An already cancelled wait does not even start a lookup',async()=>{
 const controller=new AbortController();controller.abort();
 const value=await waitForJob(async()=>{assert.fail('cancelled wait must not query');},10000,controller.signal);
 assert.equal(value.wait.state,'wait_cancelled');
});
