type JobView={taskView?:{terminal?:boolean;needsAttention?:boolean;canWait?:boolean};[key:string]:unknown};
type Observation={kind:'result';job:JobView}|{kind:'cancelled'}|{kind:'timeout'};
function observe(lookup:()=>Promise<JobView>,ms:number,signal?:AbortSignal){
 return new Promise<Observation>((resolve,reject)=>{
  if(signal?.aborted){resolve({kind:'cancelled'});return;}
  let settled=false;
  const clean=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);};
  const finish=(value:Observation)=>{if(settled)return;settled=true;clean();resolve(value);};
  const abort=()=>finish({kind:'cancelled'}),timer=setTimeout(()=>finish({kind:'timeout'}),Math.max(0,ms));
  signal?.addEventListener('abort',abort,{once:true});
  // This is a read-only lookup. Its late settlement is observed, but cannot
  // keep the caller waiting or cancel/modify the original task.
  Promise.resolve().then(lookup).then(job=>finish({kind:'result',job}),error=>{
   if(settled)return;settled=true;clean();reject(error);
  });
 });
}
function pause(ms:number,signal?:AbortSignal){
 return new Promise<boolean>(resolve=>{
  if(signal?.aborted){resolve(false);return;}
  const finish=(ok:boolean)=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);resolve(ok);};
  const abort=()=>finish(false),timer=setTimeout(()=>finish(true),ms);
  signal?.addEventListener('abort',abort,{once:true});
 });
}

/** Read-only wait. Aborting the caller's wait never calls any cancel/interrupt API. */
export async function waitForJob(lookup:()=>Promise<JobView>,waitMs:unknown=5000,signal?:AbortSignal){
 if(typeof waitMs!=='number'||!Number.isInteger(waitMs)||waitMs<0||waitMs>10000)throw new Error('waitMs must be an integer from 0 to 10000');
 // waitMs=0 requests one lookup without polling; that lookup still has the
 // service's ten-second upper bound. Positive waits include lookup latency.
 const deadline=performance.now()+(waitMs===0?10000:waitMs);
 let job:JobView|null=null,lookupPending=false;
 const result=(state:string)=>({...job,wait:{state,readOnly:true,taskUnaffected:true,maxWaitMs:waitMs,maxLookupMs:10000,resultAvailable:job!==null,lookupPending,resume:'Query the same jobId/requestId. No message has been resent.'}});
 for(;;){
  if(signal?.aborted)return result('wait_cancelled');
  lookupPending=true;
  const observed=await observe(lookup,deadline-performance.now(),signal);
  if(observed.kind==='cancelled')return result('wait_cancelled');
  if(observed.kind==='timeout')return result('still_pending');
  job=observed.job;lookupPending=false;
  if(!job.taskView||job.taskView.terminal||job.taskView.needsAttention||!job.taskView.canWait)return result('state_available');
  if(waitMs===0)return result('still_pending');
  const remaining=deadline-performance.now();
  if(remaining<=0)return result('still_pending');
  if(!await pause(Math.min(1000,remaining),signal))return result('wait_cancelled');
  if(performance.now()>=deadline)return result('still_pending');
 }
}
