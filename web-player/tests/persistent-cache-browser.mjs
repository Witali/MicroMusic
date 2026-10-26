import {createIndexedDBTranslationStore} from '../lib/avr-indexeddb-cache.js';
import {createCachedDeviceCore} from '../lib/avr-persistent-cache.js';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js?v=20261026-persistent-cache';
import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';
const report={schema:'micromusic-persistent-cache-browser-v1',compilerIdentity:AVR_CACHE_COMPILER_ID,
  hardwareTested:false,realtimeTested:false,tests:[],workers:[]};
const assert=(ok,message)=>{if(!ok)throw Error(message);};
const json=value=>JSON.stringify(value,(_key,v)=>typeof v==='bigint'?v+'n':typeof v==='number'&&!Number.isFinite(v)?String(v):ArrayBuffer.isView(v)?Array.from(v):v);
const equal=(a,b,message)=>assert(json(a)===json(b),message);
const names=[],stores=[],prefix='micromusic-avr-cache-test-'+Date.now();
let tick=0;
function store(id,limits={}){
  const name=prefix+'-'+id;names.push(name);
  const result=createIndexedDBTranslationStore({name,now:()=>++tick,...limits});
  stores.push(result);return result;
}
function inspect(name){return new Promise((resolve,reject)=>{
  const request=indexedDB.open(name,1);request.onerror=()=>reject(request.error);
  request.onsuccess=()=>{const db=request.result,tx=db.transaction('translations','readonly'),rows=tx.objectStore('translations').getAll();
    tx.oncomplete=()=>{db.close();resolve(rows.result);};tx.onabort=()=>{db.close();reject(tx.error);};};
});}
async function check(name,fn){const start=performance.now();await fn();report.tests.push({name,passed:true,ms:performance.now()-start});}
try{
  await check('IndexedDB is available',async()=>assert(!!globalThis.indexedDB,'IndexedDB unavailable'));
  await check('browser runtime bytes do not expose the loader ArrayBuffer',async()=>{
    const a=getRuntimeBytes(),b=getRuntimeBytes();a.fill(0);equal(getRuntimeBytes(),b,'Immutable runtime input');
    assert(a.buffer!==b.buffer,'Independent copies');
  });
  await check('binary records preserve snapshots and count metadata plus bytecode',async()=>{
    const a=store('binary',{maxEntries:3,maxBytes:7}),bytes=Uint8Array.of(1,2,3,4),value={metadata:'é',bytes};
    const pending=a.put('a',value);bytes.fill(0);value.metadata='changed';await pending;
    let actual=await a.get('a');equal(actual,{metadata:'é',bytes:Uint8Array.of(1,2,3,4)},'Snapshot before async open');
    actual.bytes.fill(9);actual=await a.get('a');assert(actual.bytes[0]===1,'Reads do not mutate stored bytes');
    await a.put('b','x');let rows=await inspect(prefix+'-binary');assert(rows.reduce((n,r)=>n+r.bytes,0)===7,'Binary plus UTF-8 weight');
    await a.put('c','x');assert(await a.get('a')===null,'Binary record evicted by byte cap');
    assert(await a.put('large',{metadata:'é',bytes:new Uint8Array(6)})===false,'Oversized binary rejected');
  });
  await check('entry eviction honors last use across connections',async()=>{
    const a=store('entries',{maxEntries:2,maxBytes:20});await a.put('a','1111');await a.put('b','2222');await a.get('a');
    const b=store('entries',{maxEntries:2,maxBytes:20});await b.put('c','3333');
    assert(await a.get('b')===null,'Least recently used entry must be evicted');
    assert(await b.get('a')==='1111'&&await a.get('c')==='3333','Retain recent entries');
    const rows=await inspect(prefix+'-entries');assert(rows.length===2,'Entry bound');
  });
  await check('byte bounds count UTF-8 and reject oversized writes',async()=>{
    const a=store('bytes',{maxEntries:3,maxBytes:7});await a.put('a','éé');await a.put('b','abc');
    let rows=await inspect(prefix+'-bytes');assert(rows.reduce((n,r)=>n+r.bytes,0)===7,'Exact UTF-8 bound');
    await a.put('c','x');assert(await a.get('a')===null,'Byte eviction');
    assert(await a.put('large','😀😀')===false,'Oversized write cannot displace useful records');
    rows=await inspect(prefix+'-bytes');assert(rows.length===2&&rows.reduce((n,r)=>n+r.bytes,0)<=7,'Byte cap');
  });
  await check('concurrent writers commit bounded transactions',async()=>{
    const a=store('concurrent',{maxEntries:2,maxBytes:20}),b=store('concurrent',{maxEntries:2,maxBytes:20});
    await Promise.all([a.get('none'),b.get('none')]);
    await Promise.all([a.put('a','1111111'),b.put('b','2222222'),a.put('c','3333333'),b.put('d','4444444')]);
    const rows=await inspect(prefix+'-concurrent');assert(rows.length===2&&rows.reduce((n,r)=>n+r.bytes,0)<=20,'Concurrent bounds');
  });
  await check('reopened storage reuses code but resets the complete chip',async()=>{
    const a=store('chip'),flash=Uint8Array.of(0x0a,0xe5,0xff,0xcf),runtimeBytes=getRuntimeBytes();
    const cold=await createCachedDeviceCore({Core:ATtiny13A,flash,runtimeBytes,store:a});
    assert(cold.persistentTranslationCache.stored,'Cold translation stored');cold.step();cold.eeprom[0]=0;
    await a.close();const b=store('chip');
    const warm=await createCachedDeviceCore({Core:ATtiny13A,flash,runtimeBytes,store:b});
    assert(warm.persistentTranslationCache.hit,'Reopen hit');assert(warm.r[16]===0&&warm.eeprom[0]===255,'Fresh CPU/EEPROM');
    warm.step();assert(warm.r[16]===90,'Real generated instruction');
    const key=warm.persistentTranslationCache.key;await b.put(key,'{broken');
    const repaired=await createCachedDeviceCore({Core:ATtiny13A,flash,runtimeBytes,store:b});
    assert(repaired.persistentTranslationCache.status==='repaired'&&repaired.persistentTranslationCache.stored,'Corrupt record repaired');
    repaired.step();assert(repaired.r[16]===90,'Repair semantics');
  });
  const catalog=await (await fetch('../firmware.json')).json(),entry=catalog.entries.find(e=>e.id==='lumiere-stereo');
  function message(port,type){return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{port.removeEventListener('message',handler);reject(Error('Worker message timeout: '+type));},15000);
    const handler=({data})=>{if(data.type==='error'||data.type===type){clearTimeout(timer);port.removeEventListener('message',handler);data.type==='error'?reject(Error(data.message)):resolve(data);}};
    port.addEventListener('message',handler);port.start?.();
  });}
  async function runWorker(){
    const worker=new Worker(new URL('../worker.js?v=20261026-persistent-cache',import.meta.url),{type:'module'}),channel=new MessageChannel();
    try{
      const ready=message(worker,'ready'),start=performance.now();
      worker.postMessage({type:'init',entry,configuration:'verification',sampleRate:48000,controls:{volume:0,cutoff:6000}});
      const initial=await ready,readyMs=performance.now()-start;
      worker.postMessage({type:'audio-port',port:channel.port2,sampleRate:48000},[channel.port2]);
      const state=message(worker,'state'),samples=message(channel.port1,'samples');channel.port1.postMessage({type:'need',frames:4096});
      const [observed,output]=await Promise.all([state,samples]);
      assert(output.samples.every(x=>x===0),'Muted output');
      report.workers.push({readyMs,cache:initial.translationCache,model:initial.emulationModel,
        cycles:observed.state.cycles,irqs:observed.state.irqs,deviceFault:observed.state.deviceFault});
      return {state:observed.state,samples:output.samples,raw:observed.scopes,cache:initial.translationCache};
    }finally{worker.terminate();channel.port1.close();}
  }
  await check('fresh production Workers reuse verified code and reproduce physical output/state',async()=>{
    const a=await runWorker(),b=await runWorker();assert(a.cache.stored,'First Worker stored or reused code');
    assert(b.cache.hit,'Second Worker must use persistent cache after first Worker terminated');
    equal(a.state,b.state,'Complete hardware state');equal(a.samples,b.samples,'PCM');equal(a.raw,b.raw,'Physical raw pin audio');
    assert(b.state.deviceFault===0&&b.state.irqs>0,'Actual firmware and interrupts must execute beyond oscillator startup');
    assert(b.raw.some(scope=>scope.some(x=>x!==-1)),'Physical pin audio must advance beyond the initial low level');
  });
  report.passed=true;document.querySelector('#status').textContent=`PASS: ${report.tests.length} browser checks.`;
}catch(error){report.passed=false;report.error=error.stack;document.querySelector('#status').textContent='FAIL: '+error.message;}
finally{
  await Promise.all(stores.map(s=>s.close()));
  for(const name of new Set(names))await new Promise(resolve=>{
    const request=indexedDB.deleteDatabase(name);request.onsuccess=request.onerror=request.onblocked=()=>resolve();
  });
  document.querySelector('#report').textContent=json(report);
}
