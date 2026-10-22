import {subscriptionView,renewalPolicy} from './subscriptions';
import {env} from 'cloudflare:workers';
import {healthNotificationStatus,verifyHealthNotifications} from './health-alerts';
import {communicationGuide,recoveryForJob} from './communication';
import {noticeView,receiptLayers} from './receipts';
import {taskView} from './task-state';
import {waitForJob} from './wait';
// Open-source edition: single operator, no entitlement service.
import {isOperator} from './access';
export const VERSION='0.3.2+oss.1';
export function db(){if(!env.DB)throw new Error('Database unavailable');return env.DB;}
export async function hash(s:string){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))].map(b=>b.toString(16).padStart(2,'0')).join('');}
export const scope={deviceId:'mac',supported:'Enrolled Mac Codex local store: existing/future persisted chats, archived filter',unsupported:['cloud-only conversations','other devices not enrolled','ephemeral chats','independent historical per-thread account ownership verification','immediate steering into an external desktop-owned active turn'],permissions:'Metadata discovery; body reads and sends only for specifically user-authorized tasks; no bulk content scan',capabilities:{headless:true,desktopBrowser:false,desktopComputerUse:false,desktopApprovalUI:false,sameConnectionSteering:'upgraded bridge-owned active turns only',desktopOwnerRouting:'official_queue_fallback',externalActiveTurnSteering:false,queueAcceptedIsReceipt:false,writerOwnerInspection:false,writerWaitLimitMs:300000}};
export async function authorized(owner:string){
 // Bind to the already established owner, never to the first new visitor.
 let row=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind('owner').first<{value:string}>();
 if(!row){const old=await db().prepare('SELECT DISTINCT owner FROM jobs LIMIT 2').all<{owner:string}>();if(old.results.length!==1)throw new Error('Owner binding requires local enrollment');await db().prepare('INSERT OR IGNORE INTO bridge_settings(key,value) VALUES (?,?)').bind('owner',old.results[0].owner).run();row=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind('owner').first<{value:string}>();}
 if(!await isOperator(owner))throw new Error('Account is not enrolled on this device');
}
export async function status(owner?:string){
 const row=await db().prepare('SELECT seen FROM device WHERE id=?').bind('mac').first<{seen:number}>();const health=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind('health').first<{value:string}>();return {version:VERSION,online:!!row&&Date.now()-row.seen<30000,lastSeen:row?.seen??null,scope,health:health?JSON.parse(health.value):null,healthNotifications:await healthNotificationStatus(),communication:communicationGuide};
}
const requestId={type:'string',minLength:8,maxLength:100},threadId={type:'string',pattern:'^[0-9a-f-]{36}$'},cursor={type:'string'},limit={type:'integer',minimum:1,maximum:100};
function tool(name:string,description:string,properties:Record<string,unknown>,required:string[]=[]){return {name,description,annotations:{readOnlyHint:!['send_codex_message','send_dot_message','ack_codex_event','cancel_codex_queued_request','verify_codex_health_notifications'].includes(name),destructiveHint:name==='send_codex_message',idempotentHint:true,openWorldHint:name==='send_codex_message'},inputSchema:{type:'object',properties,required,additionalProperties:false}};}
export const tools=[
 tool('codex_access_status','Read only your own service access and Mac setup status. Self-hosted access requires configured operator authentication. Does not read conversations or send tasks.',{}),
 tool('codex_connection_status','Check enrolled scope, account health and actual execution limitations.',{}),
 tool('verify_codex_health_notifications','Only for user-authorized finite notification verification. Enqueue one clearly synthetic fault/recovery pair to the existing parent codex.delivery subscription. Requires fresh verified account health; never changes real health, starts a local turn, registers a webhook or changes recipients. Stable requestId never duplicates. Read both job results and require actual parent ACK.',{requestId:{...requestId,maxLength:70,pattern:'^[A-Za-z0-9._:-]+$'}},['requestId']),
 tool('list_codex_threads','Discover/search/page real local chat titles and IDs on the enrolled Mac. Call again for future chats. Metadata only. Returns a jobId; query codex_job_result. Cloud/other devices are explicitly unsupported.',{requestId,query:{type:'string',maxLength:200},cursor,limit,archived:{type:'boolean'}},['requestId']),
 tool('read_codex_thread','Read only the specifically requested discovered chat. Paginated text context; returns jobId.',{requestId,threadId,cursor,limit:{...limit,maximum:10}},['requestId','threadId']),
 tool('send_codex_message','Send a user-authorized task directly to a discovered chat. Idle writable chats start; an upgraded bridge-owned active turn receives turn/steer on its existing connection. On this upgraded Mac, desktop/external writer conflicts fall back to the official persistent queue; idle loaded desktop receipt is verified. Active external turns receive queued follow-up, not immediate steering. After five minutes without receipt, remove only matching owned pending queue items when the agent can reconnect; upstream queue has no TTL and late dispatch is possible. Never release another writer. Identical requestId is never resent. headless only: no desktop browser/computer-use/approval inheritance. Queued or steer accepted is NOT target receipt; inspect targetReceived and actual replies. Subscribe to codex.delivery.',{requestId,threadId,message:{type:'string',minLength:1,maxLength:12000},execution:{type:'string',enum:['headless','desktop_required']}},['requestId','threadId','message','execution']),
 tool('send_dot_message','Send a user-authorized message FROM a discovered Codex chat to dot through a codex.message event subscription. No relay chat. Requires active verified subscription; webhook receipt is not dot ACK. Source ID is checked, optional turn ID is caller-declared.',{requestId,sourceThreadId:threadId,sourceTurnId:{type:'string'},inReplyTo:{type:'string'},message:{type:'string',minLength:1,maxLength:12000}},['requestId','sourceThreadId','message']),
 tool('codex_job_result','Query by jobId or original requestId after disconnect. Shows target turnId, real replies, errors, delivery history and dot receipts. Never resend an unknown outcome. Large records are paginated with offset/limit.',{jobId:{type:'string'},requestId,offset:{type:'integer',minimum:0},limit:{type:'integer',minimum:1000,maximum:60000}}),
 tool('wait_codex_job','Read-only bounded wait for the original job. Returns running, approval/input required, unknown delivery, completion or failure with actual turn/reply evidence. Maximum 10 seconds; long work continues through the existing event subscription and later result query. Aborting or timing out this wait NEVER cancels the task or resends a message.',{jobId:{type:'string'},requestId,waitMs:{type:'integer',minimum:0,maximum:10000}}),
 tool('codex_notification_status','List subscription verification and recent event receipt/ACK evidence; secrets never returned.',{}),
 tool('ack_codex_event','Call when dot has actually read a delivered event and its job result. Records application ACK, distinct from webhook receipt. Does not send anything back automatically.',{eventId:{type:'string'},requestId},['eventId','requestId']),
 tool('cancel_codex_queued_request','Cancel only a cloud request not yet claimed by Mac. Never interrupts an executing target.',{requestId},['requestId'])
];
export function canonical(value:unknown):string{if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';if(value!==null&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical((value as Record<string,unknown>)[k])).join(',')+'}';return JSON.stringify(value);}
export async function jobResult(owner:string,args:Record<string,unknown>){
 const id=args.jobId??(typeof args.requestId==='string'?await hash(owner+'\0'+args.requestId):'');
 const row=await db().prepare('SELECT id,request_id,action,status,record,created,updated FROM bridge_jobs WHERE id=? AND owner=?').bind(id,owner).first();
 if(!row){const legacy=await db().prepare('SELECT id,status,result,created,updated FROM jobs WHERE id=? AND owner=?').bind(id,owner).first();if(!legacy)throw new Error('Job not found');return {...legacy,legacy:true,result:legacy.result?JSON.parse(String(legacy.result)):null};}
 const record=row.record?JSON.parse(String(row.record)):null;
 const notices=await db().prepare('SELECT e.id AS eventId,d.subscription AS subscriptionId,s.name AS eventName,s.status AS subscriptionStatus,s.expires AS subscriptionExpiresAt,d.status,d.attempt,d.next_attempt AS nextAttemptAt,d.receipt AS webhookReceivedAt,d.ack AS dotAcknowledgedAt,d.error FROM bridge_events e LEFT JOIN deliveries d ON d.event=e.id LEFT JOIN subscriptions s ON s.id=d.subscription WHERE e.job_id=? AND e.owner=?').bind(id,owner).all();
 const notificationViews=notices.results.map(n=>noticeView(n));
 const dotAck=notices.results.some(n=>n.dotAcknowledgedAt!=null),webhookReceipt=notices.results.some(n=>n.webhookReceivedAt!=null);
 const dotDelivery=dotAck?'dot_acknowledged':webhookReceipt?'webhook_received':'awaiting_event_ack';
 if(row.action==='send_dot_message'&&record?.result)record.result.dotReceipt=dotDelivery;
 const failedNotification=notificationViews.length>0&&notificationViews.every(n=>['permanent_failure','retry_exhausted'].includes(n.notificationState as string));
 const visibleStatus=row.action==='send_dot_message'&&row.status==='completed'&&!dotAck?(failedNotification?'notification_failed':'awaiting_dot'):row.status;
 const view=taskView(row.action,visibleStatus,record,dotAck);
 const envelope={jobId:row.id,requestId:row.request_id,status:visibleStatus,processingState:row.status,taskView:view,created:row.created,updated:row.updated,record,notifications:notificationViews,receiptLayers:receiptLayers(row.action,row.status,record,notices.results),recovery:recoveryForJob({action:row.action,status:row.status,request_id:row.request_id},record,notices.results)};
 const raw=JSON.stringify(envelope),offset=Math.max(0,Number(args.offset)||0),length=Math.min(60000,Math.max(1000,Number(args.limit)||60000));
 if(raw.length<=length&&offset===0)return envelope;
 return {jobId:id,requestId:row.request_id,status:visibleStatus,processingState:row.status,taskView:view,format:'json-text-pages',totalCharacters:raw.length,offset,data:raw.slice(offset,offset+length),nextOffset:offset+length<raw.length?offset+length:null};
}
export async function callTool(owner:string,name:string,args:Record<string,unknown>,signal?:AbortSignal){
 if(name==='wait_codex_job'){
  let accountCheck:Promise<void>|undefined;
  return {jobId:args.jobId,requestId:args.requestId,...await waitForJob(async()=>{
   await (accountCheck??=authorized(owner));
   return jobResult(owner,{jobId:args.jobId,requestId:args.requestId});
  },args.waitMs??5000,signal)};
 }
 await authorized(owner);
 if(name==='codex_connection_status')return status(owner);
 if(name==='verify_codex_health_notifications'){if(!await isOperator(owner))throw new Error('Personal notification probes are not available on a customer connection');return verifyHealthNotifications(owner,args.requestId);}
 if(name==='codex_job_result')return jobResult(owner,args);
 if(name==='codex_notification_status'){
  const subs=await db().prepare('SELECT id,name,status,error,expires,pending_expires,verify_until,verified_at,last_refresh_requested,last_refresh_completed,refresh_requests,refresh_successes,refresh_error FROM subscriptions WHERE owner=?').bind(owner).all();
  const events=await db().prepare('SELECT e.id,e.name,e.job_id,d.subscription AS subscriptionId,s.status AS subscriptionStatus,s.expires AS subscriptionExpiresAt,d.status,d.attempt,d.next_attempt AS nextAttemptAt,d.receipt,d.ack,d.receipt AS webhookReceivedAt,d.ack AS dotAcknowledgedAt,d.error FROM bridge_events e LEFT JOIN deliveries d ON e.id=d.event LEFT JOIN subscriptions s ON s.id=d.subscription WHERE e.owner=? ORDER BY e.seq DESC LIMIT 30').bind(owner).all();return {renewalPolicy,subscriptions:subs.results.map(s=>subscriptionView(s)),events:events.results.map(n=>noticeView(n)),meaning:'Subscription receipt and application ACK do not prove a visible chat message or a reply.'};
 }
 if(name==='ack_codex_event'){
  if(typeof args.requestId!=='string'||args.requestId.length<8||args.requestId.length>100)throw new Error('Invalid requestId');
  const ackKey='ack:'+await hash(owner+'\0'+args.requestId);
  const previous=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind(ackKey).first();
  if(previous&&previous.value!==args.eventId)throw new Error('requestId conflict');
  const e=await db().prepare('SELECT id FROM bridge_events WHERE id=? AND owner=?').bind(args.eventId,owner).first();if(!e)throw new Error('Event not found');
  await db().prepare('INSERT OR IGNORE INTO bridge_settings(key,value) VALUES (?,?)').bind(ackKey,args.eventId).run();
  const reserved=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind(ackKey).first();if(reserved?.value!==args.eventId)throw new Error('requestId conflict');
  const ack=await db().prepare("UPDATE deliveries SET ack=COALESCE(ack,?),status='dot_acknowledged' WHERE event=? AND receipt IS NOT NULL RETURNING id").bind(Date.now(),args.eventId).first();if(!ack)throw new Error('No verified webhook receipt; cannot assert dot received this event');return {eventId:args.eventId,acknowledged:true,meaning:'Explicit recipient tool call; see receipt row for end-to-end evidence'};
 }
 if(name==='cancel_codex_queued_request'){const id=await hash(owner+'\0'+args.requestId);const r=await db().prepare("UPDATE bridge_jobs SET status='cancelled',updated=? WHERE id=? AND owner=? AND status='queued' RETURNING id").bind(Date.now(),id,owner).first();return {cancelled:!!r,reason:r?'Not yet delivered':'Already claimed or terminal: not interrupted'};}
 if(!['list_codex_threads','read_codex_thread','send_codex_message','send_dot_message'].includes(name))throw new Error('Unknown tool');
 if(typeof args.requestId!=='string'||!/^.{8,100}$/.test(args.requestId))throw new Error('Invalid requestId');
 const request=Object.fromEntries(Object.entries(args).filter(([k])=>k!=='requestId'));
 if(name==='send_codex_message')request.execution=args.execution??'headless';
 const encoded=canonical(request);if(encoded.length>20000)throw new Error('Request too large');
 const id=await hash(owner+'\0'+args.requestId);
 const old=await db().prepare('SELECT * FROM bridge_jobs WHERE id=? AND owner=?').bind(id,owner).first();
 if(old){if(old.action!==name||old.args!==encoded)throw new Error('requestId conflict: immutable payload');return {jobId:id,status:old.status,reused:true};}
 const legacy=await db().prepare('SELECT id,status,action,thread,message FROM jobs WHERE id=? AND owner=?').bind(id,owner).first();if(legacy){if(legacy.action!==name||legacy.thread!==args.threadId||legacy.message!==(args.message??''))throw new Error('requestId conflict with legacy request');return {jobId:id,status:legacy.status,reused:true,legacy:true};}
 if(name!=='list_codex_threads'){
  const tid=name==='send_dot_message'?args.sourceThreadId:args.threadId;
  if(typeof tid!=='string'||! /^[0-9a-f-]{36}$/.test(tid))throw new Error('Invalid thread ID');
  const known=await db().prepare('SELECT id FROM discoveries WHERE owner=? AND thread=?').bind(owner,tid).first();
  const prior=known?null:await db().prepare('SELECT id FROM jobs WHERE owner=? AND thread=? LIMIT 1').bind(owner,tid).first();
  if(!known&&!prior)throw new Error('Discover this chat first with list_codex_threads; discovery does not authorize unrelated sensitive content');
 }
 if(name.startsWith('send_')&&(typeof args.message!=='string'||!args.message.trim()||args.message.length>12000))throw new Error('Invalid message');
 if(name==='send_dot_message'){
  const sub=await db().prepare("SELECT id FROM subscriptions WHERE owner=? AND name='codex.message' AND status='active' AND expires>? LIMIT 1").bind(owner,Date.now()).first();if(!sub)throw new Error('Dot must first subscribe to codex.message; no active verified notification route');
 }
 const now=Date.now();await db().prepare('INSERT OR IGNORE INTO bridge_jobs(id,owner,request_id,action,args,status,created,updated) VALUES (?,?,?,?,?,?,?,?)').bind(id,owner,args.requestId,name,encoded,'queued',now,now).run();
 const won=await db().prepare('SELECT action,args,status FROM bridge_jobs WHERE id=? AND owner=?').bind(id,owner).first();if(won?.action!==name||won?.args!==encoded)throw new Error('requestId conflict: concurrent payload');
 return {jobId:id,requestId:args.requestId,status:won.status,targetReceived:false,deviceOnline:(await status(owner)).online};
}
