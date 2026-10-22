type RecordView=Record<string,unknown>|null;
type StateText={title:string;detail:string};
const text:Record<string,StateText>={
 queued:{title:'Saved in cloud queue',detail:'The request is durable. The Mac has not claimed it yet.'},
 received:{title:'Claimed by the Mac',detail:'Device processing is separate from receipt in the target Codex turn.'},
 waiting_writer:{title:'Waiting for the existing writer',detail:'No other writer is released or interrupted. Inspect the recorded deadline and writer evidence.'},
 submitting:{title:'Delivery in progress',detail:'Submission or queue acceptance does not prove target receipt. Query this same request instead of resending.'},
 target_received:{title:'Received by the target turn',detail:'Target receipt is recorded. Execution and completion remain separate.'},
 executing:{title:'Running',detail:'The target turn is in progress. Its actual reply and final turn status are still pending.'},
 awaiting_approval:{title:'Awaiting approval',detail:'An approval wait was observed. This connection cannot provide the desktop approval UI.'},
 needs_input:{title:'Input required',detail:'A request for input or confirmation was observed. This connection does not fabricate an answer.'},
 needs_desktop:{title:'Desktop interaction unavailable',detail:'The standalone connection cannot supply the requested desktop tool, input or approval.'},
 delivery_unknown:{title:'Delivery outcome needs checking',detail:'Only query or reconcile the original request. A missing reply is not permission to resend.'},
 completed:{title:'Completed',detail:'Inspect the evidence below for the actual target turn, reply or recipient acknowledgement.'},
 failed:{title:'Failed',detail:'Inspect the recorded error. Do not automatically replay a request with an uncertain outcome.'},
 blocked_capability:{title:'Required tools unavailable',detail:'The requested execution environment is unavailable. No target task was started for this request.'},
 cancelled:{title:'Cancelled before delivery',detail:'Only the unclaimed cloud request was cancelled. No executing task was interrupted.'},
 awaiting_dot:{title:'Awaiting Dot acknowledgement',detail:'The notification is separate from target execution. A webhook receipt is not Dot acknowledgement.'},
 notification_failed:{title:'Notification failed',detail:'Delivery to Dot failed. This does not change the Codex task result.'},
};

export function taskView(action:unknown,state:unknown,record:RecordView,recipientAcknowledged=false){
 const status=String(state),base=text[status]??{title:'State unavailable',detail:'Inspect the raw processing state. No completion is inferred.'};
 const turnVerified=record?.targetReceived===true&&typeof record?.turnId==='string'&&record.turnId.length>0;
 const targetExecutionCompleted=action==='send_codex_message'&&status==='completed'&&turnVerified;
 const unverifiedCompletion=status==='completed'&&(action==='send_codex_message'&&!turnVerified||action==='send_dot_message'&&!recipientAcknowledged);
 const interaction=record?.interaction as Record<string,unknown>|undefined;
 const unavailable=status==='needs_desktop'&&interaction?.status==='unavailable';
 const intervention=['awaiting_approval','needs_input','needs_desktop','blocked_capability','delivery_unknown','notification_failed'].includes(status)||unverifiedCompletion;
 const terminal=['completed','failed','blocked_capability','cancelled','notification_failed'].includes(status);
 const replyAvailable=Array.isArray(record?.messages)&&record.messages.some(m=>typeof m==='string'&&m.length>0);
 const title=unverifiedCompletion?'Completion evidence missing':unavailable&&interaction?.kind==='approval'?'Approval unavailable on this connection':unavailable&&interaction?.kind==='input'?'Input unavailable on this connection':base.title;
 return {state:unverifiedCompletion?'completion_unverified':status,title,detail:base.detail,terminal,
  targetReceived:record?.targetReceived===true,targetTurnId:record?.turnId??null,turnVerified,
  targetExecutionCompleted,replyAvailable,needsAttention:intervention,canWait:!terminal&&!intervention,
  interaction:interaction??null,
  completionEvidence:targetExecutionCompleted?'target_turn':action==='send_dot_message'&&status==='completed'&&recipientAcknowledged?'recipient_ack':status==='completed'&&!['send_codex_message','send_dot_message'].includes(String(action))?'operation_result':null,
  nextAction:intervention?'Inspect this request and its required action; do not auto-resend.':terminal?'Inspect the result and receipt layers.':'Query this request or use the bounded wait tool; stopping a wait does not cancel the task.'};
}
