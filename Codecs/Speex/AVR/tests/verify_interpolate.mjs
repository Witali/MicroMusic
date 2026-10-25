// Compare quarter steps against untouched Xiph lsp.c executed on AVR as well.
// This preserves AVR's 16-bit int promotions even on deliberately invalid LSPs.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=join(root,'build/quarter-unit');
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'quarter.bin')),program=new Uint16Array(16384).fill(65535);
assert.ok(binary.length<=32768);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),command=address('quarter_command'),status=address('quarter_status');
const arrays=['old','next','raw','delta','out','expected'].map(n=>address('quarter_'+n));
const [oldAddress,nextAddress,rawAddress,deltaAddress,outAddress,expectedAddress]=arrays;
function until(predicate){const end=cpu.cycles+100000;while(!predicate()){
  assert.ok(cpu.cycles<end,'quarter mailbox timeout');avrInstruction(cpu);cpu.tick();
}}
function issue(n){cpu.data[status]=1;cpu.data[command]=n;until(()=>cpu.data[status]===2);}
function put(p,i,v){cpu.dataView.setInt16(p+2+2*i,v,true);}
function get(p,i){return cpu.dataView.getInt16(p+2+2*i,true);}
let seed=0x8b251e7d;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function signed(v){return v<<16>>16;}
let cases=0,calls=0;
until(()=>cpu.data[status]===1);
function check(old,next,count=4){
  for(const p of arrays){cpu.dataView.setUint16(p,0x1357,true);cpu.dataView.setUint16(p+22,0x2468,true);}
  for(let i=0;i<10;i++){assert.equal(old[i]&15,0);assert.equal(next[i]&15,0);put(oldAddress,i,old[i]);put(nextAddress,i,next[i]);}
  issue(1);
  const delta=old.map((v,i)=>(next[i]-v)/4);
  for(let sub=0;sub<count;sub++){
    issue(2);assert.equal(cpu.data[address('quarter_sub')],sub+1);
    for(let i=0;i<10;i++){
      assert.equal(get(outAddress,i),get(expectedAddress,i),`case ${cases}, sub ${sub}, angle ${i}`);
      assert.equal(get(rawAddress,i),old[i]+(sub+1)*delta[i],'Unclamped interpolation state');
      assert.equal(get(deltaAddress,i),delta[i],'Read-only step');
      assert.equal(get(oldAddress,i),old[i],'Read-only old endpoint');
      assert.equal(get(nextAddress,i),next[i],'Read-only new endpoint');
    }
    for(const p of arrays){
      assert.equal(cpu.dataView.getUint16(p,true),0x1357,'prefix guard');
      assert.equal(cpu.dataView.getUint16(p+22,true),0x2468,'suffix guard');
    }
    assert.equal(cpu.data[1],0,'GCC zero register after C calls');calls++;
  }
  if(count===4 || old.every((v,i)=>v===next[i]))
    for(let i=0;i<10;i++)assert.equal(get(rawAddress,i),next[i],'Final raw endpoint');
  cases++;
}
// Construct real codebook endpoints using the pinned upstream quant_lsp.c
// equation. The native primitive test exhausts all 262144 triples as well.
const tables=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/lsp_tables_nb.c'),'utf8');
function table(name,length){const a=tables.match(new RegExp(name+'\\[\\d+\\]=\\{([^}]+)\\}'))[1].split(',').filter(s=>s.trim()).map(Number);assert.equal(a.length,length);return a;}
const base=table('cdbk_nb',640),low=table('cdbk_nb_low1',320),high=table('cdbk_nb_high1',320);
function angles(code){const a=code>>>12,b=(code>>>6)&63,c=code&63;return Array.from({length:10},(_,i)=>(i+1)*2048+32*base[a*10+i]+16*(i<5?low[b*5+i]:high[c*5+i-5]));}
let previous=Array(10).fill(0);
for(let n=0;n<4096;n++){const next=angles(random()&0x3ffff);check(previous,next);previous=next;}
for(let n=0;n<512;n++){const a=angles(random()&0x3ffff);check(a,a,1);}
for(let n=0;n<16384;n++)check(Array.from({length:10},()=>signed(random()&0xfff0)),Array.from({length:10},()=>signed(random()&0xfff0)));
const edge=[-32768,-32752,-16,0,16,25712,25728,32752];
for(let n=0;n<64;n++)check(Array.from({length:10},(_,i)=>edge[((n>>>3)+i)%8]),Array.from({length:10},(_,i)=>edge[(n%8+9-i)%8]));
assert.equal(cases,21056);assert.equal(calls,82688);
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',backend:'c',
  compiler:'AVR GCC 7.3.0; -Os -flto -mcall-prologues -mrelax -fwrapv; helper O3',
  binarySha256:createHash('sha256').update(binary).digest('hex'),
  cases,calls,angleComparisons:10*calls,codebookTransitions:4096,resetCases:512,
  fullSignedMultiples16Transitions:16384,edgeTransitions:64,
  exactAgainstUntouchedXiphOnAvr:true,rawQuarterStateExact:true,finalRawEndpointExact:true,
  guardsIntact:true,deltaAndEndpointsPreserved:true,zeroRegisterRestored:true,
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
