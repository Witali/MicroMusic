import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';
const report={schema:'micromusic-incremental-browser-v1',compilerIdentity:AVR_CACHE_COMPILER_ID,
  hardwareTested:false,realtimeTested:false,tests:[]};
function check(caseName,entry){return new Promise((resolve,reject)=>{
  const worker=new Worker(new URL('./incremental-browser-worker.mjs',import.meta.url),{type:'module'});
  const timeout=setTimeout(()=>{worker.terminate();reject(Error('Incremental Worker timeout'));},30000);
  worker.onerror=e=>{clearTimeout(timeout);worker.terminate();reject(Error(e.message));};
  worker.onmessage=({data})=>{clearTimeout(timeout);worker.terminate();data.error?reject(Error(data.error)):resolve(data);};
  worker.postMessage({caseName,entry});
});}
try{
  const catalog=await(await fetch('../firmware.json')).json(),entry=catalog.entries.find(e=>e.id==='lumiere-stereo');
  for(const name of ['audio','spm-clki'])report.tests.push(await check(name,entry));
  report.passed=true;document.querySelector('#status').textContent='PASS: physical audio/IRQ and CLKI self-programming agree in fresh Workers.';
}catch(e){report.passed=false;report.error=e.stack;document.querySelector('#status').textContent='FAIL: '+e.message;}
document.querySelector('#report').textContent=JSON.stringify(report);
