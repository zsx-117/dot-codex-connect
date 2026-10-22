import {callTool,tools,VERSION} from '../../lib/bridge';
import {eventMethod,eventDefinitions} from '../../lib/events';
import {caller,accountAccess,AccessError} from '../../lib/access';
export async function POST(req:Request){
 let data: Record<string,any>;try{data=await req.json() as Record<string,any>;if(!data||Array.isArray(data))throw new Error();if(typeof data.method!=='string')throw new Error();}catch{return Response.json({error:'Invalid JSON-RPC request'},{status:400});}
 if(data.method==='notifications/initialized')return new Response(null,{status:202});
 let result;
 if(data.method==='server/discover')result={resultType:'complete',supportedVersions:['2026-07-28','2025-03-26','2024-11-05'],capabilities:{tools:{},events:{}}};
 else if(data.method==='initialize')result={protocolVersion:data.params?.protocolVersion??'2024-11-05',capabilities:{tools:{},events:{}},serverInfo:{name:'dot-codex-direct',version:VERSION}};
 else if(data.method==='tools/list')result={tools};
 else if(data.method==='events/list')result={events:eventDefinitions};
 else if(data.method==='ping')result={};
 else {
  const owner=req.headers.get('oai-authenticated-user-id');if(!owner)return Response.json({error:'Authenticated user required'},{status:401});
  try{
   if(data.method==='tools/call'&&data.params?.name==='codex_access_status')result={content:[{type:'text',text:JSON.stringify(await accountAccess(req))}]};
   else if(data.method==='tools/call'){const identity=await caller(req);result={content:[{type:'text',text:JSON.stringify(await callTool(identity.owner,data.params?.name??'',data.params?.arguments??{},req.signal))}]};}
   else if(data.method.startsWith('events/')){const identity=await caller(req);result=await eventMethod(identity.owner,data.method,data.params??{});}
   else throw new Error('Unknown method');
  }catch(e){const message=e instanceof Error?e.message:'Request failed';if(e instanceof AccessError){if(data.method==='tools/call')return Response.json({jsonrpc:'2.0',id:data.id,result:{isError:true,content:[{type:'text',text:JSON.stringify({error:e.code,status:e.status})}]}},{headers:{'cache-control':'no-store'}});return Response.json({jsonrpc:'2.0',id:data.id,error:{code:-32000,message:e.code,data:{status:e.status}}},{headers:{'cache-control':'no-store'}});}if(data.method.startsWith('events/'))return Response.json({jsonrpc:'2.0',id:data.id,error:{code:message.includes('CallbackEndpointError')?-32015:-32602,message,data:{reason:message.split(': ').pop()}}});result={isError:true,content:[{type:'text',text:message}]};}
 }
 return Response.json({jsonrpc:'2.0',id:data.id,result});
}
