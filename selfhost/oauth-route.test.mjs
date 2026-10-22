import './build.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign} from 'node:crypto';
import {database,createApp} from './core.mjs';
test('OAuth discovery, 401 challenge, signed access and operator isolation reach actual MCP routes',async()=>{
  const {privateKey,publicKey}=generateKeyPairSync('rsa',{modulusLength:2048});
  const jwk={...publicKey.export({format:'jwk'}),kid:'in-memory-fixture-key',alg:'RS256',use:'sig'};
  const oauth={resource:'https://connect.example.invalid/mcp',issuer:'https://identity.example.invalid/realms/connect',jwksUri:'https://identity.example.invalid/realms/connect/certs',subject:'synthetic-operator',clientId:'synthetic-client',scope:'codex:bridge'};
  const store=database(':memory:'),originalFetch=globalThis.fetch;let keyReads=0;
  globalThis.fetch=async(url)=>{assert.equal(url,oauth.jwksUri);keyReads++;return Response.json({keys:[jwk]});};
  function bearer(subject=oauth.subject){
    const now=Math.floor(Date.now()/1000),header=Buffer.from(JSON.stringify({alg:'RS256',typ:'at+jwt',kid:jwk.kid})).toString('base64url');
    const payload=Buffer.from(JSON.stringify({iss:oauth.issuer,aud:oauth.resource,sub:subject,azp:oauth.clientId,scope:oauth.scope,iat:now-1,exp:now+60})).toString('base64url');
    const raw=header+'.'+payload;return raw+'.'+sign('RSA-SHA256',Buffer.from(raw),privateKey).toString('base64url');
  }
  try{
    const app=await createApp(store,{oauth,deviceToken:'fixture-only-device-not-deployable'});
    const meta=await app(new Request('https://connect.example.invalid/.well-known/oauth-protected-resource/mcp'));
    assert.equal(meta.status,200);assert.equal((await meta.json()).resource,oauth.resource);
    const req=(token)=>new Request(oauth.resource,{method:'POST',headers:{'content-type':'application/json',...(token?{authorization:'Bearer '+token}:{}),'oai-authenticated-user-id':'forged'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'codex_access_status',arguments:{}}})});
    const denied=await app(req());assert.equal(denied.status,401);assert.match(denied.headers.get('www-authenticate'),/resource_metadata=/);
    assert.equal((await app(req('fixture-only-static-token'))).status,401);
    assert.equal((await app(req(bearer('other-subject')))).status,401);
    const accepted=await app(req(bearer()));assert.equal(accepted.status,200);
    const status=JSON.parse((await accepted.json()).result.content[0].text);assert.equal(status.authorized,true);assert.equal(status.paidServiceRequired,false);assert.equal(keyReads,1);
  }finally{globalThis.fetch=originalFetch;store.sql.close();}
});
