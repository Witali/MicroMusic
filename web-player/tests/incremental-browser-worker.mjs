import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {parseHex} from '../lib/hex.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
const corePromise=import('../lib/attiny13a.js');
const json=v=>JSON.stringify(v,(_k,x)=>typeof x==='bigint'?x+'n':typeof x==='number'&&!Number.isFinite(x)?String(x):ArrayBuffer.isView(x)?Array.from(x):x);
const same=(a,b,label)=>{if(json(a)!==json(b))throw Error(label+' differs');};
const sha=async b=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),n=>n.toString(16).padStart(2,'0')).join('');
function spmImage(){
  const write=(io,v)=>[...avr.ldi(16,v),...avr.out(io,16)],target=0x100,newWords=[avr.ldi(20,0x5a)[0],0xcfff];
  const words=[...avr.ldi(30,0),...avr.ldi(31,1),...write(IO.SPMCSR,3),0x95e8];
  for(const [n,w] of newWords.entries())words.push(...avr.ldi(30,2*n),...avr.ldi(16,w&255),0x2e00,
    ...avr.ldi(16,w>>8),0x2e10,...write(IO.SPMCSR,1),0x95e8);
  words.push(...avr.ldi(30,0),...write(IO.SPMCSR,5),0x95e8);words.push(avr.rjmp(words.length,target/2)[0]);
  return flash({instructions:[words]},{at:target/2,instructions:[avr.ldi(20,0x11),[0xcfff]]});
}
self.onmessage=async({data:{caseName,entry}})=>{
  try{
    const {ATtiny13A}=await corePromise,options=caseName==='audio'?nominalVerificationDeviceOptions(entry.cpuHz):{
      resumable:true,fuseHigh:0xef,fuseLow:0x70,spmCommandCycles:4,nvmClockProfile:1,nvmCalibrationReferenceHz:1000000,
      clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}};
    const image=caseName==='audio'?parseHex(entry.flashHex):spmImage();
    const [a,b]=[false,true].map(incrementalCompilation=>new ATtiny13A(image,null,{...options,cacheTranslation:false,incrementalCompilation}));
    let observations=0,pcmSha256=null;
    if(caseName==='audio'){
      const pcm=a.capturePhysical(4096,48000,2),other=b.capturePhysical(4096,48000,2);same(pcm,other,'Physical PCM');
      if(b.state().irqs<1||!other.some(v=>v!==-1))throw Error('Firmware must execute beyond startup');
      same(a.drainPinsPs(),b.drainPinsPs(),'Pending pin trace');pcmSha256=await sha(new Uint8Array(pcm.buffer));
    }else{
      for(const c of [a,b])c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:500000n,lowPs:500000n,
        transitionCount:40000n,knownUntilPs:20000000000n});
      for(let at=200000000n;at<=20000000000n;at+=200000000n){
        same(a.runUntilPs(at),b.runUntilPs(at),'Retirement count');const pins=a.drainPinsPs();same(pins,b.drainPinsPs(),'Every CLKI pin');observations+=pins.length;
      }
      if(b.r[20]!==0x5a||b._exports.avr_device_generation()!==2n||b.incrementalCompilation.compiled!==1)
        throw Error('Expected actual SPM and one affected compiled fragment');
    }
    const snapshot=c=>({state:c.state(),native:c._state,data:c.data,flash:c.rom,eeprom:c.eeprom,irq:c.irqFrames,
      control:c.controlRequest,watchdog:c.watchdogResetCycle,debug:c.debugEnabled});
    same(snapshot(a),snapshot(b),'Complete chip snapshot');same(a.transpiledBytes,b.transpiledBytes,'Portable artifact');
    if(b.state().deviceFault)throw Error('Device fault');
    self.postMessage({caseName,passed:true,irqs:b.state().irqs,cycles:b.state().cycles,observations,pcmSha256,
      snapshotSha256:await sha(new TextEncoder().encode(json(snapshot(b)))),
      translatedSha256:await sha(b.transpiledBytes),diagnostics:b.incrementalCompilation});
  }catch(e){self.postMessage({error:e.stack});}
};
