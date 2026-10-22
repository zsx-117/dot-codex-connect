import {db} from './bridge';
export const renewalPolicy={initiator:'ChatGPT MCP Events runtime',defaultLifetimeMs:86400000,verificationCacheMs:600000,verificationDeadlineMs:20000,serverSelfExtends:false,expiresStopsDelivery:true};
export async function beginRefresh(owner:string,id:string,name:string,url:string,secret:string,ttl:unknown,now=Date.now()){
 if(ttl!==undefined&&ttl!==null&&(typeof ttl!=='number'||!Number.isFinite(ttl)||ttl<=0))throw new Error('Invalid lifetime');
 // A null lifetime request is deliberately granted a finite lifetime, as allowed by MCP Events.
 const expires=now+Math.min(86400000,typeof ttl==='number'?ttl:86400000);
 await db().prepare("INSERT OR IGNORE INTO subscriptions(id,owner,name,args,url,secret,status,expires,created) VALUES (?,?,?,'{}',?,'','verifying',0,?)").bind(id,owner,name,url,now).run();
 const cached=await db().prepare("UPDATE subscriptions SET expires=?,last_refresh_requested=?,last_refresh_completed=?,refresh_requests=refresh_requests+1,refresh_successes=refresh_successes+1,refresh_error=NULL WHERE id=? AND owner=? AND status='active' AND expires>? AND secret=? AND verified_at>=? AND pending_expires IS NULL RETURNING expires").bind(expires,now,now,id,owner,now,secret,now-renewalPolicy.verificationCacheMs).first();
 if(cached)return {expires:Number(cached.expires),generation:null,complete:true};
 // Stage the candidate without changing the existing route or key. Old authorization
 // expires on its original deadline even if the replacement challenge is still pending.
 const staged=await db().prepare("UPDATE subscriptions SET pending_secret=?,pending_expires=?,verify_until=?,verify_generation=verify_generation+1,last_refresh_requested=?,refresh_requests=refresh_requests+1,refresh_error=NULL,status=CASE WHEN status='active' THEN status ELSE 'verifying' END WHERE id=? AND owner=? AND (pending_expires IS NULL OR verify_until<=?) RETURNING verify_generation").bind(secret,expires,now+renewalPolicy.verificationDeadlineMs,now,id,owner,now).first();
 if(!staged)throw new Error('CallbackEndpointError: refresh_in_progress');
 return {expires,generation:Number(staged.verify_generation),complete:false};
}
export async function finishRefresh(id:string,generation:number,ok:boolean,error:string|null,now=Date.now()){
 return await db().prepare("UPDATE subscriptions SET previous_secret=CASE WHEN ? AND secret!=pending_secret AND secret!='' THEN secret ELSE previous_secret END,rotation_until=CASE WHEN ? AND secret!=pending_secret AND secret!='' THEN ? ELSE rotation_until END,secret=CASE WHEN ? THEN pending_secret ELSE secret END,expires=CASE WHEN ? THEN pending_expires ELSE expires END,status=CASE WHEN ? THEN 'active' WHEN status='active' THEN 'active' ELSE 'verification_failed' END,verified_at=CASE WHEN ? THEN ? ELSE verified_at END,last_refresh_completed=CASE WHEN ? THEN ? ELSE last_refresh_completed END,refresh_successes=refresh_successes+?,refresh_error=?,error=CASE WHEN ? THEN NULL WHEN status='active' THEN error ELSE ? END,pending_secret=NULL,pending_expires=NULL,verify_until=NULL WHERE id=? AND verify_generation=? AND pending_expires IS NOT NULL AND (?=0 OR (verify_until>? AND pending_expires>?)) RETURNING id").bind(ok?1:0,ok?1:0,now+60000,ok?1:0,ok?1:0,ok?1:0,ok?1:0,now,ok?1:0,now,ok?1:0,error,ok?1:0,error,id,generation,ok?1:0,now,now).first();
}
export function subscriptionView(s:Record<string,unknown>,now=Date.now()){
 const live=s.status==='active'&&Number(s.expires)>now;
 return {...s,effectiveStatus:s.status==='active'&&!live?'expired':s.status,refreshBefore:Number(s.expires)>0?new Date(Number(s.expires)).toISOString():null,remainingMs:Math.max(0,Number(s.expires)-now),renewalState:s.pending_expires!=null?(Number(s.verify_until)>now?'verifying':'verification_timed_out'):s.refresh_error?'last_refresh_failed':Number(s.refresh_successes)>0?'last_refresh_succeeded':'not_observed',deliveryActive:live};
}
