import assert from 'node:assert/strict';
import {communicationGuide,recoveryForJob} from '../lib/communication.ts';
const row={action:'send_codex_message',status:'failed',request_id:'same-logical-request'};
const unsent={targetReceived:false,error:{code:'WRITER_WAIT_EXPIRED'}};
assert.equal(recoveryForJob(row,unsent,[]).decision,'alternative_route_requires_verification');
for(const proof of [{startIntent:true},{targetReceived:true},{turnId:'actual-turn'}]){
 const r=recoveryForJob(row,{...unsent,...proof},[]);
 assert.equal(r.decision,'reconcile_only');assert.equal(r.automaticAlternateDispatch,false);
}
for(const state of ['submitting','delivery_unknown','executing','target_received','completed','needs_desktop','awaiting_approval','needs_input'])assert.equal(recoveryForJob({...row,status:state},null,[]).decision,'reconcile_only');
assert.equal(recoveryForJob({...row,status:'queued'},null,[]).decision,'do_not_race_queue');
assert.equal(recoveryForJob({...row,status:'waiting_writer'},unsent,[]).decision,'bounded_wait_or_inspect');
assert.equal(recoveryForJob(row,{targetReceived:false,error:{code:'APPROVAL_DENIED'}},[]).decision,'bounded_wait_or_inspect');
const dot={action:'send_dot_message',status:'completed'};
assert.equal(recoveryForJob(dot,null,[{webhookReceivedAt:1}]).decision,'wait_for_dot_ack');
assert.equal(recoveryForJob(dot,null,[{dotAcknowledgedAt:2}]).decision,'recipient_acknowledged');
assert.equal(recoveryForJob({action:'bridge_health',status:'completed'},{targetReceived:false},[]).decision,'inspect_result');
assert.equal(communicationGuide.layers.length,7);
assert.ok(communicationGuide.relayBoundary.includes('cannot execute native desktop tools'));
console.log('PASS route guidance: uncertain delivery, competing queues, approval rejection, health events and webhook receipt never authorize alternate dispatch');
