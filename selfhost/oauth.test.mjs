import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign} from 'node:crypto';
import {createOAuthVerifier,validateOAuth,resourceMetadata,authChallenge} from './oauth.mjs';
// Ephemeral cryptographic fixtures only; private keys and signed tokens never leave memory.
const {privateKey,publicKey}=generateKeyPairSync('rsa',{modulusLength:2048});
const jwk={...publicKey.export({format:'jwk'}),kid:'synthetic-key',alg:'RS256',use:'sig'};
const cfg={resource:'https://connect.example.invalid/mcp',issuer:'https://identity.example.invalid/realms/connect',jwksUri:'https://identity.example.invalid/realms/connect/certs',subject:'synthetic-operator',clientId:'synthetic-client',scope:'codex:bridge'};
const now=2_000_000_000;
const payload={iss:cfg.issuer,sub:cfg.subject,aud:cfg.resource,azp:cfg.clientId,scope:cfg.scope,iat:now-10,exp:now+300,typ:'Bearer'};
function token(p={},h={}){const head=Buffer.from(JSON.stringify({alg:'RS256',typ:'JWT',kid:jwk.kid,...h})).toString('base64url'),body=Buffer.from(JSON.stringify({...payload,...p})).toString('base64url');const input=head+'.'+body;return input+'.'+sign('RSA-SHA256',Buffer.from(input),privateKey).toString('base64url');}
test('protected resource discovery points to operator-controlled issuer',()=>{
  assert.equal(resourceMetadata(cfg).resource,cfg.resource);assert.deepEqual(resourceMetadata(cfg).authorization_servers,[cfg.issuer]);assert.ok(authChallenge(cfg).includes('/.well-known/oauth-protected-resource/mcp'));
  assert.throws(()=>validateOAuth({...cfg,jwksUri:'https://attacker.example.invalid/keys'}));
});
test('valid RSA access token is accepted and public keys are cached',async()=>{
  let calls=0;const verify=createOAuthVerifier(cfg,{clock:()=>now*1000,fetcher:async()=>{calls++;return Response.json({keys:[jwk]});}});
  assert.equal(await verify(token()),true);assert.equal(await verify(token()),true);assert.equal(calls,1);
});
test('wrong issuer, audience, subject, client, expiry, scope and ID tokens fail',async()=>{
  const verify=createOAuthVerifier(cfg,{clock:()=>now*1000,fetcher:async()=>Response.json({keys:[jwk]})});
  for(const p of [{iss:'https://other.example.invalid'},{aud:'other-api'},{sub:'other-operator'},{azp:'other-client'},{exp:now},{iat:now+60},{nbf:now+60},{exp:now+7200},{scope:'openid'},{typ:'ID'}])assert.equal(await verify(token(p)),false);
  for(const h of [{alg:'none'},{alg:'HS256'},{jku:'https://attacker.example.invalid/keys'},{crit:['b64']}])assert.equal(await verify(token({},h)),false);
  const signed=token();assert.equal(await verify(signed.slice(0,-8)+'AAAAAAAA'),false);
});
test('JWKS outage, duplicate kid, invalid key and refresh storms fail closed',async()=>{
  for(const fetcher of [async()=>{throw new Error('offline')},async()=>Response.json({keys:[jwk,jwk]}),async()=>Response.json({keys:[{...jwk,kty:'oct'}]})]){
    const verify=createOAuthVerifier(cfg,{clock:()=>now*1000,fetcher});assert.equal(await verify(token()),false);
  }
  let calls=0;const verify=createOAuthVerifier(cfg,{clock:()=>now*1000,fetcher:async()=>{calls++;return Response.json({keys:[jwk]});}});
  for(let i=0;i<10;i++)assert.equal(await verify(token({},{kid:'unknown-'+i})),false);
  assert.equal(calls,1);
});
