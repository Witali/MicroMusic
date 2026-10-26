import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {parseHex} from '../lib/hex.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {createRenderer} from '../lib/engines.js';
const $=id=>document.getElementById(id),status=$('status');
const assert=(ok,message)=>{if(!ok)throw Error(message);};
const json=v=>JSON.stringify(v,(_,n)=>typeof n==='bigint'?n.toString():n);
const pretty=v=>JSON.stringify(v,(_,n)=>typeof n==='bigint'?n.toString():n,2);
const equal=(a,b,label)=>assert(json(a)===json(b),label);
const sha=async bytes=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
const hash=async value=>sha(new TextEncoder().encode(json(value)));
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:Array.from(c.data),eeprom:Array.from(c.eeprom),flash:Array.from(c.rom),irq:Array.from(c.irqFrames)});
const report={schema:'micromusic-bounded-browser-v1',complete:false,parityComplete:false,realtimeComplete:false,
  browser:navigator.userAgent,platform:navigator.platform,started:new Date().toISOString(),sampleRate:48000,
  frameBlock:4096,audioDurationMs:10000,parity:[],audio:[]};
let entries,runtime;const packages=new Map();
const update=()=>{$('report').textContent=pretty(report);$('download').disabled=false;};
function error(e){status.className='fail';status.textContent='FAIL: '+e.message;report.error=e.message;update();}
function receive(target,type,timeout=30000){
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{target.removeEventListener('message',listener);reject(Error(type+' timeout'));},timeout);
    function listener({data}){
      if(data.type!==type&&data.type!=='error')return;
      clearTimeout(timer);target.removeEventListener('message',listener);
      if(data.type==='error')reject(Error(data.message||'Worker error'));else resolve(data);
    }
    target.addEventListener('message',listener);
  });
}
async function prepare(){
  if(entries)return;
  const catalogs=await Promise.all(['firmware','hq4-firmware'].map(async n=>(await(await fetch('../'+n+'.json')).json()).entries));
  entries=['rhythmic','lumiere-stereo','hq4-chego-tiny'].map(id=>catalogs.flat().find(e=>e.id===id));
  runtime=new Uint8Array(await(await fetch('../wasm/attiny13a.wasm')).arrayBuffer());report.runtimeSha256=await sha(runtime);
  report.sourceSha256={};
  for(const path of ['lib/avr-transpiler.js','lib/avr-wasm-regions.js','lib/avr-wasm-phases.js','lib/avr-phase-locals.js',
    'lib/avr-transpiled-runtime.js','lib/attiny13a-runtime.js','lib/renderer-package.js','lib/renderer-js.js','lib/audio-queue.js',
    'audio-worklet.js','worker.js','tests/bounded-browser.mjs']){
    const source=(await(await fetch('../'+path)).text()).replaceAll('\r\n','\n');
    report.sourceSha256['web-player/'+path]=await sha(new TextEncoder().encode(source));
  }
}
async function packageEntry(entry,boundedRegions){
  const key=entry.id+'/'+boundedRegions;if(packages.has(key))return packages.get(key);
  const flash=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):undefined;
  assert(await sha(flash)===entry.flashSha256,'Flash integrity '+entry.id);
  const hz=entry.cpuHz||9600000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  const configuration={resumable:true,oscillatorHz:hz,osccalHz,nvmClockProfile:1,nvmCalibrationReferenceHz:hz};
  const core=new ATtiny13A(flash,eeprom,{...configuration,boundedRegions,runtimeModule});
  const devicePackage=await createPackage({flash,eeprom,runtime,translated:core.transpiledBytes,configuration});
  const result={...entry,devicePackage};packages.set(key,result);return result;
}
$('parity').onclick=async()=>{
  $('parity').disabled=true;
  try{
    await prepare();
    for(const entry of entries){
      status.textContent='Exact browser parity: '+entry.id;
      const reference=await createRenderer(await packageEntry(entry,false),48000,{cutoff:9000,volume:.65},'device');
      const candidate=await createRenderer(await packageEntry(entry,true),48000,{cutoff:9000,volume:.65},'device');
      const checkpoints=[];
      for(let n=0;n<4;n++){
        const old=reference.render(1024),next=candidate.render(1024);
        equal(Array.from(old),Array.from(next),'Filtered PCM '+entry.id);
        equal(Array.from(reference.core.rawSamples),Array.from(candidate.core.rawSamples),'Raw PCM '+entry.id);
        equal(snapshot(reference.core),snapshot(candidate.core),'Complete CPU/device state '+entry.id);
        const pins=reference.core.drainPinsPs();equal(pins,candidate.core.drainPinsPs(),'Pin events '+entry.id);
        checkpoints.push({pcmSha256:await sha(old),stateSha256:await hash(snapshot(reference.core)),pinsSha256:await hash(pins)});
      }
      assert(candidate.core.irqCount>0,'Active firmware IRQs');assert(candidate.core.state().deviceFault===0,'No device fault');
      assert(candidate.core.transpilation.boundedRegions===true,'Embedded region option');
      report.parity.push({id:entry.id,flashSha256:entry.flashSha256,
        cpuSha256:[await sha(reference.core.transpiledBytes),await sha(candidate.core.transpiledBytes)],
        regions:candidate.core.transpilation.stats.boundedRegions,irqCount:candidate.core.irqCount,checkpoints});update();
    }
    report.parityComplete=true;status.textContent='Exact browser parity passed: 3 firmwares, 12 checkpoints. Audio checks are ready.';
    $('realtime').disabled=false;update();
  }catch(e){error(e);}
};
async function audio(entry,boundedRegions){
  const context=new AudioContext({sampleRate:48000,latencyHint:'interactive'});
  const worker=new Worker('../worker.js',{type:'module'}),ports=new MessageChannel();let node,mute;
  const row={id:entry.id,boundedRegions,sampleRate:context.sampleRate,visibilityStart:document.visibilityState,
    visibilityEnd:null,visibilityChanges:[],positions:[],states:[],contextEvents:[],wallMs:0,contextMs:0,accepted:false};
  const visibility=()=>row.visibilityChanges.push(document.visibilityState);document.addEventListener('visibilitychange',visibility);
  context.onstatechange=()=>row.contextEvents.push({state:context.state,time:context.currentTime});
  worker.addEventListener('message',({data})=>{
    if(data.type==='state')row.states.push({headroom:data.headroom,irqCount:data.state.irqs,cycles:data.state.cycles,
      deviceFault:data.state.deviceFault,timePs:data.state.timePs});
    if(data.type==='error')row.error=data.message;
  });
  try{
    const ready=receive(worker,'ready');worker.postMessage({type:'init',entry:await packageEntry(entry,boundedRegions),
      engine:'device',sampleRate:context.sampleRate,controls:{cutoff:9000,volume:.65}});await ready;
    await context.audioWorklet.addModule('../audio-worklet.js');
    node=new AudioWorkletNode(context,'firmware-output',{numberOfInputs:0,numberOfOutputs:1,outputChannelCount:[entry.audioChannels||1]});
    mute=context.createGain();mute.gain.value=0;node.connect(mute);mute.connect(context.destination);
    node.port.onmessage=({data})=>{if(data.type==='position')row.positions.push({...data,receivedAtMs:performance.now()});};
    worker.postMessage({type:'audio-port',port:ports.port2,sampleRate:context.sampleRate,controls:{cutoff:9000,volume:.65}},[ports.port2]);
    node.port.postMessage({type:'connect',session:1,channels:entry.audioChannels||1,port:ports.port1},[ports.port1]);
    node.port.postMessage({type:'playing',value:true});
    await context.resume();assert(context.state==='running','AudioContext running');
    row.contextEvents=[];
    const start=performance.now(),clock=context.currentTime;
    await new Promise(resolve=>setTimeout(resolve,report.audioDurationMs));
    row.wallMs=performance.now()-start;row.contextMs=(context.currentTime-clock)*1000;row.visibilityEnd=document.visibilityState;row.contextState=context.state;
    row.last=row.positions.at(-1)||null;row.minimumHeadroom=row.states.length?Math.min(...row.states.map(s=>s.headroom)):null;
    row.lastPositionAgeMs=row.last?performance.now()-row.last.receivedAtMs:null;
    row.maximumIRQs=row.states.length?Math.max(...row.states.map(s=>Number(s.irqCount))):0;
    row.accepted=!row.error&&row.last?.underruns===0&&row.last.frames>=context.sampleRate*8&&
      row.last.frames===row.last.clockFrames&&row.maximumIRQs>0&&row.states.every(s=>s.deviceFault===0)&&
      row.contextMs>=9000&&row.wallMs<12000&&row.lastPositionAgeMs<250&&row.contextState==='running'&&row.visibilityStart==='visible'&&row.visibilityEnd==='visible'&&
      row.visibilityChanges.every(v=>v==='visible')&&
      row.contextEvents.every(e=>e.state==='running');
    return row;
  }finally{document.removeEventListener('visibilitychange',visibility);context.onstatechange=null;node?.port.postMessage({type:'playing',value:false});node?.disconnect();mute?.disconnect();worker.terminate();await context.close();}
}
$('realtime').onclick=async()=>{
  $('realtime').disabled=true;
  try{
    for(const entry of entries)for(const enabled of [false,true]){
      status.textContent='Live audio queue: '+entry.id+' / boundedRegions='+enabled+' (10 seconds, muted output)';
      report.audio.push(await audio(entry,enabled));update();
    }
    report.realtimeComplete=true;report.complete=true;report.realtimeAccepted=report.audio.every(r=>r.accepted);
    status.className=report.realtimeAccepted?'':'fail';
    status.textContent='Audio checks completed. Real-time acceptance: '+report.realtimeAccepted+'. JSON contains underruns, IRQs and buffer positions.';update();
  }catch(e){error(e);}
};
$('download').onclick=()=>{
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([pretty(report)],{type:'application/json'}));
  a.download='bounded-browser.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
};
