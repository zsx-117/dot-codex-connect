import './build.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {database,createApp} from './core.mjs';
import {createHttpServer} from './http.mjs';
test('loopback HTTP: real transport, isolated SQLite, synthetic device and MCP credentials',async()=>{
  const config={mcpToken:'fixture-only-mcp-not-deployable',deviceToken:'fixture-only-device-not-deployable'};
  const store=database(':memory:'),app=await createApp(store,config),server=createHttpServer(app);
  server.listen(0,'127.0.0.1');await once(server,'listening');
  const origin='http://127.0.0.1:'+server.address().port;
  try{
    const send=(path,body,headers={})=>fetch(origin+path,{method:'POST',headers:{'content-type':'application/json',...headers},body:JSON.stringify(body)});
    assert.equal((await send('/mcp',{})).status,401);
    assert.equal((await fetch(origin+'/mcp')).status,405);
    assert.equal((await send('/agent',{}, {'x-bridge-device-key':config.mcpToken})).status,401);
    const init=await send('/mcp',{jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-11-25'}},{authorization:'Bearer '+config.mcpToken});
    assert.equal(init.status,200);assert.equal((await init.json()).result.protocolVersion,'2025-11-25');
    const heartbeat=await send('/agent',{op:'heartbeat'},{'x-bridge-device-key':config.deviceToken});assert.equal(heartbeat.status,200);
    const status=await send('/mcp',{jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'codex_connection_status',arguments:{}}},{authorization:'Bearer '+config.mcpToken});
    assert.equal(JSON.parse((await status.json()).result.content[0].text).online,true);
    const rejected=await send('/mcp',{}, {authorization:'Bearer '+config.mcpToken,origin:'https://untrusted.example.invalid'});assert.equal(rejected.status,403);
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));store.sql.close();}
});
