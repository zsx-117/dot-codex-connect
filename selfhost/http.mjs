import {createServer} from 'node:http';
export function createHttpServer(app){
const server=createServer(async (req,res)=>{
  const controller=new AbortController();
  res.on('close',()=>{if(!res.writableEnded)controller.abort();});
  try{
    const chunks=[];let size=0;
    for await (const chunk of req){size+=chunk.length;if(size>2_100_000){res.writeHead(413);res.end();return;}chunks.push(chunk);}
    const method=req.method??'GET';
    const request=new Request('http://127.0.0.1'+(req.url??'/'),{method,headers:req.headers,body:['GET','HEAD'].includes(method)?undefined:Buffer.concat(chunks),signal:controller.signal});
    const result=await app(request);
    res.writeHead(result.status,Object.fromEntries(result.headers));res.end(Buffer.from(await result.arrayBuffer()));
  }catch{if(!res.headersSent)res.writeHead(400);res.end();}
});
server.requestTimeout=15000;
server.headersTimeout=10000;
return server;
}
