// Untouched non-LTO Xiph and production C/ASM math, including overlapping output.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url));
const bi=process.argv.indexOf('--backend'),backend=bi<0?'c':process.argv[bi+1];assert.ok(['asm','c'].includes(backend));
const dir=join(root,'build/lifetime-unit-'+backend);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'lifetime.bin')),program=new Uint16Array(16384).fill(65535);
assert.ok(binary.length<=32768);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),command=address('lifetime_command'),status=address('lifetime_status');
const arrays=['old','next','raw','delta','out','expected'].map(n=>address('lifetime_'+n));
const [old,next,raw,delta,out,expected]=arrays,space=address('lifetime_space');
const arena=address('lifetime_arena');
const entries=new Set([...symbols].filter(([n])=>n==='lifetime_interpolate'||n.startsWith('lifetime_interpolate.')||n==='lsp_to_lpc'||n.startsWith('lsp_to_lpc.')).map(([,a])=>a));
assert.ok(entries.size>=2);
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29];let active=null,retChecks=0;
function until(predicate){const deadline=cpu.cycles+500000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'LSP lifetime timeout');
 if(entries.has(cpu.pc*2)){assert.equal(active,null);active={sp:cpu.SP,regs:regs.map(r=>cpu.data[r])};}
 const ret=cpu.progMem[cpu.pc]===0x9508;avrInstruction(cpu);cpu.tick();
 if(active&&ret&&cpu.SP===active.sp+2){assert.deepEqual(regs.map(r=>cpu.data[r]),active.regs);assert.equal(cpu.data[1],0);active=null;retChecks++;}
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
function issue(n){cpu.data[status]=1;cpu.data[command]=n;until(()=>cpu.data[status]===2);assert.equal(active,null);}
function put(p,i,v){cpu.dataView.setInt16(p+2*i,v,true);}
function get(p,i){return cpu.dataView.getInt16(p+2*i,true);}
function guards(){for(const p of arrays){put(p,0,0x1357);put(p,11,0x2468);}}
function checkGuards(){for(const p of arrays){assert.equal(get(p,0),0x1357);assert.equal(get(p,11),0x2468);}}
let seed=0x83b4d027,cases=0,calls=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function signed(n){return n<<16>>16;}
until(()=>cpu.data[status]===1);
function check(a,b,count=4){
 guards();for(let i=0;i<10;i++){assert.equal(a[i]&15,0);assert.equal(b[i]&15,0);put(old,i+1,a[i]);put(next,i+1,b[i]);}
 issue(1);const step=a.map((v,i)=>(b[i]-v)/4);
 for(let sub=0;sub<count;sub++){
  assert.ok(a[0]+(sub+1)*step[0]>=16&&a[9]+(sub+1)*step[9]<=25720);
  issue(2);assert.equal(cpu.data[address('lifetime_sub')],sub+1);
  for(let i=0;i<10;i++){
   assert.equal(get(out,i+1),get(expected,i+1),`bounded case ${cases} sub ${sub} angle ${i}`);
   assert.equal(get(raw,i+1),a[i]+(sub+1)*step[i]);assert.equal(get(delta,i+1),step[i]);
   assert.equal(get(old,i+1),a[i]);assert.equal(get(next,i+1),b[i]);
  }
  checkGuards();calls++;
 }
 cases++;
}
const source=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/lsp_tables_nb.c'),'utf8');
function table(n,len){const a=source.match(new RegExp(n+'\\[\\d+\\]=\\{([^}]+)\\}'))[1].split(',').filter(s=>s.trim()).map(Number);assert.equal(a.length,len);return a;}
const base=table('cdbk_nb',640),low=table('cdbk_nb_low1',320),high=table('cdbk_nb_high1',320);
function angles(code){const a=code>>>12,b=(code>>>6)&63,c=code&63;return Array.from({length:10},(_,i)=>(i+1)*2048+32*base[a*10+i]+16*(i<5?low[b*5+i]:high[c*5+i-5]));}
let previous=angles(0);
for(let n=0;n<4096;n++){const a=angles(random()&0x3ffff);check(previous,a);previous=a;}
for(let n=0;n<512;n++){const a=angles(random()&0x3ffff);check(a,a,1);}
for(let n=0;n<8192;n++){
 const a=Array.from({length:10},()=>signed(random()&0xfff0)),b=Array.from({length:10},()=>signed(random()&0xfff0));
 for(const i of [0,9]){a[i]=16+16*(random()%1607);b[i]=16+16*(random()%1607);}check(a,b);
}
for(let n=0;n<4;n++){
 const a=Array.from({length:10},(_,i)=>i&1?32752:-32768),b=a.map(v=>v===32752?-32768:32752);
 a[0]=n&1?16:0;b[0]=n&1?16:64;a[9]=n&2?25712:25728;b[9]=n&2?25712:25696;check(a,b);
}
assert.equal(cases,12804);assert.equal(calls,49680);
for(let n=0;n<4096;n++){
 guards();let a=Array.from({length:10},()=>n<3072?random()%25737:signed(random()));
 if(n<2048)a.sort((x,y)=>x-y);
 if(n<64){const edge=[-32768,-16,0,16,8192,12868,25720,32767];a=Array.from({length:10},(_,i)=>edge[(i&1)?n>>>3:n&7]);a[2]=edge[n>>>3];a[3]=edge[n&7];}
 cpu.data.fill(0x69,arena,arena+712);
 for(let i=0;i<10;i++)put(old,i+1,a[i]);issue(3);checkGuards();
 for(const offset of [0,1,2,3,708,709,710,711])assert.equal(cpu.data[arena+offset],0x69,'Oracle arena guard');
 const savedArena=cpu.data.slice(arena,arena+712);
 const coefficients=Array.from({length:10},(_,i)=>get(expected,i+1));
 for(let i=0;i<10;i++){assert.equal(get(old,i+1),a[i]);assert.equal(get(out,i+1),coefficients[i]);}
 for(const offset of [-1,0,1]){
  const before=Array(24).fill(0x4b6d);for(let i=0;i<10;i++)before[i+5]=a[i];
  for(let i=0;i<24;i++)put(space,i,before[i]);cpu.data[address('lifetime_offset')]=offset&255;issue(4);
  for(let i=0;i<24;i++)assert.equal(get(space,i),i>=5+offset&&i<15+offset?coefficients[i-5-offset]:before[i],`LPC ${n} offset ${offset} lane ${i}`);
  checkGuards();
  assert.deepEqual(cpu.data.slice(arena,arena+712),savedArena,'Production uses no oracle arena');
 }
}
assert.equal(retChecks,calls+4*4096);
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',backend,
 binarySha256:createHash('sha256').update(binary).digest('hex'),
 oracle:'Untouched Xiph lsp.c in separate non-LTO object; production compact LSP with real C/ASM math',
 boundedCases:cases,boundedCalls:calls,codebookTransitions:4096,resetCases:512,
 fullSignedInteriorTransitions:8192,exactEndpointBoundaryCases:4,lpcInputs:4096,
 overlappingLpcOutputs:12288,disjointLpcOutputs:4096,aliasOffsets:[-1,0,1],
 exactAgainstUntouchedXiphOnAvr:true,rawQuarterStateExact:true,deltaAndEndpointsPreserved:true,
 memoryOutsideLpcOutputPreserved:true,oracleArenaGuardsIntact:true,guardsIntact:true,calleeSavedRegistersAtRet:true,
 zeroRegisterAtRet:true,retChecks,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
