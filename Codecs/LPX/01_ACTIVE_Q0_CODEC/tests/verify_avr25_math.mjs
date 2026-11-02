import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {AVRCore} from '../../../../web-player/lib/avr-transpiled.js';
const folder=resolve(process.argv[2]||'build/avr25-math');
const names=['c','asm','generic'];
const cpus=names.map(name=>{
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
  if(h)h.forEach((v,i)=>w16(c,s('math_h')+i*2,v));
  const preserved=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29];
  preserved.forEach(r=>c.r[r]=(r*7+cases)&255);
  const sp=c.sp,before=c.cyc;c.pushPC(0);c.pc=s('math_case')/2;
  do{c.step();assert.ok(c.cyc-before<100000,`${name} call bound`);}while(c.pc!==0);
  assert.equal(r32(c,s('math_out')),expected|0,`${name} kind${kind} x${x} y${y} case${cases}`);
  assert.equal(c.r[1],0,`${name} zero register`);assert.equal(c.sp,sp,`${name} stack`);
  preserved.forEach(r=>assert.equal(c.r[r],(r*7+cases)&255,`${name} preserved r${r}`));
  if(h)for(let i=1;i<10;i++)assert.equal((c.data[s('math_h')+i*2]|c.data[s('math_h')+i*2+1]<<8)&65535,h[i-1]&65535,'History consumed before shift');
 }
 cases++;
}
let seed=0x9a7711;
const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
const signed=()=>((random()>>>8)&65535)-32768;
const boundary=[-32768,-32767,-16384,-4096,-256,-129,-128,-1,0,1,127,128,255,256,4096,16384,32767];
for(const x of boundary)for(const y of boundary)check(0,x,y,x*y);
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
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
writeFileSync(folder+'/verification.json',JSON.stringify({target:'attiny88',clock_hz:16000000,
 cases,results,physical_board_measured:false,
 math_header_sha256:sha(new URL('../src/Lpx4Math.h',import.meta.url)),
 probe_sha256:sha(new URL('./avr25_math.cpp',import.meta.url)),
 observer_sha256:sha(new URL('./verify_avr25_math.mjs',import.meta.url))},null,2)+'\n');
