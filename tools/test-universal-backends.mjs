// Arithmetic conformance on the same AVR, including the explicitly selected C fallback.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-reference.js';
const load=name=>({meta:JSON.parse(fs.readFileSync('build/universal/engine-'+name+'.json')),
 binary:fs.readFileSync('build/universal/engine-'+name+'.bin')});
const variants=[load('c'),load('avr-asm')];
let random=0x774d31;
const next=()=>{random=(Math.imul(random,1664525)+1013904223)>>>0;return random;};
for(let test=0;test<512;test++){
 const count=1+next()%8,grouped=!!(test&1),states=[];
 let expectedL=0,sum=0;
 for(let i=0;i<count;i++){
  const phase=next()&65535,step=next()&16383,level=next()&15;
  const wave=Array.from({length:16},()=>grouped?next()%16-8:next()%81-40);
  const mix=grouped?(i===count-1?160|(test&2?1:0):0):128|(test&4?8:0)|(test&8?16:0);
  const output=wave[((phase+step)&65535)>>12];sum+=output;
  if(mix&128){const q=grouped?Math.floor(Math.floor(sum*level/8)/2**(mix&1)):sum;
   expectedL+=(mix&8)?Math.floor(q/2):q;sum=0;}
  states.push({phase,step,level,wave,mix});
 }
 const expected=expectedL&65535;
 check(states,expected,test);
}
function check(states,expected,label){
 const count=states.length;
 for(const {meta,binary} of variants){
  const core=new AVRCore(binary,new Uint8Array(64),{target:'attiny88',fastBlocks:false});
  const base=meta.labels.um-0x800000;
  core.data[base+216]=count;
  states.forEach((s,i)=>{
   const at=base+i*23;core.data[at]=s.phase;core.data[at+1]=s.phase>>8;
   core.data[at+2]=s.step;core.data[at+3]=s.step>>8;
   core.data.set(s.wave.map(v=>v&255),at+4);core.data[at+20]=s.level;core.data[at+22]=s.mix;
  });
  for(const r of [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29])core.r[r]=r+37;
  core.pushPC(0);core.pc=meta.labels.um_render/2;
  const start=core.cyc;
  do{core.step();assert.ok(core.cyc-start<20000);}while(core.pc!==0);
  const result=core.r[24]|core.r[25]<<8;
  assert.equal(result,expected,`${meta.backend}: signed mono mix case ${label}`);
  for(const r of [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29])assert.equal(core.r[r],r+37,'GCC callee-save register');
  assert.equal(core.r[1],0,'GCC zero register');assert.equal(core.sp,767);
  states.forEach((s,i)=>assert.equal(core.data[base+i*23]|core.data[base+i*23+1]<<8,(s.phase+s.step)&65535));
 }
}
for(let count=1;count<=8;count++)for(const value of [-128,-1,127])for(const mix of [128,136]){
 const states=Array.from({length:count},()=>({phase:65535,step:1,level:15,wave:Array(16).fill(value),mix}));
 check(states,(count*((mix&8)?Math.floor(value/2):value))&65535,`limits ${count}/${value}/${mix}`);
}
for(let level=0;level<16;level++)for(let q=-64;q<64;q++)for(const pan of [0,8])for(const attenuation of [0,1]){
 let value=Math.floor(Math.floor(q*level/8)/2**attenuation);if(pan)value=Math.floor(value/2);
 check([{phase:0,step:0,level,wave:Array(16).fill(q),mix:160|pan|attenuation}],value&65535,`gain ${q}/${level}/${pan}/${attenuation}`);
}
const digest=b=>createHash("sha256").update(b).digest("hex");
let cacheCases=0;
for(const {meta,binary} of variants){
 const image=new Uint8Array(8192);image.set(binary);
 const source=8000,target=600;image.fill(0,source,source+8);
 const core=new AVRCore(image,null,{target:'attiny88',fastBlocks:false});
 for(const raw of [false,true])for(let level=0;level<(raw?1:16);level++)for(let gain=0;gain<8;gain++)for(let packed=0;packed<256;packed++){
  // Only the unused Flash data tail changes; decoded instructions stay fixed.
  core.rom.fill(packed,source,source+8);
  core.data.fill(0xa5,target-1,target+17);
  core.r[24]=source&255;core.r[25]=source>>8;core.r[22]=target&255;core.r[23]=target>>8;
  core.r[20]=level;core.r[18]=gain|(raw?32:0);
  for(const r of [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29])core.r[r]=r+37;
  core.pushPC(0);core.pc=meta.labels.um_scale_wave/2;const start=core.cyc;
  do{core.step();assert.ok(core.cyc-start<10000);}while(core.pc!==0);
  for(let i=0;i<16;i++){
   const q=((i&1?packed>>4:packed)&15)-8;
   assert.equal(core.data[target+i],Math.floor(q*(raw?1:level)/2**gain)&255,`${meta.backend}: cached nibble ${packed}/${level}/${gain}/${raw}`);
  }
  assert.equal(core.data[target-1],0xa5);assert.equal(core.data[target+16],0xa5);
  for(const r of [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29])assert.equal(core.r[r],r+37);
  assert.equal(core.r[1],0);assert.equal(core.sp,767);cacheCases++;
 }
}
let irqCases=0;
for(const {meta,binary} of variants){
 const core=new AVRCore(binary,null,{target:'attiny88',fastBlocks:false});
 const at=name=>meta.labels[name]-0x800000,size=meta.pwmBufferFrames;
 assert.ok(Number.isInteger(size)&&size>=8&&size<=192);
 for(let read=0;read<size;read++)for(const empty of [false,true]){
  const frame=(read*73+19)&255;
  core.data[at('um_ring')+read]=frame;core.data[at('um_read')]=read;
  core.data[at('um_write')]=empty?read:(read+1)%size;core.data[at('um_underruns')]=255;
  core.data[core.profile.timer.ocrb]=83;
  for(let r=0;r<32;r++)core.r[r]=(r*17+read)&255;
  const saved=[...core.r],flags=(read*29)&127;core.sreg=flags;
  core.pushPC(0);core.pc=meta.labels['__vector_'+core.profile.timer.vector]/2;
  const start=core.cyc;do{core.step();assert.ok(core.cyc-start<256);}while(core.pc!==0);
  assert.deepEqual([...core.r],saved,meta.backend+': ISR registers including nonzero r1');
  assert.equal(core.sreg,flags|128);assert.equal(core.sp,767);
  assert.equal(core.data[at('um_read')],empty?read:(read+1)%size);
  assert.equal(core.data[at('um_underruns')],empty?0:255);
  assert.equal(core.data[core.profile.timer.ocrb],empty?83:frame);irqCases++;
 }
}
const report={cases:8752,exhaustiveGroupGainCases:8192,cacheCases:cacheCases/2,irqCases:irqCases/2,exactMonoIRQ:true,exactPhases:true,exactMonoMix:true,exactCachedWaves:true,abiPreserved:true,backends:variants.map(v=>({backend:v.meta.backend,bufferFrames:v.meta.pwmBufferFrames,engineSha256:digest(v.binary)}))};
fs.writeFileSync("ATtiny88/Music/universal/backend-verification.json",JSON.stringify(report,null,2)+"\n");
console.log("8752 C/ASM/reference mono mixes and 34816 cache cases per backend: exact phases, gain, waves and ABI");
