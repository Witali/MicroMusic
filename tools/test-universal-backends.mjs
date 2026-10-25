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
 let expectedL=0,expectedR=0,sum=0;
 for(let i=0;i<count;i++){
  const phase=next()&65535,step=next()&16383,level=next()&15;
  const wave=Array.from({length:16},()=>grouped?next()%16-8:next()%81-40);
  const mix=grouped?(i===count-1?160|(test&2?1:0):0):128|(test&4?8:0)|(test&8?16:0);
  const output=wave[((phase+step)&65535)>>12];sum+=output;
  if(mix&128){const q=grouped?Math.floor(Math.floor(sum*level/8)/2**(mix&1)):sum;
   expectedL+=(mix&8)?Math.floor(q/2):q;expectedR+=(mix&16)?Math.floor(q/2):q;sum=0;}
  states.push({phase,step,level,wave,mix});
 }
 const expected=((expectedL&65535)|((expectedR&65535)<<16))>>>0;
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
  do{core.step();assert.ok(core.cyc<20000);}while(core.pc!==0);
  const result=(core.r[22]|core.r[23]<<8|core.r[24]<<16|core.r[25]<<24)>>>0;
  assert.equal(result,expected,`${meta.backend}: wide signed mix case ${label}`);
  for(const r of [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29])assert.equal(core.r[r],r+37,'GCC callee-save register');
  assert.equal(core.r[1],0,'GCC zero register');assert.equal(core.sp,767);
  states.forEach((s,i)=>assert.equal(core.data[base+i*23]|core.data[base+i*23+1]<<8,(s.phase+s.step)&65535));
 }
}
for(let level=0;level<16;level++)for(let q=-64;q<64;q++){
 const value=Math.floor(q*level/8);
 const expected=((value&65535)|((value&65535)<<16))>>>0;
 check([{phase:0,step:0,level,wave:Array(16).fill(q),mix:160}],expected,`gain ${q}/${level}`);
}
const digest=b=>createHash("sha256").update(b).digest("hex");
const report={cases:2560,exhaustiveGroupGainCases:2048,exactPhases:true,exactWideMix:true,abiPreserved:true,backends:variants.map(v=>({backend:v.meta.backend,engineSha256:digest(v.binary)}))};
fs.writeFileSync("ATtiny88/Music/universal/backend-verification.json",JSON.stringify(report,null,2)+"\n");
console.log("2560 C/ASM/reference cases: exact phases, wide mix, exhaustive group gain and AVR ABI");
