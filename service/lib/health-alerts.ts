import {db,hash} from './bridge';

// Open-source preparation: personal notification route removed; disabled by default.
export const HEALTH_PARENT_THREAD='';
export const HEALTH_SUBSCRIPTION='';
const MONITOR_KEY='health-notifications:v1';
const HEALTH_FRESH_MS=75000;
type HealthState='unobserved'|'healthy'|'fault';
type Monitor={state:HealthState;transitionId:string;code:string|null;checkedAt:number;lastObservedAt:number;lastJobId?:string;lastEventId?:string};
type Observation={state:'healthy'|'fault';code:string;accountVerified:boolean;checkedAt:number;requiresUserAction:boolean};
const safeCodes=new Set(['STARTING','HEALTHY','HEALTH_CHECK_STALE','HEALTH_PROBE_FAILED','HEALTH_PROBE_TIMEOUT','HEALTH_PROBE_INVALID_RESPONSE','APP_SERVER_TIMEOUT','APP_SERVER_DISCONNECTED','APP_SERVER_AUTH_REJECTED','APP_SERVER_RPC_REJECTED','CODEX_EXECUTABLE_NOT_FOUND','CODEX_EXECUTABLE_UNUSABLE','CODEX_EXECUTABLE_OVERRIDE_INVALID','ACCOUNT_MISMATCH','ACCOUNT_BINDING_MISMATCH','ACCOUNT_UNVERIFIED','ACCOUNT_BINDING_MISSING','LOGIN_REQUIRED','FILESYSTEM_ACCESS_DENIED','REQUIRED_LOCAL_FILE_MISSING','SERVICE_AUTH_REJECTED','SERVICE_TEMPORARILY_UNAVAILABLE','SERVICE_REQUEST_REJECTED','DNS_RESOLUTION_FAILED','TLS_VERIFICATION_FAILED','CLOUD_TIMEOUT','CLOUD_DISCONNECTED','CLOUD_TRANSPORT_ERROR','UNCLASSIFIED_ERROR']);

export function healthObservation(input:unknown,now:number):Observation{
 const health=input&&typeof input==='object'&&!Array.isArray(input)?input as Record<string,unknown>:{};
 const cloudError=health.cloudTransportError&&typeof health.cloudTransportError==='object'?health.cloudTransportError as Record<string,unknown>:null;
 const reportedAt=typeof health.checkedAt==='number'&&Number.isFinite(health.checkedAt)?health.checkedAt:now;
 const checkedAt=reportedAt-now>1000?now:reportedAt;
 const accountVerified=health.accountVerified===true;
 let code='HEALTH_REPORT_INVALID';
 if(accountVerified){
  code=typeof health.checkedAt!=='number'||!Number.isFinite(health.checkedAt)||now-checkedAt>HEALTH_FRESH_MS||reportedAt-now>1000?'HEALTH_CHECK_STALE':'HEALTHY';
  if(code==='HEALTHY'&&cloudError){
   const reported=cloudError.code;
   code=typeof reported==='string'&&safeCodes.has(reported)&&reported!=='HEALTHY'?reported:'CLOUD_TRANSPORT_ERROR';
  }
 }else if(health?.accountVerified===false){
  code=typeof health.code==='string'&&safeCodes.has(health.code)&&health.code!=='HEALTHY'?health.code:'ACCOUNT_UNVERIFIED';
 }
 return {state:code==='HEALTHY'?'healthy':'fault',code,accountVerified,checkedAt,requiresUserAction:health.requiresUserAction===true||cloudError?.requiresUserAction===true};
}

async function notification(owner:string,requestId:string,observation:Observation,phase:'fault'|'recovered',previousCode:string|null,now:number,synthetic=false){
 const id=await hash(owner+'\0'+requestId);
 const eventId=await hash(id+'\0completed');
 const args=JSON.stringify({threadId:HEALTH_PARENT_THREAD,notificationKind:'bridge_health',synthetic});
 const message=synthetic
  ?`[告警路径自检] ${phase==='fault'?'模拟故障':'模拟恢复'}；这不是实际桥接故障或恢复，也不启动本机任务。`
  :phase==='fault'?'桥接健康检查出现故障，自动投递继续受账号校验门禁约束。':'桥接健康检查已恢复；这不代表桌面对话 writer 路由或目标执行已恢复。';
 const record={id,revision:1,state:'completed',targetReceived:false,result:{kind:synthetic?'bridge_health_notification_probe':'bridge_health_transition',transition:phase,synthetic,code:observation.code,previousFaultCode:phase==='recovered'?previousCode:null,requiresUserAction:observation.requiresUserAction,accountVerified:synthetic?null:observation.accountVerified,observedAt:new Date(now).toISOString(),source:synthetic?'owner_authorized_notification_probe':'authenticated_device_heartbeat',parentThreadId:HEALTH_PARENT_THREAD,localAccountGatePreserved:true,fullOfflineDetection:false,message}};
 const payload={jobId:id,requestId,threadId:HEALTH_PARENT_THREAD,status:'completed'};
 return {id,eventId,requestId,args,record:JSON.stringify(record),payload:JSON.stringify(payload)};
}

export async function observeHealth(health:unknown,now=Date.now()){
 const ownerRow=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind('owner').first<{value:string}>();
 // Never enroll an owner or infer a new recipient from a heartbeat.
 if(!ownerRow)return {recorded:false,reason:'existing_owner_binding_missing'};
 const initial:Monitor={state:'unobserved',transitionId:'initial',code:null,checkedAt:0,lastObservedAt:0};
 await db().prepare('INSERT OR IGNORE INTO bridge_settings(key,value) VALUES (?,?)').bind(MONITOR_KEY,JSON.stringify(initial)).run();
 const observation=healthObservation(health,now);
 for(let attempt=0;attempt<3;attempt++){
  const row=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind(MONITOR_KEY).first<{value:string}>();
  if(!row)throw new Error('Health notification monitor unavailable');
  const previous=JSON.parse(row.value) as Monitor;
  if(observation.checkedAt<previous.checkedAt)return {recorded:false,reason:'older_health_observation'};
  const changed=previous.state!==observation.state;
  const emit=changed&&(observation.state==='fault'||previous.state==='fault');
  const transitionId=changed?await hash(previous.transitionId+'\0'+observation.state+'\0'+now):previous.transitionId;
  const next:Monitor={...previous,state:observation.state,transitionId,code:changed?observation.code:previous.code,checkedAt:observation.checkedAt,lastObservedAt:now};
  const notice=emit?await notification(ownerRow.value,'health-transition-'+transitionId,observation,observation.state==='fault'?'fault':'recovered',previous.code,now):null;
  const statements=[];
  if(notice){
   next.lastJobId=notice.id;next.lastEventId=notice.eventId;
   statements.push(db().prepare("INSERT OR IGNORE INTO bridge_jobs(id,owner,request_id,action,args,status,record,revision,created,updated) SELECT ?,?,?,'bridge_health',?,'completed',?,1,?,? WHERE EXISTS (SELECT 1 FROM bridge_settings WHERE key=? AND value=?)").bind(notice.id,ownerRow.value,notice.requestId,notice.args,notice.record,now,now,MONITOR_KEY,row.value));
   statements.push(db().prepare("INSERT OR IGNORE INTO bridge_events(id,owner,name,job_id,payload,created) SELECT ?,?,'codex.delivery',?,?,? WHERE EXISTS (SELECT 1 FROM bridge_settings WHERE key=? AND value=?)").bind(notice.eventId,ownerRow.value,notice.id,notice.payload,now,MONITOR_KEY,row.value));
  }
  statements.push(db().prepare('UPDATE bridge_settings SET value=? WHERE key=? AND value=?').bind(JSON.stringify(next),MONITOR_KEY,row.value));
  // One transaction reserves the transition and its durable job/event together.
  const result=await db().batch(statements);
  if(result.at(-1)?.meta.changes)return {recorded:true,transition:notice?(observation.state==='fault'?'fault':'recovered'):null,...(notice?{jobId:notice.id,eventId:notice.eventId}:{})};
 }
 throw new Error('Concurrent health update; retry the heartbeat');
}

export async function healthNotificationStatus(){
 const row=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind(MONITOR_KEY).first<{value:string}>();
 return {enabled:true,parentThreadId:HEALTH_PARENT_THREAD,subscriptionId:HEALTH_SUBSCRIPTION,event:'codex.delivery',accountGatePreserved:true,dispatchRequiresFreshLocalAccount:true,fullOfflineDetection:false,delivery:'Existing Mac dispatcher; account failures remain queued until verification recovers.',current:row?JSON.parse(row.value):null};
}

export async function verifyHealthNotifications(owner:string,requestId:unknown){
 if(typeof requestId!=='string'||! /^[A-Za-z0-9._:-]{8,70}$/.test(requestId))throw new Error('Invalid probe requestId');
 const healthRow=await db().prepare('SELECT value FROM bridge_settings WHERE key=?').bind('health').first<{value:string}>();
 const now=Date.now();
 const health=healthRow?JSON.parse(healthRow.value):{};
 if(healthObservation(health,now).state!=='healthy')throw new Error('Fresh verified account health required for notification probe');
 const sub=await db().prepare("SELECT id FROM subscriptions WHERE id=? AND owner=? AND name='codex.delivery' AND status='active' AND expires>?").bind(HEALTH_SUBSCRIPTION,owner,now).first();
 if(!sub)throw new Error('Original parent notification route is not active and verified');
 const notices=[];
 for(const phase of ['fault','recovered'] as const){
  const observation:Observation={state:phase==='fault'?'fault':'healthy',code:phase==='fault'?'HEALTH_PROBE_TIMEOUT':'HEALTHY',accountVerified:phase!=='fault',checkedAt:now,requiresUserAction:false};
  notices.push(await notification(owner,'health-probe-'+requestId+'-'+phase,observation,phase,phase==='recovered'?'HEALTH_PROBE_TIMEOUT':null,now,true));
 }
 const statements=[];
 for(const notice of notices){
  const old=await db().prepare('SELECT action,args FROM bridge_jobs WHERE id=? AND owner=?').bind(notice.id,owner).first();
  if(old&&(old.action!=='bridge_health'||old.args!==notice.args))throw new Error('Probe requestId conflict');
  statements.push(db().prepare("INSERT OR IGNORE INTO bridge_jobs(id,owner,request_id,action,args,status,record,revision,created,updated) VALUES (?,?,?,'bridge_health',?,'completed',?,1,?,?)").bind(notice.id,owner,notice.requestId,notice.args,notice.record,now,now));
  statements.push(db().prepare("INSERT OR IGNORE INTO bridge_events(id,owner,name,job_id,payload,created) VALUES (?,?,'codex.delivery',?,?,?)").bind(notice.eventId,owner,notice.id,notice.payload,now));
 }
 await db().batch(statements);
 return {synthetic:true,actualHealthUnchanged:true,localTargetStarted:false,parentThreadId:HEALTH_PARENT_THREAD,notifications:notices.map((n,i)=>({transition:i===0?'fault':'recovered',jobId:n.id,eventId:n.eventId,requestId:n.requestId})),meaning:'Read each job and verify webhook receipt plus parent ACK; queue creation is not notification delivery.'};
}
