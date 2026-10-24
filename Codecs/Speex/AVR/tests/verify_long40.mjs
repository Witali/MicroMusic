// Independent Xiph fixed-point oracle; actual top-level RET, RAM and LPM bounds.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=join(root,'build/long40-unit');
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function addr(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
function entry(n){const p=[...symbols].find(([s])=>s===n||s.startsWith(n+'.'));assert.ok(p,n);return p[1];}
const binary=readFileSync(join(dir,'long40.bin')),program=new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),status=addr('long40_status'),command=addr('long40_command');
const input=addr('long40_input')+2,out=addr('long40_output')+2,gain=addr('long40_gains')+1,indices=addr('long40_indices')+1;
const book=addr('exc_10_32_table');assert.ok(book+320<=binary.length);
const entries=[0,addr('speex_avr_long_innovation40'),entry('long40_test_ten'),entry('long40_test_c')];
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29];
const timing=[null,...Array.from({length:3},()=>({min:Infinity,max:0,total:0,calls:0}))];
const shapesSeen=new Set(),indicesSeen=Array.from({length:4},()=>new Set()),deltas={min:Infinity,max:-Infinity,total:0};
let active=null,which=0,cases=0,seed=0x8fe19437,clips=0,pitchClips=0,spMin=0x8ff,loads=[],flashLoads=[],lastCycles=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
for(const [start,length,name] of [[input-2,88,'history'],[out-2,84,'output'],[gain-1,5,'gain'],[indices-1,6,'indices']])
 for(let i=0;i<length;i++)cpu.readHooks[start+i]=a=>{if(active)loads.push([name,a-start]);return cpu.data[a];};
function until(p){const deadline=cpu.cycles+100000;while(!p()){
 assert.ok(cpu.cycles<deadline,'long40 timeout');
 if(cpu.pc*2===entries[which]&&which){assert.equal(active,null);active={sp:cpu.SP,c:cpu.cycles,r:regs.map(r=>cpu.data[r])};}
 if(active){const op=program[cpu.pc];if((op&0xfe0e)===0x9004||op===0x95c8)flashLoads.push(cpu.data[30]|(cpu.data[31]<<8));}
 avrInstruction(cpu);cpu.tick();spMin=Math.min(spMin,cpu.SP);assert.ok(cpu.SP>=addr('__bss_end'));
 if(active&&cpu.SP===active.sp+2){
  assert.deepEqual(regs.map(r=>cpu.data[r]),active.r,'callee-saved registers at actual RET');assert.equal(cpu.data[1],0,'r1 at RET');
  lastCycles=cpu.cycles-active.c;const t=timing[which];t.min=Math.min(t.min,lastCycles);t.max=Math.max(t.max,lastCycles);t.total+=lastCycles;t.calls++;active=null;
 }
}}
until(()=>cpu.data[status]===1);
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const global=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number);
const corrections=upstream.match(/exc_gain_quant_scal1\[2\]=\{([^}]+)\}/)[1].split(',').map(Number);
const scales=global.flatMap(g=>corrections.map(c=>Math.floor(c*Math.floor(28406*g/32768)/16384)));
const table=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/gain_table_lbr.c'),'utf8')
 .match(/gain_cdbk_lbr\[128\]\s*=\s*\{([^}]+)\}/)[1].split(',').filter(v=>v.trim()).map(Number);
const gains=Array.from({length:32},(_,i)=>[table[4*i+2]+32,table[4*i+1]+32,table[4*i]+32]);
assert.equal(Math.max(...gains.map(g=>g.reduce((a,b)=>a+Math.abs(b),0))),147);
const samples=new Int16Array(42),expected=new Int16Array(40),edges=[-32768,32767,-32767,0,-1,1,-32000,32000];
function check(g,scale,codes){
 assert.ok(g.reduce((a,b)=>a+Math.abs(b),0)<=147&&scale>=0&&scale<=121000000);
 cpu.dataView.setInt32(addr('long40_scale'),scale,true);
 cpu.dataView.setUint16(input-2,0x1357,true);cpu.dataView.setUint16(input+84,0x2468,true);
 cpu.dataView.setUint16(out-2,0x9876,true);cpu.dataView.setUint16(out+80,0xabcd,true);
 cpu.data[gain-1]=0x56;cpu.data[gain+3]=0x78;g.forEach((v,i)=>cpu.data[gain+i]=v&255);
 cpu.data[indices-1]=0x39;cpu.data[indices+4]=0x93;cpu.data.set(codes,indices);
 for(let i=0;i<42;i++)cpu.dataView.setInt16(input+2*i,samples[i],true);
 const expectedFlash=[];
 for(let i=0;i<40;i++){
  const vector=i/10|0,offset=10*codes[vector]+i%10,shape=(offset*73+19)%256-128;
  assert.equal((binary[book+offset]<<24)>>24,shape,'actual synthetic Flash table');
  shapesSeen.add(shape);indicesSeen[vector].add(codes[vector]);expectedFlash.push(book+offset);
  const raw=g[0]*samples[i]+g[1]*samples[i+1]+g[2]*samples[i+2];
  const pitch=Math.max(-262144000,Math.min(262144000,raw*128));pitchClips+=pitch!==raw*128;
  const scaledShape=shape*4;
  const innovation=((scaledShape*(scale>>14)+Math.floor(scaledShape*(scale&16383)/16384))*128)|0;
  const value=((2*pitch+innovation+8192)|0)>>14;expected[i]=Math.max(-32767,Math.min(32767,value));clips+=expected[i]!==value;
 }
 const historyBefore=cpu.data.slice(input-2,input+86),gainBefore=cpu.data.slice(gain-1,gain+4),codesBefore=cpu.data.slice(indices-1,indices+5);
 const times=[];
 for(which of [1,2,3]){
  for(let i=0;i<40;i++)cpu.dataView.setInt16(out+2*i,0x55aa,true);
  loads=[];flashLoads=[];const calls=timing[which].calls;
  cpu.data[status]=1;cpu.data[command]=which;until(()=>cpu.data[status]===2);
  assert.equal(active,null);assert.equal(timing[which].calls,calls+1,'exactly one observed top-level RET');times[which]=lastCycles;
  for(let i=0;i<40;i++)assert.equal(cpu.dataView.getInt16(out+2*i,true),expected[i],`variant ${which}, case ${cases}, sample ${i}`);
  assert.equal(cpu.dataView.getUint16(out-2,true),0x9876);assert.equal(cpu.dataView.getUint16(out+80,true),0xabcd);
  assert.deepEqual(cpu.data.slice(input-2,input+86),historyBefore);assert.deepEqual(cpu.data.slice(gain-1,gain+4),gainBefore);assert.deepEqual(cpu.data.slice(indices-1,indices+5),codesBefore);
  assert.equal(cpu.data[addr('long40_zero')],0);
  assert.deepEqual(flashLoads,expectedFlash,'exactly 40 valid Flash shape reads in vector order');
  for(const [n,o] of loads)assert.ok((n==='history'&&o>=2&&o<86)||(n==='gain'&&o>=1&&o<4)||(n==='indices'&&o>=1&&o<5),'unexpected input/output RAM read');
  if(which===1){assert.equal(loads.filter(([n])=>n==='history').length,84);assert.equal(loads.filter(([n])=>n==='gain').length,3);assert.equal(loads.filter(([n])=>n==='indices').length,4);}
 }
 const delta=times[2]-times[1];deltas.min=Math.min(deltas.min,delta);deltas.max=Math.max(deltas.max,delta);deltas.total+=delta;
 cases++;
}
function codes(i){return [i,(i*7+3)&31,(i*13+5)&31,31-i];}
for(const g of gains)for(const scale of scales)for(let i=0;i<32;i++){
 for(let j=0;j<42;j++)samples[j]=cases%4===0?edges[(j+cases)%edges.length]:(random()<<16)>>16;
 check(g,scale,codes(i));
}
const tableCases=cases;
for(const scale of scales)for(const pos of [0,9,10,19,20,29,30,39])for(const sign of [-1,1])for(const delta of [-1,0,1]){
 for(let j=0;j<42;j++)samples[j]=(random()<<16)>>16;
 samples[pos]=sign*32000;samples[pos+1]=sign*delta;check([64,1,0],scale,codes(random()&31));
}
const boundaryCases=cases-tableCases;
for(const scale of [0,1,4095,4096,16383,16384,120988612,121000000])for(let i=0;i<32;i++){
 for(let j=0;j<42;j++)samples[j]=edges[(i+j)%edges.length];check(gains[i],scale,codes(i));
}
for(let i=0;i<4096;i++){
 let g;do{g=Array.from({length:3},()=>((random()&255)<<24)>>24);}while(g.reduce((a,b)=>a+Math.abs(b),0)>147);
 for(let j=0;j<42;j++)samples[j]=(random()<<16)>>16;
 check(g,i%2?scales[i%64]:random()%121000001,Array.from({length:4},()=>random()&31));
}
assert.equal(cases,72960);assert.equal(shapesSeen.size,256);assert.ok(indicesSeen.every(s=>s.size===32));assert.ok(clips>10000&&pitchClips>10000);
for(const t of timing.slice(1)){assert.equal(t.calls,cases);t.mean=Number((t.total/t.calls).toFixed(4));}
assert.ok(deltas.min>0,'one forty-sample call must beat four rolling-ten calls for every component case');
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:'AVR GCC 7.3.0 mixed Os/O2 LTO fwrapv mcall-prologues mrelax',
 binarySha256:createHash('sha256').update(binary).digest('hex'),casesPerImplementation:cases,samplesPerImplementation:cases*40,
 tableCases,boundaryCases,randomGainBlocks:4096,scaleEdgeBlocks:256,tableGainTriples:32,tableScales:64,all256Shapes:true,all32IndicesAtEachVector:true,
 pitchClippedSamples:pitchClips,outputClippedSamples:clips,exact:true,historyGainIndicesAndGuardsPreserved:true,
 actualRamReadsChecked:true,exact40FlashReadsPerCall:true,newKernelHistoryBytesRead:84,newKernelGainBytesRead:3,newKernelIndexBytesRead:4,
 calleeSavedRegistersPreserved:true,zeroRegisterRestored:true,topLevelReturnsEach:cases,asm40Cycles:timing[1],fourAsmTenCycles:timing[2],c40Cycles:timing[3],
 cyclesSavedVsFourTen:{min:deltas.min,max:deltas.max,mean:Number((deltas.total/cases).toFixed(4))},
 peakStackBytes:0x8ff-spMin,staticSramBytes:addr('__bss_end')-0x100,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
