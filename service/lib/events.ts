import {authorized,canonical,db,hash} from './bridge';
import {beginRefresh,finishRefresh} from './subscriptions';
import {HEALTH_SUBSCRIPTION} from './health-alerts';
export const eventDefinitions=['codex.delivery','codex.message'].map(name=>({name,description:name==='codex.delivery'?'Terminal delivery result for requested Codex jobs and sanitized bridge health fault/recovery notices. Health notices never start a target turn. Read codex_job_result, distinguish synthetic probes, and ACK the event; a callback alone is not execution success.':'User-authorized message from a Codex chat to dot. Read the job for text and origin, then ACK. Do not automatically send replies without the user-authorized task.',delivery:['webhook'],inputSchema:{type:'object',properties:{},additionalProperties:false},payloadSchema:{type:'object',properties:{jobId:{type:'string'},requestId:{type:'string'},threadId:{type:'string'},status:{type:'string'}},required:['jobId','requestId','threadId','status'],additionalProperties:false}}));
export async function eventMethod(owner:string,method:string,p:Record<string,unknown>){
 await authorized(owner);
 if(method==='events/list')return {events:eventDefinitions};
 if(!eventDefinitions.some(e=>e.name===p.name)||canonical(p.arguments??{})!=='{}')throw new Error('Invalid event or filters');
 const d=p.delivery as {mode?:string;url?:string;secret?:string}|undefined;
 if(d?.mode!=='webhook'||typeof d.url!=='string')throw new Error('Webhook delivery required');
 const u=new URL(d.url);if(u.protocol!=='https:'||u.username||u.password||u.port&&u.port!=='443'||u.hash)throw new Error('Invalid HTTPS callback');
 const id=await hash(owner+'\0'+d.url+'\0'+p.name+'\0{}');
 if(method==='events/unsubscribe'){
  await db().prepare("UPDATE subscriptions SET status='unsubscribed',secret='',previous_secret=NULL,rotation_until=NULL,pending_secret=NULL,pending_expires=NULL,verify_until=NULL,verify_generation=verify_generation+1 WHERE id=? AND owner=?").bind(id,owner).run();return {};
 }
 if(method!=='events/subscribe')throw new Error('Unsupported event method');
 if(typeof d.secret!=='string'||!/^whsec_[A-Za-z0-9+/]+={0,2}$/.test(d.secret))throw new Error('Invalid signing secret');
 let bytes;try{bytes=atob(d.secret.slice(6));}catch{throw new Error('Invalid signing key');}if(bytes.length<24||bytes.length>64)throw new Error('Invalid signing key length');
 const request=await beginRefresh(owner,id,String(p.name),d.url,d.secret,p.ttlMs);
 const response=()=>({id,refreshBefore:new Date(request.expires).toISOString(),cursor:null,truncated:p.cursor!=null});
 if(request.complete)return response();
 for(let i=0;i<20;i++){
  const row=await db().prepare('SELECT verify_generation,pending_expires,refresh_error,status FROM subscriptions WHERE id=? AND owner=?').bind(id,owner).first();
  if(row?.verify_generation!==request.generation)throw new Error('CallbackEndpointError: refresh_superseded');
  if(row?.pending_expires==null){
   if(row?.status==='active'&&!row.refresh_error)return response();
   throw new Error('CallbackEndpointError: '+(row?.refresh_error??'verification_failed'));
  }
  await new Promise(r=>setTimeout(r,1000));
 }
 await finishRefresh(id,request.generation!,false,'timeout');
 throw new Error('CallbackEndpointError: timeout');
}
export async function emitForJob(job:Record<string,unknown>,record:Record<string,unknown>){
 const name=job.action==='send_dot_message'?'codex.message':'codex.delivery';
 if(typeof job.action!=='string'||!['send_codex_message','send_dot_message'].includes(job.action))return;
 if(typeof record.state!=='string'||!['completed','failed','blocked_capability'].includes(record.state))return;
 const args=JSON.parse(String(job.args));const id=await hash(job.id+'\0'+record.state);
 const payload={jobId:job.id,requestId:job.request_id,threadId:args.threadId??args.sourceThreadId??'',status:record.state};
 await db().prepare('INSERT OR IGNORE INTO bridge_events(id,owner,name,job_id,payload,created) VALUES (?,?,?,?,?,?)').bind(id,job.owner,name,job.id,JSON.stringify(payload),Date.now()).run();
}
export async function callbacks(owner?:string){
 owner??=(await db().prepare("SELECT value FROM bridge_settings WHERE key='owner'").first<{value:string}>())?.value;
 if(!owner)return null;
 const now=Date.now();
 // An exhausted lease is terminal, not an endlessly displayed retry.
 await db().prepare("UPDATE deliveries SET status='retry_exhausted' WHERE status IN ('pending','retry') AND attempt>=8 AND next_attempt<=? AND receipt IS NULL AND ack IS NULL").bind(now).run();
 await db().prepare('UPDATE subscriptions SET previous_secret=NULL,rotation_until=NULL WHERE rotation_until<?').bind(now).run();
 await db().prepare("UPDATE subscriptions SET pending_secret=NULL,pending_expires=NULL,verify_until=NULL,refresh_error='timeout',status=CASE WHEN status='active' THEN status ELSE 'verification_failed' END WHERE pending_expires IS NOT NULL AND verify_until<=?").bind(now).run();
 const verify=await db().prepare("SELECT id,url,pending_secret AS secret,verify_generation AS verifyGeneration FROM subscriptions WHERE pending_expires>? AND verify_until>? AND owner=? LIMIT 1").bind(now,now,owner).first();
 if(verify)return {type:'verify',...verify};
 // Durable outbox. Events survive missing/expired subscriptions; future subscription picks them up.
 await db().prepare("INSERT OR IGNORE INTO deliveries(id,subscription,event,status) SELECT s.id||':'||e.id,s.id,e.id,'pending' FROM subscriptions s JOIN bridge_events e ON s.owner=e.owner AND s.name=e.name LEFT JOIN bridge_jobs j ON j.id=e.job_id WHERE s.status='active' AND s.expires>? AND s.owner=? AND (j.action IS NULL OR j.action!='bridge_health' OR s.id=?)").bind(now,owner,HEALTH_SUBSCRIPTION).run();
 const task=await db().prepare("SELECT d.id,d.attempt,s.id AS subscriptionId,s.url,s.secret,s.previous_secret,s.rotation_until,e.id AS eventId,e.name,e.payload,e.created FROM deliveries d JOIN subscriptions s ON s.id=d.subscription JOIN bridge_events e ON e.id=d.event LEFT JOIN bridge_jobs j ON j.id=e.job_id WHERE d.status IN ('pending','retry') AND d.receipt IS NULL AND d.ack IS NULL AND d.next_attempt<=? AND d.attempt<8 AND s.status='active' AND s.expires>? AND s.owner=? AND (j.action IS NULL OR j.action!='bridge_health' OR s.id=?) ORDER BY e.seq LIMIT 1").bind(now,now,owner,HEALTH_SUBSCRIPTION).first();
 if(!task)return null;
 // A competing poll must not claim the same event/attempt twice.
 const claimed=await db().prepare("UPDATE deliveries SET next_attempt=?,attempt=attempt+1 WHERE id=? AND attempt=? AND next_attempt<=? AND status IN ('pending','retry') AND receipt IS NULL AND ack IS NULL RETURNING id").bind(now+60000,task.id,task.attempt,now).first();
 return claimed?{type:'event',...task}:null;
}
