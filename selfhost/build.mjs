// New portable adapter. Reuses the actual product libraries and route handlers.
import {readFileSync, writeFileSync, mkdirSync, readdirSync, rmSync, renameSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join, dirname} from 'node:path';
const root=dirname(fileURLToPath(import.meta.url));
const source=join(root,'../service');
const output=join(root,'.generated');
if(process.argv[1]===fileURLToPath(import.meta.url))rmSync(output,{recursive:true,force:true});
mkdirSync(output,{recursive:true});
function save(name,data){const temporary=join(output,name+'.'+process.pid+'.tmp');writeFileSync(temporary,data);renameSync(temporary,join(output,name));}
function transform(s){
  return s.replace(/import\s*\{env\}\s*from\s*'cloudflare:workers';/g,'const env = (globalThis as any).__dotSelfhostEnv;')
    .replace(/from '\.\/([^']+)'/g,(_,name)=>`from './${/\.(ts|mjs)$/.test(name)?name:name+'.ts'}'`)
    .replace(/from '\.\.\/\.\.\/lib\/([^']+)'/g,(_,name)=>`from './${name}.ts'`);
}
for(const name of readdirSync(join(source,'lib')).filter(x=>x.endsWith('.ts'))){
  save(name,transform(readFileSync(join(source,'lib',name),'utf8')));
}
for(const name of ['mcp','agent']){
  save(name+'.ts',transform(readFileSync(join(source,'app',name,'route.ts'),'utf8')));
}
save('package.json','{"type":"module"}\n');
