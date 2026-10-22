import {DatabaseSync} from 'node:sqlite';
import {readFileSync, readdirSync} from 'node:fs';
import {timingSafeEqual} from 'node:crypto';
import {validateOAuth,resourceMetadata,authChallenge,createOAuthVerifier} from './oauth.mjs';

export function database(filename){
  const sql=new DatabaseSync(filename);
  sql.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;');
  sql.exec('CREATE TABLE IF NOT EXISTS selfhost_migrations(name TEXT PRIMARY KEY)');
  const dir=new URL('../service/drizzle/',import.meta.url);
  for(const name of readdirSync(dir).filter(x=>x.endsWith('.sql')).sort()){
    if(sql.prepare('SELECT name FROM selfhost_migrations WHERE name=?').get(name))continue;
    sql.exec('BEGIN');
    try{sql.exec(readFileSync(new URL(name,dir),'utf8'));sql.prepare('INSERT INTO selfhost_migrations VALUES (?)').run(name);sql.exec('COMMIT');}
    catch(e){sql.exec('ROLLBACK');sql.close();throw e;}
  }
  const DB={
    prepare(query){let values=[];const q={bind(...v){values=v;return q;},async first(){return sql.prepare(query).get(...values)??null;},async all(){return {results:sql.prepare(query).all(...values)};},execute(){return {meta:{changes:Number(sql.prepare(query).run(...values).changes)}};},async run(){return q.execute();}};return q;},
    async batch(statements){sql.exec('BEGIN');try{const result=statements.map(q=>q.execute());sql.exec('COMMIT');return result;}catch(e){sql.exec('ROLLBACK');throw e;}}
  };
  return {sql,DB};
}
export function checkConfig(config){
  for(const key of config.oauth?['deviceToken']:['mcpToken','deviceToken']){
    if(typeof config[key]!=='string'||config[key].length<32||/REPLACE|CHANGEME|example|fixture/i.test(config[key]))throw new Error('Supply operator-managed credentials; no default credentials are provided.');
  }
  if(config.mcpToken===config.deviceToken)throw new Error('MCP and device credentials must be distinct.');
  if(config.oauth){validateOAuth(config.oauth);if(config.mcpToken)throw new Error('Do not enable static-token fallback in OAuth mode');}
}
function equal(a,b){const x=Buffer.from(a??''),y=Buffer.from(b);return x.length===y.length&&timingSafeEqual(x,y);}
export function authenticatedRequest(req,config,oauthVerified=false){
  const path=new URL(req.url).pathname;
  if(!['/mcp','/agent'].includes(path))return null;
  const allowed=path==='/mcp'?(config.oauth?oauthVerified:equal(req.headers.get('authorization'),'Bearer '+config.mcpToken)):equal(req.headers.get('x-bridge-device-key'),config.deviceToken);
  if(!allowed)return null;
  const headers=new Headers(req.headers);
  // Never trust internet-supplied platform identities; one configured owner only.
  for(const name of [...headers.keys()])if(name.startsWith('oai-'))headers.delete(name);
  if(path==='/mcp')headers.set('oai-authenticated-user-id','selfhost-owner');
  return new Request(req,{headers});
}
export async function createApp(store,config){
  // Process-global binding deliberately supports ONE database/owner per process.
  // Production bootstrap validates credentials; unit tests use inert in-memory fixtures.
  globalThis.__dotSelfhostEnv={DB:store.DB,DEVICE_KEY:config.deviceToken};
  store.sql.prepare("INSERT OR IGNORE INTO bridge_settings(key,value) VALUES ('owner','selfhost-owner')").run();
  const owner=store.sql.prepare("SELECT value FROM bridge_settings WHERE key='owner'").get();
  if(owner.value!=='selfhost-owner')throw new Error('Refuse an existing database with another owner.');
  const mcp=await import('./.generated/mcp.ts');
  const agent=await import('./.generated/agent.ts');
  const verifyToken=config.oauth?createOAuthVerifier(config.oauth):null;
  return async request=>{
    const path=new URL(request.url).pathname;
    if(config.oauth&&['/.well-known/oauth-protected-resource/mcp','/.well-known/oauth-protected-resource'].includes(path)){
      return request.method==='GET'?Response.json(resourceMetadata(config.oauth),{headers:{'cache-control':'public, max-age=300'}}):new Response(null,{status:405});
    }
    if(!['/mcp','/agent'].includes(path))return new Response(null,{status:404});
    if(request.method!=='POST')return new Response(null,{status:405,headers:{allow:'POST'}});
    // Browser-origin requests require a separate, reviewed front end/CSRF flow.
    if(request.headers.has('origin'))return new Response(null,{status:403});
    const token=request.headers.get('authorization')?.match(/^Bearer ([A-Za-z0-9_.-]+)$/)?.[1];
    const verified=path==='/mcp'&&verifyToken&&token?await verifyToken(token):false;
    const req=authenticatedRequest(request,config,verified);
    if(!req)return new Response(null,{status:401,headers:{'www-authenticate':config.oauth&&path==='/mcp'?authChallenge(config.oauth):'Bearer'}});
    try{return await (path==='/mcp'?mcp:agent).POST(req);}
    catch{return Response.json({error:'internal_error'},{status:500});}
  };
}
