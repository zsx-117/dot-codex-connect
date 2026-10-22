import {db,hash} from '../../lib/bridge';
import {authenticateDevice,AccessError} from '../../lib/access';
import {callbacks,emitForJob} from '../../lib/events';
import {finishRefresh} from '../../lib/subscriptions';
import {observeHealth} from '../../lib/health-alerts';
type AgentRecord={id:string;revision:number;state:string;result?:{chats?:({id:string}&Record<string,unknown>)[]};[key:string]:unknown};
type AgentBody={op?:string;version?:number;health?:Record<string,unknown>;record?:AgentRecord;type?:string;id?:string;ok?:boolean;error?:string;code?:number;attempt?:number;verifyGeneration?:number};
export async function POST(req:Request){
 let device:Awaited<ReturnType<typeof authenticateDevice>>;
 try{device=await authenticateDevice(req);}catch(e){return Response.json({error:e instanceof AccessError?e.code:'device_authorization_failed'},{status:e instanceof AccessError?e.status:503});}
 let body:AgentBody;try{body=await req.json() as AgentBody;if(!body||Array.isArray(body))throw new Error();}catch{return Response.json({error:'Invalid JSON'},{status:400});}
 const now=Date.now();
 if(body.op==='heartbeat'){
  await db().prepare('INSERT INTO device(id,seen) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET seen=excluded.seen').bind('mac',now).run();
  const healthNotification=body.health?await observeHealth(body.health,now):null;
  if(body.health)await db().prepare('INSERT INTO bridge_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').bind('health',JSON.stringify(body.health)).run();
  return Response.json({ok:true,healthNotification});
 }
 if(body.op==='poll'){
  if(body.version!==2)return Response.json({job:null,upgradeRequired:true});
  const job=await db().prepare("UPDATE bridge_jobs SET status='received',updated=? WHERE id=(SELECT id FROM bridge_jobs WHERE status='queued' AND owner=? ORDER BY created LIMIT 1) AND status='queued' AND owner=? RETURNING id,action,args,request_id").bind(now,device.owner,device.owner).first();
  return Response.json({job:job?{id:job.id,action:job.action,args:JSON.parse(String(job.args)),requestId:job.request_id}:null});
 }
 if(body.op==='recover'){
  const rows=await db().prepare("SELECT id,action,args,request_id FROM bridge_jobs WHERE owner=? AND status NOT IN ('queued','completed','failed','blocked_capability','cancelled') ORDER BY created LIMIT 100").bind(device.owner).all();
  return Response.json({jobs:rows.results.map(j=>({id:j.id,action:j.action,args:JSON.parse(String(j.args)),requestId:j.request_id}))});
 }
 if(body.op==='sync'){
  const record=body.record;
  if(!record||typeof record.id!=='string'||!Number.isInteger(record.revision))return Response.json({error:'Invalid record'},{status:400});
  const states=['received','waiting_writer','submitting','target_received','executing','delivery_unknown','needs_desktop','awaiting_approval','needs_input','completed','failed','blocked_capability'];
  if(!states.includes(record.state))return Response.json({error:'Invalid state'},{status:400});
  const job=await db().prepare('SELECT * FROM bridge_jobs WHERE id=? AND owner=?').bind(record.id,device.owner).first();if(!job)return Response.json({error:'Unknown job'},{status:404});
  const clean={...record};delete clean.job;
  const raw=JSON.stringify(clean);if(raw.length>2000000)return Response.json({error:'Result too large'},{status:413});
  // State sync is monotonic and idempotent across retries and restarts.
  await db().prepare('UPDATE bridge_jobs SET status=?,record=?,revision=?,updated=? WHERE id=? AND owner=? AND revision<?').bind(record.state,raw,record.revision,now,record.id,device.owner,record.revision).run();
  if(record.state==='completed'&&job.action==='list_codex_threads'){
   for(const chat of record.result?.chats??[]){const id=await hash(job.owner+'\0'+chat.id);await db().prepare('INSERT INTO discoveries(id,owner,thread,metadata,updated) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata,updated=excluded.updated').bind(id,job.owner,chat.id,JSON.stringify(chat),now).run();}
  }
  const latest=await db().prepare('SELECT revision FROM bridge_jobs WHERE id=? AND owner=?').bind(record.id,device.owner).first();
  if(latest?.revision===record.revision)await emitForJob(job,record);
  return Response.json({ok:true,revision:latest?.revision});
 }
 if(body.op==='callback')return Response.json({task:await callbacks(device.owner)});
 if(body.op==='callback_result'){
  if(body.type==='verify'){
   if(typeof body.ok!=='boolean'||!Number.isInteger(body.verifyGeneration)||!body.id)return Response.json({error:'Invalid verification generation'},{status:400});
   if(!await db().prepare('SELECT id FROM subscriptions WHERE id=? AND owner=?').bind(body.id,device.owner).first())return Response.json({error:'Unknown subscription'},{status:404});
   await finishRefresh(body.id,body.verifyGeneration!,body.ok,body.ok?null:String(body.error??'challenge_failed').slice(0,100),now);
  }else{
   if(typeof body.ok!=='boolean'||typeof body.attempt!=='number'||!Number.isInteger(body.attempt)||body.attempt<0||body.attempt>=8)return Response.json({error:'Invalid callback attempt'},{status:400});
   if(!await db().prepare('SELECT d.id FROM deliveries d JOIN subscriptions s ON s.id=d.subscription WHERE d.id=? AND s.owner=?').bind(body.id,device.owner).first())return Response.json({error:'Unknown delivery'},{status:404});
   const stopped=body.code===410||body.code===413;
   const nextStatus=body.ok?'webhook_received':stopped?'permanent_failure':body.attempt>=7?'retry_exhausted':'retry';
   // A late success still proves receipt. Stale failures cannot undo newer attempts,
   // a successful receipt, or an application ACK. The reported attempt is zero-based.
   const updated=await db().prepare("UPDATE deliveries SET status=?,receipt=CASE WHEN ? THEN ? ELSE receipt END,error=?,next_attempt=? WHERE id=? AND ack IS NULL AND receipt IS NULL AND ((?=1 AND attempt>=?) OR (?=0 AND attempt=?)) RETURNING id").bind(nextStatus,body.ok?1:0,now,body.ok?null:String(body.error??body.code??'delivery_failed').slice(0,100),nextStatus==='retry'?now+Math.min(3600000,Math.pow(2,body.attempt)*10000):0,body.id,body.ok?1:0,body.attempt+1,body.ok?1:0,body.attempt+1).first();
   if(updated&&body.code===410&&!body.ok)await db().prepare("UPDATE subscriptions SET status='receiver_gone',secret='',previous_secret=NULL,rotation_until=NULL,pending_secret=NULL,pending_expires=NULL,verify_until=NULL,verify_generation=verify_generation+1 WHERE id=(SELECT subscription FROM deliveries WHERE id=?)").bind(body.id).run();
  }
  return Response.json({ok:true});
 }
 return Response.json({error:'Unknown operation'},{status:400});
}
