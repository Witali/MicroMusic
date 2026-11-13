import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {AVRCore} from '../../../../web-player/lib/avr-transpiled.js';
const folder=resolve(process.argv[2]||'build/avr25-math');
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const build=JSON.parse(readFileSync(folder+'/build.json','utf8'));
assert.equal(build.target,'attiny88');assert.equal(build.clock_hz,16000000);
assert.ok([1,2,4,8,16].includes(build.mul16_unroll),'Valid recorded multiply unroll factor');
const names=['c','asm','generic'];
const cpus=names.map(name=>{
 assert.equal(sha(`${folder}/${name}.bin`),build.backends[name].binary_sha256,`${name} built image`);
 const nm=readFileSync(`${folder}/${name}.nm`,'utf8');
 const sym=n=>parseInt(nm.split(/\r?\n/).find(l=>l.trim().endsWith(' '+n)).trim().split(/\s+/)[0],16)&65535;
 const cpu=new AVRCore(readFileSync(`${folder}/${name}.bin`),null,{target:'attiny88',cpuHz:16000000,
  fastIdle:false,fastBlocks:false,optimizeFlags:false,cacheTranslation:false});
 while(!cpu.data[sym('math_ready')]){cpu.step();assert.ok(cpu.cyc<20000);}
 return {cpu,sym,name};
});
const w16=(c,a,x)=>{c.data[a]=x;c.data[a+1]=x>>8;};
const w32=(c,a,x)=>{w16(c,a,x);w16(c,a+2,x>>16);};
const r32=(c,a)=>(c.data[a]|c.data[a+1]<<8|c.data[a+2]<<16|c.data[a+3]<<24);
let cases=0;
function check(kind,x,y,expected,{exc=0,t=0,bits=0,a=null,h=null}={}){
 for(const {cpu:c,sym:s,name} of cpus){
  c.data[s('math_kind')]=kind;c.data[s('math_t')]=t;c.data[s('math_bits')]=bits;
  w16(c,s('math_x'),x);w16(c,s('math_y'),y);w32(c,s('math_exc'),exc);
  if(a)a.forEach((v,i)=>w16(c,s('math_a')+i*2,v));
  if(h){
   for(let i=0;i<20;i++)w16(c,s('math_h')+i*2,0x5aa5+i);
   h.forEach((v,i)=>w16(c,s('math_h')+i*2,v));
  }
  const preserved=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29];
  preserved.forEach(r=>c.r[r]=(r*7+cases)&255);
  const sp=c.sp,before=c.cyc;c.pushPC(0);c.pc=s('math_case')/2;
  do{c.step();assert.ok(c.cyc-before<100000,`${name} call bound`);}while(c.pc!==0);
  assert.equal(r32(c,s('math_out')),expected|0,`${name} kind${kind} x${x} y${y} case${cases}`);
  assert.equal(c.r[1],0,`${name} zero register`);assert.equal(c.sp,sp,`${name} stack`);
  preserved.forEach(r=>assert.equal(c.r[r],(r*7+cases)&255,`${name} preserved r${r}`));
  if(h){
   const firstGuard=kind===25||kind===26?11:10;
   if(firstGuard===11)assert.equal((c.data[s('math_h')+20]|c.data[s('math_h')+21]<<8)&65535,h[9]&65535,'Discarded padded history');
   for(let i=firstGuard;i<20;i++)assert.equal((c.data[s('math_h')+i*2]|c.data[s('math_h')+i*2+1]<<8)&65535,0x5aa5+i,'History guard');
  }
  if(h)for(let i=1;i<10;i++)assert.equal((c.data[s('math_h')+i*2]|c.data[s('math_h')+i*2+1]<<8)&65535,h[i-1]&65535,'History consumed before shift');
 }
 cases++;
}
let seed=0x9a7711;
const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
const signed=()=>((random()>>>8)&65535)-32768;
const boundary=[-32768,-32767,-16384,-4096,-256,-129,-128,-1,0,1,127,128,255,256,4096,16384,32767];
for(const x of boundary)for(const y of boundary)check(0,x,y,x*y);
// Exercise carries and signed corrections around every bit, including the
// loop-group boundaries for compact 1/2/4/8-round multiplication bodies.
const carryPatterns=new Set([0x5555,0xaaaa,0x7fff,0x8000,0xffff]);
for(let bit=0;bit<16;bit++)
 for(const value of [1<<bit,(1<<bit)-1,(1<<bit)+1])carryPatterns.add(value&65535);
const signedPatterns=[...carryPatterns].map(value=>(value<<16)>>16);
for(const x of signedPatterns)for(const y of signedPatterns)check(0,x,y,x*y);
for(let i=0;i<1200;i++){
 const x=signed(),y=signed(),byte=(random()>>>24)-128,unsigned=random()&65535;
 check(0,x,y,x*y);check(1,byte,y,byte*y);check(2,byte,unsigned,byte*unsigned);
 const gain=random()%32,q=random()%64-32;
 check(3,q,gain,Math.floor((q*gain+8)/16));
 const coef=random()%16385;
 check(4,x,coef,Math.floor(x*coef/16384));
 const bits=2+random()%3,t=random()%((1<<bits)+1);
 check(5,x,y,x+Math.trunc((y-x)*t/(1<<bits)),{bits,t});
 const pwmGain=i&1?130:random()%256;
 check(6,x,pwmGain,Math.max(0,Math.min(255,128+Math.floor((x*pwmGain+8192)/16384))));
 for(const [kind,c]of [[9,13094],[10,64],[11,7800],[19,13926],[20,11469],
                     [21,1],[22,16383],[23,4096]])check(kind,x,0,Math.floor(x*c/16384));
 const wide=random()|0;
 check(12,0,0,Math.floor(wide/4096),{exc:wide});check(13,0,0,Math.floor(wide/16384),{exc:wide});
 check(14,0,y,(wide*y)|0,{exc:wide});
 check(15,x,y,Math.max(-32767,Math.min(32767,x+y)));
 if(i%3===0){
  const a=Array.from({length:10},signed),h=Array.from({length:10},signed);
  // Force the zero, unsigned-byte, signed-byte and full-word product routes.
  h[i%10]=[0,255,-128,-129,256,-32768][i%6];
  const exc=(random()%1048576)-524288;
  const expected=exc-a.reduce((sum,v,k)=>sum+Math.floor(v*h[k]/4096),0);
  check(7,0,0,expected,{a,h,exc:exc*16});
 }
}
for(const x of boundary)for(const gain of [0,1,64,127,128,130,255])
 check(6,x,gain,Math.max(0,Math.min(255,128+Math.floor((x*gain+8192)/16384))));
for(const x of boundary){
 check(16,x,0,Math.floor(x/2));check(17,x,0,0);check(18,x,0,x);
 for(const y of boundary){
  const a=Array(10).fill(x),h=Array(10).fill(y),exc=524287;
  check(7,0,0,exc-10*Math.floor(x*y/4096),{a,h,exc:exc*16});
 }
}
for(const value of [-3145728,-32769,-32768,-32767,-1,0,1,32767,32768,3145728])
 check(8,0,0,Math.max(-32767,Math.min(32767,value)),{exc:value});
for(let x=-32768;x<=32767;x++)check(24,x,0,Math.max(-16384,Math.min(16384,x)));
for(const x of boundary)for(const c of [0,1,63,64,65,8191,8192,8193,16383,16384])
 check(4,x,c,Math.floor(x*c/16384));
// Both hint states and all saturated-history signs, with nonzero coefficient
// low bytes that distinguish floor from truncation before the Q12 masking.
for(const first of [0,32767,-32767,32512,-32512])for(const history of [32767,-32767])
 for(const coefficient of boundary){
  const a=Array(10).fill(coefficient),h=Array(10).fill(history);h[0]=first;
  check(7,0,0,123-a.reduce((sum,v,k)=>sum+Math.floor(v*h[k]/4096),0),{a,h,exc:123*16});
 }
// Exact carry/floor boundaries of the signed high-byte addition route,
// both history layouts, both excitation units, and both saturation hints.
const splitHistory=[-32768,-32767,-2305,-2304,-2049,-2048,-2047,-1792,-1536,
 -1025,-1024,-769,-768,-513,-512,-257,-256,-255,-129,-128,-1,0,1,127,128,
 255,256,257,511,512,767,768,1023,1024,1536,1791,1792,2047,2048,2049,32767];
for(const coefficient of [...boundary,0x5555,-0x5555])for(const history of splitHistory){
 const a=Array(10).fill(coefficient),h=Array(10).fill(history);
 const expected=123-a.reduce((sum,v,k)=>sum+Math.floor(v*h[k]/4096),0);
 for(const kind of [7,25,26,27])check(kind,0,0,expected,{a,h,exc:kind===7||kind===25?123*16:123});
}
// The optimized pitch quotient also preserves the former full signed8
// input behavior, including the int8 result cast above the six-bit domain.
for(let x=-128;x<=127;x++)for(let gain=0;gain<=31;gain++){
 const expected=(Math.floor((x*gain+8)/16)<<24)>>24;
 check(3,x,gain,expected);
}
// Byte-shuffle PWM identity covers even values outside the decoder's Q14 clip.
for(let x=-32768;x<=32767;x++)
 check(6,x,130,Math.max(0,Math.min(255,128+Math.floor((x*130+8192)/16384))));
if(process.argv.includes('--exhaustive-synthesis')){
 // Batch nine independent products per call. Every signed16 history value
 // gets minimum/maximum/random coefficients, both T hints and both layouts.
 for(const hint of [0,32767])for(let first=-32768;first<=32767;first+=9)
  for(const coefficient of [-32768,32767,null]){
   const a=Array(10).fill(0),h=Array(10).fill(0);h[0]=hint;
   for(let i=1;i<10&&first+i-1<=32767;i++){
    h[i]=first+i-1;a[i]=coefficient===null?signed():coefficient;
   }
   const expected=123-a.reduce((sum,v,k)=>sum+Math.floor(v*h[k]/4096),0);
   for(const kind of [7,25])check(kind,0,0,expected,{a,h,exc:123*16});
  }
}
if(process.argv.includes('--exhaustive-dynamic')){
 for(let c=0;c<=16384;c++)for(const x of [-32768,-32767,-1,1,32767])
  check(4,x,c,Math.floor(x*c/16384));
 for(let x=-32768;x<=32767;x++)for(const c of [1,8191,8193,16383])
  check(4,x,c,Math.floor(x*c/16384));
}
if(process.argv.includes('--exhaustive-fixed'))
 for(let x=-32768;x<=32767;x++)
  for(const [kind,c]of [[9,13094],[11,7800],[19,13926],[20,11469],
                      [21,1],[22,16383],[23,4096]])check(kind,x,0,Math.floor(x*c/16384));
const results=[];
for(const {cpu,sym,name}of cpus){
 const irqs=cpu.data[sym('math_irqs')]|cpu.data[sym('math_irqs')+1]<<8;
 assert.ok(irqs>100,`${name} active IRQs`);
 assert.equal(cpu.lost,0,`${name} lost interrupts`);
 assert.equal(cpu.irqCount&65535,irqs,`${name} completed IRQs`);
 const result={backend:name,cases,irqs,cycles:cpu.cyc,passed:true};results.push(result);
 console.log(JSON.stringify(result));
}
assert.ok(readFileSync(folder+'/c.bin').equals(readFileSync(folder+'/generic.bin')),'Explicit generic retains the C image');
writeFileSync(folder+'/verification.json',JSON.stringify({target:'attiny88',clock_hz:16000000,
 mul16_unroll:build.mul16_unroll,cases,results,physical_board_measured:false,
 coverage:{pwm130_signed16_exhaustive:true,pitch_signed8_gain5_exhaustive:true,history_layouts:[10,11],
  synthesis_signed16_exhaustive:process.argv.includes('--exhaustive-synthesis'),
  attenuation_dynamic_exhaustive:process.argv.includes('--exhaustive-dynamic')},
 build_sha256:sha(folder+'/build.json'),
 math_header_sha256:sha(new URL('../src/Lpx4Math.h',import.meta.url)),
 multiply_header_sha256:sha(new URL('../src/Lpx4MultiplyAvr.h',import.meta.url)),
 probe_sha256:sha(new URL('./avr25_math.cpp',import.meta.url)),
 observer_sha256:sha(new URL('./verify_avr25_math.mjs',import.meta.url))},null,2)+'\n');
