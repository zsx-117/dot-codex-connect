import './build.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {database,checkConfig,authenticatedRequest,createApp} from './core.mjs';
const config={mcpToken:'fixture-only-mcp-not-a-valid-deployment-token',deviceToken:'fixture-only-device-not-a-valid-deployment-token'};
test('production configuration rejects absent, placeholder and equal credentials',()=>{
  for(const c of [{},config,{mcpToken:'REPLACE_WITH_OPERATOR_MANAGED_MCP_TOKEN',deviceToken:'REPLACE_WITH_OPERATOR_MANAGED_DEVICE_TOKEN'}])assert.throws(()=>checkConfig(c));
});
test('identity comes only from verified bearer; device credential cannot act as MCP user',()=>{
  assert.equal(authenticatedRequest(new Request('http://localhost/mcp',{headers:{authorization:'Bearer '+config.deviceToken,'oai-authenticated-user-id':'attacker'}}),config),null);
  const req=authenticatedRequest(new Request('http://localhost/mcp',{headers:{authorization:'Bearer '+config.mcpToken,'oai-authenticated-user-id':'attacker','oai-authenticated-user-email':'attacker@example.invalid'}}),config);
  assert.equal(req.headers.get('oai-authenticated-user-id'),'selfhost-owner');assert.equal(req.headers.get('oai-authenticated-user-email'),null);
});
test('actual MCP and agent routes round-trip durable jobs with no billing or network',async()=>{
  const store=database(':memory:');const nativeFetch=globalThis.fetch;
  globalThis.fetch=()=>{throw new Error('Network forbidden in offline acceptance');};
  try{
    const app=await createApp(store,config);
    const request=(path,body,headers={})=>new Request('http://localhost'+path,{method:'POST',headers:{'content-type':'application/json',...headers},body:JSON.stringify(body)});
    const mcp=async(name,args={})=>{const r=await app(request('/mcp',{jsonrpc:'2.0',id:1,method:'tools/call',params:{name,arguments:args}},{authorization:'Bearer '+config.mcpToken}));assert.equal(r.status,200);const value=await r.json();assert.equal(value.result?.isError,undefined);return JSON.parse(value.result.content[0].text);};
    const agent=async body=>{const r=await app(request('/agent',body,{'x-bridge-device-key':config.deviceToken}));assert.equal(r.status,200);return r.json();};
    assert.equal((await app(request('/mcp',{}))).status,401);
    assert.equal((await app(request('/mcp',{}, {origin:'https://untrusted.example.invalid',authorization:'Bearer '+config.mcpToken}))).status,403);
    assert.equal((await app(request('/agent',{}, {'x-bridge-device-key':config.mcpToken}))).status,401);
    const access=await mcp('codex_access_status');assert.equal(access.licensed,true);
    await agent({op:'heartbeat'});
    const args={requestId:'selfhost-fixture-list-001',limit:10};
    const first=await mcp('list_codex_threads',args);
    const duplicate=await mcp('list_codex_threads',args);assert.equal(first.jobId,duplicate.jobId);
    const poll=await agent({op:'poll',version:2});assert.equal(poll.job.id,first.jobId);
    assert.equal((await agent({op:'poll',version:2})).job,null);
    await agent({op:'sync',record:{id:first.jobId,revision:1,state:'completed',result:{chats:[]}}});
    await agent({op:'sync',record:{id:first.jobId,revision:0,state:'executing'}});
    const row=store.sql.prepare('SELECT status,revision FROM bridge_jobs WHERE id=?').get(first.jobId);assert.equal(row.status,'completed');assert.equal(row.revision,1);
    const result=await mcp('codex_job_result',{requestId:args.requestId});assert.ok(JSON.stringify(result).includes('completed'));
    assert.equal(store.sql.prepare("SELECT COUNT(*) AS n FROM sqlite_master WHERE name='bridge_accounts'").get().n,0);
  }finally{globalThis.fetch=nativeFetch;store.sql.close();}
});
