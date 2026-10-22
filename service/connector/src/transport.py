"""Public App Server transport. Only owns its subprocess; never takes another writer's lock."""
import collections,json,queue,subprocess,threading,time
from executable import resolve_executable
from reliability import VERSION
class RpcError(Exception):
 def __init__(self,error):self.error=error;super().__init__(json.dumps(error,ensure_ascii=False))
class Disconnected(Exception):pass
class AppServer:
 def __init__(self,rpc_timeout=40,experimental=False):
  self.rpc_timeout=rpc_timeout
  self.executable=resolve_executable()
  try:
   self.proc=subprocess.Popen([self.executable.path,'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
  except FileNotFoundError:
   # An app upgrade can move the binary between discovery and spawn. Retry only
   # before any RPC/turn intent exists; this never restarts an existing session.
   self.executable=resolve_executable()
   self.proc=subprocess.Popen([self.executable.path,'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
  self.queue=queue.Queue();self.backlog=collections.deque();self.serial=0;self.possibly_running=False
  threading.Thread(target=self.reader,daemon=True).start()
  try:
   self.call('initialize',{'clientInfo':{'name':'dot_direct_bridge','version':VERSION},**({'capabilities':{'experimentalApi':True}} if experimental else {})})
   self.write({'method':'initialized','params':{}})
  except BaseException:
   self.close();raise
 def reader(self):
  for line in self.proc.stdout:
   try:self.queue.put(json.loads(line))
   except ValueError:pass
  self.queue.put(None)
 def write(self,obj):
  self.proc.stdin.write(json.dumps(obj,ensure_ascii=False)+'\n');self.proc.stdin.flush()
 def raw(self,timeout):
  obj=self.queue.get(timeout=timeout)
  if obj is None:raise Disconnected('App Server disconnected')
  return obj
 def event(self,timeout=10):return self.backlog.popleft() if self.backlog else self.raw(timeout)
 def call(self,method,params,timeout=None):
  timeout=self.rpc_timeout if timeout is None else timeout
  self.serial+=1;rid=self.serial;self.write({'id':rid,'method':method,'params':params});end=time.monotonic()+timeout
  while True:
   try:obj=self.raw(max(.01,end-time.monotonic()))
   except queue.Empty:raise TimeoutError(method) from None
   if obj.get('id')==rid and 'method' not in obj:
    if 'error' in obj:raise RpcError(obj['error'])
    return obj.get('result',{})
   self.backlog.append(obj)
   if time.monotonic()>=end:raise TimeoutError(method)
 def close(self):
  if self.possibly_running:return False
  # This is only our fresh subprocess and no turn may be executing in it.
  try:self.proc.stdin.close()
  except (BrokenPipeError,OSError):pass
  try:self.proc.wait(5)
  except subprocess.TimeoutExpired:
   self.proc.terminate()
   try:self.proc.wait(5)
   except subprocess.TimeoutExpired:return False
  return True
