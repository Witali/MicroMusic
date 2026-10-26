import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
// Install the handler before native loaders' top-level awaits can yield.
const modules=Promise.all([import('../lib/renderer-device.js?v=20261026-persistent-cache'),
  import('../lib/attiny13a.js?v=20261026-persistent-cache')]);
const sha=async b=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),n=>n.toString(16).padStart(2,'0')).join('');
const json=v=>JSON.stringify(v,(_k,x)=>typeof x==='bigint'?x+'n':typeof x==='number'&&!Number.isFinite(x)?String(x):ArrayBuffer.isView(x)?Array.from(x):x);
self.onmessage=async({data})=>{
  try{
    const [{Renderer,createDeviceRenderer},{getRuntimeBytes}]=await modules;
    const options=nominalVerificationDeviceOptions(data.entry.cpuHz),controls={volume:0,cutoff:6000};
    const start=performance.now();
    const r=data.persistent?await createDeviceRenderer(data.entry,48000,controls,options)
      :new Renderer(data.entry,48000,controls,undefined,options);
    const ms=performance.now()-start,c=r.core;
    const snapshot={state:c.state(),data:c.data,flash:c.rom,eeprom:c.eeprom,nativeState:c._state,pins:c.drainPinsPs()};
    self.postMessage({ms,cache:r.translationCache??null,snapshotSha256:await sha(new TextEncoder().encode(json(snapshot))),
      translatedSha256:await sha(c.transpiledBytes),runtimeSha256:await sha(getRuntimeBytes())});
  }catch(e){self.postMessage({error:e.stack});}
};
