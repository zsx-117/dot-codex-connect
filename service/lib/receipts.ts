type Notice={status?:unknown;webhookReceivedAt?:unknown;dotAcknowledgedAt?:unknown;attempt?:unknown;nextAttemptAt?:unknown;subscriptionStatus?:unknown;subscriptionExpiresAt?:unknown;[key:string]:unknown};
export function noticeView(n:Notice,now=Date.now()){
 const receipt=n.webhookReceivedAt!=null,ack=n.dotAcknowledgedAt!=null;
 const exhausted=!receipt&&!ack&&Number(n.attempt)>=8&&Number(n.nextAttemptAt)<=now;
 const paused=!receipt&&!ack&&(n.subscriptionStatus!=='active'||Number(n.subscriptionExpiresAt)<=now);
 const state=ack?'recipient_acknowledged':receipt?'webhook_received':n.status==='permanent_failure'?'permanent_failure':n.status==='retry_exhausted'||exhausted?'retry_exhausted':paused?'subscription_unavailable':n.status??'not_dispatched';
 return {...n,notificationState:state,attemptsRemaining:Math.max(0,8-(Number(n.attempt)||0)),automaticRetry:(state==='pending'||state==='retry')&&Number(n.attempt)<8,visibleChatMessageVerified:null};
}
export function receiptLayers(action:unknown,state:unknown,record:Record<string,unknown>|null,notices:Notice[]){
 return {transport:action==='send_dot_message'?'codex.message webhook subscription':action==='send_codex_message'?'local App Server':'non-message operation',targetReceived:record?.targetReceived===true,targetTurnId:record?.turnId??null,targetExecutionCompleted:action==='send_codex_message'&&state==='completed'&&record?.targetReceived===true&&typeof record?.turnId==='string'&&record.turnId.length>0,taskState:state,webhookReceived:notices.some(n=>n.webhookReceivedAt!=null),recipientAcknowledged:notices.some(n=>n.dotAcknowledgedAt!=null),visibleChatMessageVerified:null,replyTextAvailable:action==='send_codex_message'&&Array.isArray(record?.messages)&&record.messages.length>0,meaning:'Application ACK is not proof of a visible chat message or an actual reply. Inspect target turn and reply text separately.'};
}
