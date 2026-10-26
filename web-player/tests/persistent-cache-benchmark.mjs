import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';
// Same Williams design verified by scripts/lib/runtime-control-design.mjs;
// the Node report verifier checks the actual recorded sequence independently.
const labels=['oldA','oldB','newA','newB'],orders=[[0,1,3,2],[1,2,0,3],[2,3,1,0],[3,0,2,1]];
const report={schema:'micromusic-persistent-cache-construction-v1',compilerIdentity:AVR_CACHE_COMPILER_ID,
  at:new Date().toISOString(),userAgent:navigator.userAgent,trials:8,
  old:'ordinary full-device construction, process cache retained',new:'warm persistent binary lookup and verified construction',
  construction:'inside fresh Worker after module imports; whole Worker readyMs also retained',hardwareTested:false,realtimeTested:false,workloads:[]};
function run(entry,persistent){return new Promise((resolve,reject)=>{
  const worker=new Worker(new URL('./persistent-cache-benchmark-worker.mjs',import.meta.url),{type:'module'}),start=performance.now();
  const timeout=setTimeout(()=>{worker.terminate();reject(Error('Construction Worker timeout'));},15000);
  worker.onerror=e=>{clearTimeout(timeout);worker.terminate();reject(Error(e.message));};
  worker.onmessage=({data})=>{clearTimeout(timeout);worker.terminate();data.error?reject(Error(data.error)):resolve({...data,readyMs:performance.now()-start});};
  worker.postMessage({entry,persistent});
});}
try{
  const catalog=await(await fetch('../firmware.json')).json();
  for(const id of ['rhythmic','lumiere-stereo']){
    const entry=catalog.entries.find(e=>e.id===id),record={id,flashSha256:entry.flashSha256,warmups:[],runs:[]};
    report.workloads.push(record);
    for(const variant of labels)record.warmups.push({variant,...await run(entry,variant.startsWith('new'))});
    const expected=record.warmups[0];
    for(let trial=0;trial<8;trial++){
      const order=orders[trial%4].map(n=>labels[n]);if(trial%8>=4)order.reverse();
      for(const [position,variant] of order.entries()){
        const result=await run(entry,variant.startsWith('new'));
        if(result.snapshotSha256!==expected.snapshotSha256||result.translatedSha256!==expected.translatedSha256||result.runtimeSha256!==expected.runtimeSha256)
          throw Error('Constructor output differs: '+id+' / '+variant);
        if(variant.startsWith('new')&&!result.cache?.hit)throw Error('Expected a warm persistent hit');
        record.runs.push({trial,position,variant,...result});
      }
      document.querySelector('#status').textContent=`Running: ${id}, ${trial+1}/8 trials.`;
    }
  }
  report.passed=true;document.querySelector('#status').textContent='PASS: 64 balanced observations; all constructor snapshots and code agree.';
}catch(error){report.passed=false;report.error=error.stack;document.querySelector('#status').textContent='FAIL: '+error.message;}
document.querySelector('#report').textContent=JSON.stringify(report);
