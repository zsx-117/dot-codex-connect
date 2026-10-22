// MIT — zsx-117 and contributors. Single-operator access; no purchase or account service.
import {env} from 'cloudflare:workers';
import {db,authorized} from './bridge';
export class AccessError extends Error {status:number;code:string;constructor(status:number,code:string){super(code);this.status=status;this.code=code;}}
export async function operator(){return (await db().prepare("SELECT value FROM bridge_settings WHERE key='owner'").first<{value:string}>())?.value??null;}
export async function isOperator(owner:string){return owner===await operator();}
export async function caller(req:Request){
 const owner=req.headers.get('oai-authenticated-user-id');
 if(!owner)throw new AccessError(401,'authentication_required');
 await authorized(owner);
 return {owner};
}
export async function accountAccess(req:Request){
 const {owner}=await caller(req);
 const device=await db().prepare("SELECT seen FROM device WHERE id='mac'").first<{seen:number}>();
 const pending=await db().prepare("SELECT COUNT(*) AS n FROM bridge_jobs WHERE owner=? AND status NOT IN ('completed','failed','blocked_capability','cancelled')").bind(owner).first<{n:number}>();
 return {authorized:true,licensed:true,accessMode:'self_hosted_operator',paidServiceRequired:false,deviceLinked:!!device,online:!!device&&Date.now()-device.seen<30000,pendingTasks:pending?.n??0};
}
export async function authenticateDevice(req:Request){
 const key=req.headers.get('x-bridge-device-key'),expected=(env as unknown as Record<string,string>).DEVICE_KEY;
 if(!key||!expected||key.length!==expected.length)throw new AccessError(403,'device_authorization_required');
 let different=0;for(let i=0;i<key.length;i++)different|=key.charCodeAt(i)^expected.charCodeAt(i);
 if(different)throw new AccessError(403,'device_authorization_required');
 const owner=await operator();if(!owner)throw new AccessError(403,'operator_not_configured');
 return {owner,id:'mac'};
}
