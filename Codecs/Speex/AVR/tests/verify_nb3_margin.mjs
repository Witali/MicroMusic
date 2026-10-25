// Original Xiph interpolation/LPC; exact ASM RAM accesses, ABI and C fallback.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),bi=process.argv.indexOf('--backend');
const backend=bi<0?'asm':process.argv[bi+1];assert.ok(['asm','c'].includes(backend));
const fi=process.argv.indexOf('--firmware');
const dir=fi<0?join(root,'build/margin-unit-'+backend):resolve(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'lifetime.bin')),program=new Uint16Array(16384).fill(65535);
assert.ok(binary.length<=32768);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const status=address('margin_status'),command=address('margin_command'),subAddress=address('margin_sub');
const labels=['old','next','delta','raw_fused','raw_separate','lsp_actual','lsp_expected','coef_fused','coef_separate','coef_expected'];
const arrays=labels.map(n=>address('margin_'+n));
const [old,next,delta,rawF,rawS,lspActual,lspExpected,coefF,coefS,coefExpected]=arrays;
const arena=address('margin_arena'),work=address('margin_work'),pointers=address('margin_addresses');
const entries=new Map([...symbols].filter(([n])=>/^(?:speex_nb3_interpolate_lpc|speex_avr_nb3_advance10|lsp_to_lpc|margin_codebook|margin_advance|margin_advance_c)(?:\.|$)/.test(n)).map(([n,a])=>[a,n]));
assert.equal(symbols.has('speex_avr_nb3_advance10'),backend==='asm');assert.ok(entries.size>=4);
// GCC may fold the selected and forced-C wrappers to the same address.
for(const name of ['speex_nb3_interpolate_lpc','lsp_to_lpc','margin_codebook','margin_advance','margin_advance_c'])
 assert.ok([...symbols.keys()].some(n=>n===name||n.startsWith(name+'.')),name);
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29],active=[];
let retChecks=0,asmCalls=0,trace=null,asmWatch=false,workWatch=false,workReads=[],workWrites=[];
const cycleClasses=[new Set(),new Set(),new Set()];
const originalRead=cpu.readData,originalWrite=cpu.writeData;
cpu.readData=function(...args){if(asmWatch)trace.reads.push(args[0]);if(workWatch&&args[0]>=work&&args[0]<work+576)workReads.push(args[0]);return originalRead.apply(this,args);};
cpu.writeData=function(...args){if(asmWatch)trace.writes.push(args[0]);if(workWatch&&args[0]>=work&&args[0]<work+576)workWrites.push(args[0]);return originalWrite.apply(this,args);};
function get(p,i=0){return cpu.dataView.getInt16(p+2*i,true);}
function put(p,i,v){cpu.dataView.setInt16(p+2*i,v,true);}
function until(predicate){const deadline=cpu.cycles+1000000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'margin mailbox timeout');
 const name=entries.get(cpu.pc*2);
 if(name){active.push({name,sp:cpu.SP,regs:regs.map(r=>cpu.data[r])});
  if(name==='speex_avr_nb3_advance10'){
   assert.equal(trace,null);trace={raw:cpu.dataView.getUint16(24,true),delta:cpu.dataView.getUint16(22,true),center:cpu.dataView.getUint16(20,true),reads:[],writes:[],start:cpu.cycles};
  }
 }
 const ret=cpu.progMem[cpu.pc]===0x9508;asmWatch=trace!==null&&!ret;
 avrInstruction(cpu);cpu.tick();asmWatch=false;
 if(ret)while(active.length&&cpu.SP===active.at(-1).sp+2){
  const frame=active.pop();assert.deepEqual(regs.map(r=>cpu.data[r]),frame.regs);assert.equal(cpu.data[1],0);retChecks++;
  if(frame.name==='speex_avr_nb3_advance10'){
   const expectedReads=[],expectedWrites=[];
   for(let i=0;i<10;i++){
    expectedReads.push(trace.raw+2*i,trace.raw+2*i+1,trace.delta+2*i,trace.delta+2*i+1);
    expectedWrites.push(trace.raw+2*i,trace.raw+2*i+1);
    if(i===5)for(let k=0;k<6;k++)expectedWrites.push(trace.center+k);
   }
   assert.deepEqual(trace.reads,expectedReads,'Exactly 20 raw and 20 delta bytes read');
   assert.deepEqual(trace.writes,expectedWrites,'Exactly 20 raw and six center bytes written');
   const mask=(get(trace.center)!==get(trace.raw,3)?1:0)|(get(trace.center,2)!==get(trace.raw,5)?2:0);
   assert.ok(mask<3);cycleClasses[mask].add(cpu.cycles-trace.start);asmCalls++;trace=null;
  }
 }
 assert.ok(cpu.SP>=address('__bss_end'),'Stack/static collision');
}}
function issue(n){cpu.data[status]=1;cpu.data[command]=n;until(()=>cpu.data[status]===2);assert.equal(active.length,0);}
function guards(){for(const p of arrays){put(p,0,0x1357);put(p,11,0x2468);}}
function checkGuards(){for(const p of arrays){assert.equal(get(p),0x1357);assert.equal(get(p,11),0x2468);}}
let seed=0x1973a44d,cases=0,calls=0;const masks=[0,0,0,0];
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
const source=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/lsp_tables_nb.c'),'utf8');
function table(n,len){const a=source.match(new RegExp(n+'\\[\\d+\\]=\\{([^}]+)\\}'))[1].split(',').filter(s=>s.trim()).map(Number);assert.equal(a.length,len);return a;}
const base=table('cdbk_nb',640),low=table('cdbk_nb_low1',320),high=table('cdbk_nb_high1',320);
function angles(code){const a=code>>>12,b=(code>>>6)&63,c=code&63;return Array.from({length:10},(_,i)=>(i+1)*2048+32*base[10*a+i]+16*(i<5?low[5*b+i]:high[5*c+i-5]));}
const groups=[[],[],[]];
for(let code=0;code<(1<<18);code++){
 const a=angles(code),mask=(a[3]>a[4]-16?1:0)|(a[4]>a[5]-16?2:0);assert.ok(mask<3);groups[mask].push(code);
}
assert.equal(groups[1].length,1088);assert.equal(groups[2].length,3593);
until(()=>cpu.data[status]===1);
function check(a,b,count=4){
 guards();for(let i=0;i<10;i++){put(old,i+1,a[i]);put(next,i+1,b[i]);}issue(1);
 const step=a.map((v,i)=>(b[i]-v)/4);
 for(let sub=0;sub<count;sub++){
  cpu.data.fill(0x69,arena,arena+712);issue(2);assert.equal(cpu.data[subAddress],sub+1);
  for(let i=0;i<10;i++){
   assert.equal(get(lspActual,i+1),get(lspExpected,i+1));
   assert.equal(get(coefF,i+1),get(coefExpected,i+1));assert.equal(get(coefS,i+1),get(coefExpected,i+1));
   assert.equal(get(rawF,i+1),a[i]+(sub+1)*step[i]);assert.equal(get(rawS,i+1),get(rawF,i+1));
   assert.equal(get(delta,i+1),step[i]);assert.equal(get(old,i+1),a[i]);assert.equal(get(next,i+1),b[i]);
   assert.equal(get(rawF,i+1)&3,0);assert.equal(get(lspExpected,i+1)&1,0);
  }
  const mask=(get(lspExpected,4)!==get(rawF,4)?1:0)|(get(lspExpected,6)!==get(rawF,6)?2:0);
  assert.ok(mask<3);masks[mask]++;
  for(const offset of [0,1,2,3,708,709,710,711])assert.equal(cpu.data[arena+offset],0x69,'Original Xiph workspace guard');
  checkGuards();calls++;
 }
 cases++;
}
for(let n=0;n<1024;n++)check(angles(random()&0x3ffff),angles(random()&0x3ffff));
for(let group=1;group<=2;group++)for(let n=0;n<256;n++)check(angles(groups[group][(n*7+3)%groups[group].length]),angles(groups[group][(n*11+1)%groups[group].length]));
for(let n=0;n<64;n++){const a=angles(random()&0x3ffff);check(a,a,1);}
assert.equal(cases,1600);assert.equal(calls,6208);assert.ok(masks[0]&&masks[1]&&masks[2]&&!masks[3]);
const page=Math.ceil((work+16)/256)*256;let addressCases=0;
for(let group=0;group<3;group++)for(let phase=1;phase<=4;phase++)for(let offset=0;offset<256;offset++){
 const a=angles(groups[group][(offset*13+phase*11)%groups[group].length]);
 const b=angles(groups[group][(offset*17+phase*7+1)%groups[group].length]);
 const step=a.map((v,i)=>(b[i]-v)/4),before=a.map((v,i)=>v+(phase-1)*step[i]),after=a.map((v,i)=>v+phase*step[i]);
 guards();for(let i=0;i<10;i++){put(old,i+1,a[i]);put(next,i+1,b[i]);}cpu.data[subAddress]=phase-1;issue(5);
 const center=Array.from({length:3},(_,i)=>get(lspExpected,4+i));
 const rp=page+offset,dp=page+((offset+64)&255),op=page+((offset+128)&255);
 assert.ok(rp>=work+16&&rp+20<=work+576-16&&dp+20<=work+576-16&&op+6<=work+576-16);
 const inputSet=new Set([...Array.from({length:20},(_,i)=>rp+i),...Array.from({length:20},(_,i)=>dp+i)]);
 const outputSet=new Set([...Array.from({length:20},(_,i)=>rp+i),...Array.from({length:6},(_,i)=>op+i)]);
 for(const mode of [3,4]){
  cpu.data.fill(0x69,work,work+576);for(let i=0;i<10;i++){put(rp,i,before[i]);put(dp,i,step[i]);}
  const expected=cpu.data.slice(work,work+576);
  for(let i=0;i<10;i++)new DataView(expected.buffer).setInt16(rp-work+2*i,after[i],true);
  for(let i=0;i<3;i++)new DataView(expected.buffer).setInt16(op-work+2*i,center[i],true);
  for(const [i,p] of [rp,dp,op].entries())cpu.dataView.setUint16(pointers+2*i,p,true);
  workReads=[];workWrites=[];workWatch=true;issue(mode);workWatch=false;
  assert.deepEqual(cpu.data.slice(work,work+576),expected,'Only ten raw and three center words may change');
  for(const a of workReads)assert.ok(inputSet.has(a));for(const a of workWrites)assert.ok(outputSet.has(a));
  assert.equal(new Set(workReads).size,40);assert.equal(new Set(workWrites).size,26);checkGuards();
 }
 addressCases++;
}
assert.equal(addressCases,3072);assert.equal(asmCalls,backend==='asm'?calls+addressCases:0);
assert.equal(retChecks,calls*(backend==='asm'?4:3)+addressCases*(backend==='asm'?3:2));
if(backend==='asm')for(const set of cycleClasses)assert.equal(set.size,1);
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',backend,
 binarySha256:createHash('sha256').update(binary).digest('hex'),cases,calls,repairMasks:masks,
 addressCases,all256LowBytesAtEachRepairClassAndQuarter:true,oddAndPageCrossingPointers:true,
 selectorAndForcedCExact:true,selectedAndForcedCWrappersShareAddress:symbols.get('margin_advance')===symbols.get('margin_advance_c'),
 fusedAndSeparateExactAgainstUntouchedXiph:true,rawStateExact:true,
 exactAsmReadAndWriteAddresses:backend==='asm',asmCalls,asmReadBytes:40*asmCalls,asmWrittenBytes:26*asmCalls,
 primitiveCyclesByRepairClass:cycleClasses.map(s=>[...s]),guardsAndInputsPreserved:true,
 originalOracleWorkspaceGuarded:true,calleeSavedRegistersAtRet:true,zeroRegisterAtRet:true,retChecks,
 includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
