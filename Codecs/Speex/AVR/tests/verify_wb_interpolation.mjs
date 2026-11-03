// Isolated AVR C interpolation candidates, not a Speex decoder execution.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU, avrInstruction} from 'avr8js';

const root=fileURLToPath(new URL('../',import.meta.url)),base=resolve(process.argv[2]);
const recipes=['original-loop-switch','difference-loop-switch','difference-unswitched',
 'finite-loop-margin','finite-unrolled-margin','shared-quarter-loop','shared-quarter-finite-margin'];
const text=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/high_lsp_tables.c'),'utf8');
const tables=['high_lsp_cdbk','high_lsp_cdbk2'].map(name=>{
 const body=text.match(new RegExp('\\b'+name+'\\[512\\]\\s*=\\s*\\{([\\s\\S]*?)\\}'))?.[1];
 assert.ok(body,name);const words=body.match(/-?\d+/g).map(Number);assert.equal(words.length,512);
 return Array.from({length:64},(_,i)=>words.slice(8*i,8*i+8));
});
const endpoints=[];
for(const a of tables[0])for(const b of tables[1])
 endpoints.push(Array.from({length:8},(_,i)=>6144+2560*i+32*a[i]+16*b[i]));
function model(old,next,sub){
 const f=4096*(sub+1),x=old.map((a,i)=>Math.floor((a*(16384-f)+8192)/16384)+Math.floor((next[i]*f+8192)/16384));
 if(x[0]<410)x[0]=410;if(x[7]>25326)x[7]=25326;
 for(let i=1;i<7;i++){
  if(x[i]<x[i-1]+410)x[i]=x[i-1]+410;
  if(x[i]>x[i+1]-410)x[i]=Math.floor(x[i]/2)+Math.floor((x[i+1]-410)/2);
 }
 return x;
}
const cases=[];
for(let i=0;i<4096;i++)for(let sub=0;sub<4;sub++)
 cases.push({old:endpoints[(i*4051+113)&4095],next:endpoints[i],sub});
for(let i=0;i<4096;i+=31)for(let sub=0;sub<4;sub++)cases.push({old:endpoints[i],next:endpoints[i],sub});
for(let i=0;i<8;i++){
 const sorted=[...endpoints].sort((a,b)=>a[i]-b[i]);
 for(const old of [sorted[0],sorted.at(-1)])for(const next of [sorted[0],sorted.at(-1)])
  for(let sub=0;sub<4;sub++)cases.push({old,next,sub});
}
const summary={scope:'Isolated AVR C recipes; no full C decoder execution, no IRQ admission',
 physicalBoardTested:false, includesInterrupts:false,cases:cases.length,recipes:[]};
let baseline=null;
for(const recipe of recipes){
 const dir=join(base,recipe),binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json'),'utf8'));
 assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
 assert.equal(meta.recipe,recipe);
 for(const [name,sha] of Object.entries(meta.sourceSha256))
  assert.equal(createHash('sha256').update(readFileSync(join(root,name)).toString('utf8').replaceAll('\r\n','\n')).digest('hex'),sha,name);
 const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/))
  .filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
 const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
 const [oldAt,nextAt,work,outPointer,subAt,command,status,end,entry]=[
  'probe_old','probe_new','probe_work','probe_out','probe_sub','probe_command','probe_status','__bss_end','wb_probe_interpolate'].map(at);
 const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
 const cpu=new CPU(program,2048),saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
 let active=null,lastCycles=null,returns=0,ownStack=0,minSP=2303;
 function until(done){const deadline=cpu.cycles+5000;while(!done()){
  assert.ok(cpu.cycles<deadline,'interpolation timeout');
  if(cpu.pc*2===entry){
   assert.equal(active,null);assert.equal(cpu.data[1],0);
   const original=saved.map(r=>cpu.data[r]),patterns=saved.map(r=>(returns*73+r*29)&255);
   saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
   active={sp:cpu.SP,start:cpu.cycles,original,patterns};
  }
  const opcode=cpu.progMem[cpu.pc];avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);
  assert.ok(cpu.SP>=end,'SRAM collision');
  if(active)ownStack=Math.max(ownStack,active.sp-cpu.SP);
  if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
   assert.deepEqual(saved.map(r=>cpu.data[r]),active.patterns);assert.equal(cpu.data[1],0);
   lastCycles=cpu.cycles-active.start;saved.forEach((r,i)=>{cpu.data[r]=active.original[i];});
   active=null;returns++;
  }
 }}
 until(()=>cpu.data[status]===1);
 const timings=[],perQuarter=Array.from({length:4},()=>[]);
 for(let i=0;i<cases.length;i++){
  const {old,next,sub}=cases[i],out=work+16+(i&255),expected=model(old,next,sub);
  cpu.data.fill(0xa5,work,work+320);
  old.forEach((v,j)=>cpu.dataView.setInt16(oldAt+2*j,v,true));next.forEach((v,j)=>cpu.dataView.setInt16(nextAt+2*j,v,true));
  cpu.dataView.setUint16(outPointer,out,true);cpu.data[subAt]=sub;
  const before=cpu.data.slice(256,end);
  cpu.data[status]=1;cpu.data[command]=1;lastCycles=null;until(()=>cpu.data[status]===2);
  assert.equal(active,null);assert.notEqual(lastCycles,null);
  assert.deepEqual(Array.from({length:8},(_,j)=>cpu.dataView.getInt16(out+2*j,true)),expected,`${recipe} case ${i}`);
  for(let p=256;p<end;p++)if(!((p>=out&&p<out+16)||p===command||p===status))
   assert.equal(cpu.data[p],before[p-256],`${recipe} guard/input ${i}/${p}`);
  timings.push(lastCycles);perQuarter[sub].push(lastCycles);
 }
 assert.equal(returns,cases.length);
 if(recipe===recipes[0])baseline=timings;
 const stats=a=>({min:Math.min(...a),max:Math.max(...a),mean:a.reduce((a,b)=>a+b,0)/a.length});
 const delta=timings.map((n,i)=>n-baseline[i]);
 const sizes=readFileSync(join(dir,'symbol-sizes.txt'),'utf8').split(/\r?\n/).find(l=>l.endsWith(' wb_probe_interpolate'));
 assert.ok(sizes);const functionBytes=parseInt(sizes.trim().split(/\s+/)[1],16);
 const report={...meta,cases:cases.length,cyclesIncludingFunctionRet:stats(timings),perQuarter:perQuarter.map(stats),
  pairedDeltaVsOriginal:stats(delta),flashBytes:binary.length,functionBytes,staticSramBytes:end-256,
  ownFunctionStackBytes:ownStack,wholeProbePeakStack:2303-minSP,calleeSavedAndR1Returns:returns,
  validCorrelatedCodebookEndpoints:true,all4096NewAndOldEndpoints:true,outputAddressLowBytes:256,
  exactSeparatelyRoundedXiphModel:true,guardsAndInputsIntact:true,includesInterrupts:false,physicalBoardTested:false};
 writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');summary.recipes.push(report);
 console.log('PASS',recipe,JSON.stringify({cycles:report.cyclesIncludingFunctionRet,delta:report.pairedDeltaVsOriginal,
  flash:report.flashBytes,functionBytes,ownStack}));
}
writeFileSync(join(base,'verification.json'),JSON.stringify(summary,null,2)+'\n');
