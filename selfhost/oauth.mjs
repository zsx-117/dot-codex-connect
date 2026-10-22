// MIT — zsx-117 and contributors. OAuth resource server, not an authorization server.
import {createPublicKey,verify} from 'node:crypto';
export function validateOAuth(config){
  for(const name of ['resource','issuer','jwksUri']){
    const u=new URL(config[name]);
    if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash)throw new Error('OAuth endpoints must be explicit HTTPS URLs');
  }
  if(new URL(config.resource).pathname!=='/mcp')throw new Error('Resource must be the canonical /mcp URL');
  if(new URL(config.jwksUri).origin!==new URL(config.issuer).origin)throw new Error('JWKS must be on the configured issuer origin');
  for(const name of ['subject','clientId','scope'])if(typeof config[name]!=='string'||!config[name]||config[name].length>500||/[\r\n"\\]/.test(config[name]))throw new Error('Missing or invalid OAuth operator policy');
}
export function resourceMetadata(config){
  return {resource:config.resource,authorization_servers:[config.issuer],scopes_supported:[config.scope],bearer_methods_supported:['header']};
}
export function metadataURL(config){return new URL('/.well-known/oauth-protected-resource/mcp',config.resource).href;}
export function authChallenge(config){return `Bearer resource_metadata="${metadataURL(config)}", scope="${config.scope}"`;}
function decode(segment){
  if(!/^[A-Za-z0-9_-]+$/.test(segment))throw new Error('Invalid encoding');
  const value=JSON.parse(Buffer.from(segment,'base64url').toString('utf8'));
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('Invalid JSON object');
  return value;
}
export function createOAuthVerifier(config,{fetcher=globalThis.fetch,clock=Date.now}={}){
  validateOAuth(config);
  let keys=[],expires=0,lastFetch=-Infinity,inflight;
  async function refresh(){
    if(inflight)return inflight;
    if(clock()-lastFetch<60_000)return; // Bound unknown-kid traffic; rotation may wait <= 60s.
    lastFetch=clock();
    inflight=(async()=>{
      const response=await fetcher(config.jwksUri,{redirect:'error',signal:AbortSignal.timeout(5000),headers:{accept:'application/json'}});
      if(!response.ok||Number(response.headers.get('content-length')??0)>128_000)throw new Error('JWKS unavailable');
      const reader=response.body.getReader();let size=0;const chunks=[];
      for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>128_000){await reader.cancel();throw new Error('JWKS too large');}chunks.push(Buffer.from(value));}
      const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if(!Array.isArray(body.keys)||body.keys.length>32)throw new Error('Invalid JWKS');
      keys=body.keys.filter(k=>k.kty==='RSA'&&typeof k.kid==='string'&&(!k.alg||k.alg==='RS256')&&(!k.use||k.use==='sig')&&(!k.key_ops||k.key_ops.includes('verify'))&&!k.d);
      expires=clock()+300_000;
    })();
    try{await inflight;}finally{inflight=undefined;}
  }
  return async function verifyAccessToken(token){
    try{
      if(typeof token!=='string'||token.length>16_384)return false;
      const parts=token.split('.');if(parts.length!==3)return false;
      const h=decode(parts[0]),p=decode(parts[1]),now=Math.floor(clock()/1000);
      if(h.alg!=='RS256'||typeof h.kid!=='string'||h.kid.length>200||h.crit||h.jku||h.x5u||h.jwk)return false;
      // Do not accept an OIDC ID token as an access token.
      if(h.typ!=='at+jwt'&&!(h.typ==='JWT'&&p.typ==='Bearer'))return false;
      if(p.iss!==config.issuer||p.sub!==config.subject||(p.azp??p.client_id)!==config.clientId)return false;
      const audiences=Array.isArray(p.aud)?p.aud:[p.aud];
      if(!audiences.includes(config.resource)||typeof p.scope!=='string'||!p.scope.split(' ').includes(config.scope))return false;
      if(!Number.isSafeInteger(p.exp)||!Number.isSafeInteger(p.iat)||p.exp<=now||p.iat>now+30||p.exp<=p.iat||p.exp-p.iat>3600)return false;
      if(p.nbf!==undefined&&(!Number.isSafeInteger(p.nbf)||p.nbf>now+30))return false;
      if(expires<=clock()||!keys.some(k=>k.kid===h.kid))await refresh();
      if(expires<=clock())return false;
      const found=keys.filter(k=>k.kid===h.kid);if(found.length!==1)return false;
      const key=createPublicKey({key:found[0],format:'jwk'});
      if(key.asymmetricKeyDetails.modulusLength<2048)return false;
      return verify('RSA-SHA256',Buffer.from(parts[0]+'.'+parts[1]),key,Buffer.from(parts[2],'base64url'));
    }catch{return false;}
  };
}
