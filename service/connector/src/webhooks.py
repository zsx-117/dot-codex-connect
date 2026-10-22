"""Standard Webhooks sender with public-IP pinning, TLS hostname verification, no redirects."""
import base64,hashlib,hmac,http.client,ipaddress,json,secrets,socket,ssl,time,urllib.parse,urllib.request
def local_https_proxy(host):
 # Use the existing proxy configuration only; never accept credentials or remote proxies.
 if urllib.request.proxy_bypass(host):return None
 value=urllib.request.getproxies().get('https')
 if not value:return None
 parsed=urllib.parse.urlsplit(value if '://' in value else 'http://'+value)
 if parsed.scheme!='http' or parsed.username or parsed.password:raise ValueError('unsupported_proxy_configuration')
 try:loopback=ipaddress.ip_address(parsed.hostname).is_loopback
 except ValueError:loopback=parsed.hostname=='localhost'
 if not loopback:raise ValueError('unsupported_proxy_configuration')
 return (parsed.hostname,parsed.port or 80)

class PinnedHTTPS(http.client.HTTPSConnection):
 def __init__(self,host,address):
  super().__init__(host,timeout=12,context=ssl.create_default_context())
  self.addresses=[address] if isinstance(address,str) else list(address)
 def connect(self):
  proxy=local_https_proxy(self.host);deadline=time.monotonic()+10
  for address in self.addresses[:4]:
   raw=None
   try:
    # Revalidate even when called without the DNS helper. CONNECT uses pinned IP,
    # while end-to-end TLS still checks the original hostname and certificate.
    if not ipaddress.ip_address(address).is_global:raise ValueError('callback_not_public')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('connection_deadline')
    timeout=min(3,remaining)
    if proxy:
     tunnel=http.client.HTTPConnection(proxy[0],proxy[1],timeout=timeout)
     tunnel.set_tunnel(address,443)
     try:tunnel.connect();raw=tunnel.sock;tunnel.sock=None
     finally:tunnel.close()
    else:raw=socket.create_connection((address,443),timeout)
    self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
    self.sock.settimeout(self.timeout)
    return
   except (OSError,http.client.HTTPException):
    if raw:raw.close()
    # Only retry before an HTTP request is written; never replay an ambiguous POST here.
  raise TimeoutError('callback_connect_failed')
def public_addresses(host):
 if not host or host.endswith('.local'):raise ValueError('callback_not_public')
 addresses=sorted({r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
 # Source edition uses the operator's system DNS only; Fake-IP/private answers fail closed.
 if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('callback_not_public')
 return addresses

def send(task):
 try:
  url=urllib.parse.urlsplit(task['url'])
  if url.scheme!='https' or url.username or url.password or url.port not in (None,443) or url.fragment:raise ValueError('invalid_callback')
  addresses=public_addresses(url.hostname);verification=task['type']=='verify'
  challenge=secrets.token_urlsafe(32)
  event_id='verify_'+secrets.token_hex(16) if verification else task['eventId']
  body={'type':'verification','challenge':challenge} if verification else {'eventId':event_id,'name':task['name'],'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(task['created']/1000)),'data':json.loads(task['payload']),'cursor':None}
  raw=json.dumps(body,separators=(',',':'),ensure_ascii=False).encode();timestamp=str(int(time.time()))
  key=base64.b64decode(task['secret'].removeprefix('whsec_'),validate=True)
  signature=base64.b64encode(hmac.new(key,event_id.encode()+b'.'+timestamp.encode()+b'.'+raw,hashlib.sha256).digest()).decode()
  signatures='v1,'+signature
  if task.get('previous_secret') and task.get('rotation_until',0)>time.time()*1000:
   old=base64.b64decode(task['previous_secret'].removeprefix('whsec_'),validate=True)
   signatures+=' v1,'+base64.b64encode(hmac.new(old,event_id.encode()+b'.'+timestamp.encode()+b'.'+raw,hashlib.sha256).digest()).decode()
  sub=task['id'] if verification else task['subscriptionId']
  con=PinnedHTTPS(url.hostname,addresses)
  try:
   con.request('POST',urllib.parse.urlunsplit(('', '',url.path or '/',url.query,'')),body=raw,headers={'Content-Type':'application/json','webhook-id':event_id,'webhook-timestamp':timestamp,'webhook-signature':signatures,'X-MCP-Subscription-Id':sub})
   response=con.getresponse();code=response.status;content=response.read(16384)
  finally:con.close()
  ok=200<=code<300
  if verification:
   try:ok=ok and hmac.compare_digest(json.loads(content).get('challenge',''),challenge)
   except (ValueError,TypeError):ok=False
  return {'op':'callback_result','type':task['type'],'id':task['id'],'ok':ok,'code':code,'attempt':task.get('attempt',0),'verifyGeneration':task.get('verifyGeneration'),'error':None if ok else 'challenge_failed' if verification else 'http_'+str(code)}
 except Exception as exc:
  return {'op':'callback_result','type':task['type'],'id':task['id'],'ok':False,'attempt':task.get('attempt',0),'verifyGeneration':task.get('verifyGeneration'),'error':str(exc) if str(exc) in ('callback_not_public','invalid_callback','unsupported_proxy_configuration') else type(exc).__name__}  # no URL, signing secret or response body in logs
