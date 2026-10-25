// Execute the actual UM88 firmware with interrupts active, through a full loop.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {AVRCore} from '../web-player/lib/avr-core.js';
const root=fileURLToPath(new URL('../',import.meta.url));
const word=(b,p)=>b[p]|b[p+1]<<8;
const signed=v=>v&128?v-256:v;
const sha=b=>createHash('sha256').update(b).digest('hex');
const readJSON=p=>JSON.parse(fs.readFileSync(p));
const step=(source,cpu)=>{
 if(!source)return 0;
 const note=Math.round(69+12*Math.log2((source&32767)*15625/65536/440));
 return Math.round(440*2**((note-69)/12)*65536/(cpu/1024));
};
export function audit(name,{directory=path.join(root,'ATtiny88/Music/universal/songs')}={}){
 const folder=path.join(directory,name);
 const meta=readJSON(path.join(folder,'build-report.json'));
 const tape=readJSON(path.join(root,'build/universal',name+'.tape.json'));
 const rom=fs.readFileSync(path.join(folder,'synth.bin')),ep=fs.readFileSync(path.join(folder,'eeprom.bin'));
 assert.equal(sha(rom),meta.flashSha256);
 const c=new AVRCore(rom,ep,{target:'attiny88'});
 const state=meta.labels.um-0x800000,read=meta.labels.um_read-0x800000,write=meta.labels.um_write-0x800000;
 const render=meta.labels.um_render/2,irq=meta.labels.__vector_11/2;
 const returnPCs=new Set();
 for(let pc=0;pc<meta.engineBytes/2;pc++)if(c.op[pc]===6&&pc+1+c.k[pc]===render)returnPCs.add(pc+1);
 assert.ok(returnPCs.size);
 const hooks=new Set([render,irq,...returnPCs]);for(const p of hooks)c.batch[p]=0;
 const phases=new Array(meta.voices).fill(0);
 let ticks=-1,frame=-1,loops=0,samples=0,minQueued=64,maxRender=0,startRender=0,startIrqs=0;
 let expectedMix=0,checkedWaves=0,checkedPhases=0,observedIRQs=0,done=false;
 const start=performance.now();
 while(!done&&c.cyc<meta.cpuHz*(meta.controlTicks/(18750/256)+1)){
  if(!c.inIRQ&&c.pc===render){
   startRender=c.cyc;startIrqs=c.irqCount;
   const tick=word(c.data,state+212);
   if(tick!==ticks){
    if(tick===0&&ticks>0){loops++;frame=0;phases.fill(0);}else {frame=tick;}
    assert.ok(frame<meta.controlTicks,`${name}: control frame within song`);
    const f=tape.frames[frame];
    if(frame>0){const before=[...phases];f.phaseOps.forEach((from,i)=>{phases[i]=from<0?0:before[from];});}
    for(let i=0;i<meta.voices;i++){
     const at=state+i*23,expected=f.voices[i];
     assert.equal(c.data[at+20],expected.envelope&15,`${name}: level at tick ${frame}, voice ${i}`);
     assert.equal(word(c.data,at+2),step(expected.step,meta.cpuHz),`${name}: pitch at tick ${frame}, voice ${i}`);
     // Verify each cached waveform against packed source timbres and exact products.
     const context=meta.contexts[c.data[at+21]],bank=context[1]|((context[2]&64)&&(expected.envelope&15)>=14?48:0);
     let level=expected.envelope&15;if(context[2]&128)level>>=1;
     if(context[2]&16)level>>=1;
     for(let p=0;p<16;p++){
      const packed=ep[bank+(p>>1)],q=((p&1?packed>>4:packed)&15)-8;
      const value=((context[2]&32)?q:Math.floor(q*level/2**(context[2]&7)))||0;
      assert.equal(signed(c.data[at+4+p]),value,`${name}: waveform tick ${frame}, voice ${i}`);checkedWaves++;
     }
    }
    ticks=tick;
    if(loops&&tick>=2){done=true;break;}
   }
   let l=0,r=0,group=0;
   for(let i=0;i<meta.voices;i++){
    const at=state+i*23;
    assert.equal(word(c.data,at),phases[i],`${name}: DDS phase voice ${i} at frame ${frame}`);checkedPhases++;
    phases[i]=(phases[i]+word(c.data,at+2))&65535;
    group+=signed(c.data[at+4+(phases[i]>>12)]);
    const flags=c.data[at+22];
    if(flags&128){
     let value;
     if(flags&32)value=Math.floor(Math.floor(group*c.data[at+20]/8)/2**(flags&1));
     else value=Math.floor(group/2**(flags&7));
     group=0;l+=(flags&8)?Math.floor(value/2):value;r+=(flags&16)?Math.floor(value/2):value;
    }
   }
   assert.ok(l>=-1024&&l<=1023&&r>=-1024&&r<=1023,`${name}: wide mixer range`);
   expectedMix=((l&65535)|((r&65535)<<16))>>>0;samples++;
  }else if(!c.inIRQ&&returnPCs.has(c.pc)){
   assert.equal((c.r[22]|c.r[23]<<8|c.r[24]<<16|c.r[25]<<24)>>>0,expectedMix,`${name}: C/reference tonal mix`);
   maxRender=Math.max(maxRender,c.cyc-startRender-(c.irqCount-startIrqs)*c.maxIRQ);
  }else if(c.pc===irq){
   observedIRQs++;
   const queued=((c.data[write]-c.data[read]+192)%192)/2;
   assert.ok(queued>0,`${name}: PWM FIFO underrun at ${c.cyc/meta.cpuHz} s, frame ${frame}`);
   minQueued=Math.min(minQueued,queued);
  }
  if(!c.runBlock())c.step();
 }
 assert.ok(done,`${name}: full playback and restart`);
 assert.equal(c.data[meta.labels.um_underruns-0x800000],0);
 assert.equal(c.lost,0);assert.equal(c.workLost,0);
 const staticEnd=meta.labels.__bss_end-0x800000;
 assert.ok(c.minSP>=meta.labels.um_ring-0x800000+192,'Stack remains above all state and the audio FIFO');
 const report={variant:name,cpuHz:meta.cpuHz,backend:meta.backend,engineSha256:meta.engineSha256,flashSha256:meta.flashSha256,eepromSha256:meta.eepromSha256,
  simulatedSeconds:c.cyc/meta.cpuHz,controlFrames:meta.controlTicks,completeLoops:loops,
  samples,observedIRQs,checkedPhases,checkedWaveSamples:checkedWaves,minimumQueuedFrames:minQueued,
  maxRenderActiveCycles:maxRender,maxISRCycles:c.maxIRQ,fifoUnderruns:0,lostInterrupts:c.lost,
  minimumStackPointer:c.minSP,stackBytes:767-c.minSP,staticStateEnd:staticEnd,
  allControlFramesMatch:true,allTonalMixesMatch:true,hardwareTested:false,wallSeconds:(performance.now()-start)/1000};
 fs.writeFileSync(path.join(folder,'verification.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report));return report;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=process.argv.slice(2),option=args.find(a=>a.startsWith('--directory='));
 const directory=option?path.resolve(option.slice(12)):path.join(root,'ATtiny88/Music/universal/songs');
 const names=args.filter(a=>a!==option);const folders=fs.readdirSync(directory).filter(n=>fs.statSync(path.join(directory,n)).isDirectory());
 for(const name of names.length?names:folders)audit(name,{directory});
}
