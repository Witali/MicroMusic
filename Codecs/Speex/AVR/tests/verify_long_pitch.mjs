// Independent Xiph arithmetic, full signed8 shapes and hostile signed16 history.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/long-pitch-unit');
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const binary=readFileSync(join(build,'long-pitch.bin'));
const program=new Uint16Array(16384).fill(0xffff);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),command=address('long_command'),status=address('long_status');
const input=address('long_input')+2,out=address('long_output')+2,gain=address('long_gains')+1;
const cEntry=[...symbols].find(([n])=>/^long_test_c(?:\.|$)/.test(n))[1];
const entries=new Set([address('speex_avr_long_innovation10'),cEntry]);
const preserved=[...Array.from({length:16},(_,i)=>i+2),28,29];
const times=[null,{min:Infinity,max:0,calls:0},{min:Infinity,max:0,calls:0}];
let active=null,which=0,seed=0xc38021d7,clipped=0,pitchClipped=0,cases=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
  assert.ok(cpu.cycles<deadline,'Fused mailbox timeout');
  if(entries.has(cpu.pc*2)) {
    assert.equal(active,null);
    active={sp:cpu.SP,cycles:cpu.cycles,registers:preserved.map(r=>cpu.data[r])};
  }
  avrInstruction(cpu);cpu.tick();
  assert.ok(cpu.SP>=address('__bss_end'),'Stack/static collision');
  if(active && cpu.SP===active.sp+2) {
    assert.deepEqual(preserved.map(r=>cpu.data[r]),active.registers,'Callee-saved AVR registers');
    assert.equal(cpu.data[1],0,'Zero register at kernel return');
    const cycles=cpu.cycles-active.cycles;
    times[which].min=Math.min(times[which].min,cycles);
    times[which].max=Math.max(times[which].max,cycles);times[which].calls++;
    active=null;
  }
}}
until(()=>cpu.data[status]===1);
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const globalGains=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number);
const corrections=upstream.match(/exc_gain_quant_scal1\[2\]=\{([^}]+)\}/)[1].split(',').map(Number);
const scales=globalGains.flatMap(g=>corrections.map(c=>Math.floor(c*Math.floor(28406*g/32768)/16384)));
const table=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/gain_table_lbr.c'),'utf8')
  .match(/gain_cdbk_lbr\[128\]\s*=\s*\{([^}]+)\}/)[1].split(',').filter(v=>v.trim()).map(Number);
const gains=Array.from({length:32},(_,i)=>[table[4*i+2]+32,table[4*i+1]+32,table[4*i]+32]);
assert.equal(Math.max(...gains.map(g=>g.reduce((s,v)=>s+Math.abs(v),0))),147);
const samples=new Int16Array(12),expected=new Int16Array(10);
const edges=[-32768,32767,-32767,0,-1,1,-32000,32000];
function check(g,scale,index){
  assert.ok(g.reduce((s,v)=>s+Math.abs(v),0)<=147);
  cpu.dataView.setInt32(address('long_scale'),scale,true);cpu.data[address('long_index')]=index;
  cpu.dataView.setUint16(input-2,0x1357,true);cpu.dataView.setUint16(input+24,0x2468,true);
  cpu.dataView.setUint16(out-2,0x9876,true);cpu.dataView.setUint16(out+20,0xabcd,true);
  cpu.data[gain-1]=0x56;cpu.data[gain+3]=0x78;
  g.forEach((v,i)=>cpu.data[gain+i]=v&255);
  for(let i=0;i<12;i++)cpu.dataView.setInt16(input+2*i,samples[i],true);
  for(let i=0;i<10;i++){
    const raw=g[0]*samples[i]+g[1]*samples[i+1]+g[2]*samples[i+2];
    const pitch=Math.max(-262144000,Math.min(262144000,raw*128));
    pitchClipped+=raw*128!==pitch;
    const shape=((index+i)%256-128)*4;
    const innovation=((shape*(scale>>14)+Math.floor(shape*(scale&16383)/16384))*128)|0;
    const value=((2*pitch+innovation+8192)|0)>>14;
    expected[i]=Math.max(-32767,Math.min(32767,value));clipped+=expected[i]!==value;
  }
  for(which=1;which<=2;which++){
    for(let i=0;i<10;i++)cpu.dataView.setInt16(out+2*i,0x55aa,true);
    cpu.data[status]=1;cpu.data[command]=which;
    until(()=>cpu.data[status]===2);
    assert.equal(active,null);
    for(let i=0;i<10;i++)assert.equal(cpu.dataView.getInt16(out+2*i,true),expected[i],`backend ${which}, case ${cases}, sample ${i}`);
    for(let i=0;i<12;i++)assert.equal(cpu.dataView.getInt16(input+2*i,true),samples[i],'Read-only history');
    g.forEach((v,i)=>assert.equal((cpu.data[gain+i]<<24)>>24,v,'Read-only gains'));
    for(const [p,v] of [[input-2,0x1357],[input+24,0x2468],[out-2,0x9876],[out+20,0xabcd]])
      assert.equal(cpu.dataView.getUint16(p,true),v,'Buffer guard');
    assert.equal(cpu.data[gain-1],0x56);assert.equal(cpu.data[gain+3],0x78);
    assert.equal(cpu.data[address('long_zero')],0,'ABI zero in caller');
  }
  cases++;
}
for(const g of gains)for(const scale of scales)for(let index=0;index<256;index+=10){
  for(let i=0;i<12;i++)samples[i]=(cases%4===0)?edges[(i+cases)%edges.length]:(random()<<16)>>16;
  check(g,scale,index);
}
const tableCases=cases;
// Exact pitch-clamp boundary and +/-1, independent of real codebook sparsity.
for(const scale of scales)for(let index=0;index<256;index+=10)
  for(const sign of [-1,1])for(const delta of [-1,0,1]){
    for(let i=0;i<12;i++)samples[i]=(random()<<16)>>16;
    samples[0]=sign*32000;samples[1]=sign*delta;
    check([64,1,0],scale,index);
  }
const boundaryCases=cases-tableCases;
for(let block=0;block<4096;block++){
  let g;
  do{g=Array.from({length:3},()=>((random()&255)<<24)>>24);}while(g.reduce((s,v)=>s+Math.abs(v),0)>147);
  for(let i=0;i<12;i++)samples[i]=(random()<<16)>>16;
  check(g,scales[block%64],random()&255);
}
assert.ok(pitchClipped>1000 && clipped>10000);
assert.equal(times[1].calls,cases);assert.equal(times[2].calls,cases);
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:'AVR GCC 7.3.0 mixed Os/O2, LTO, fwrapv',
  binarySha256:createHash('sha256').update(binary).digest('hex'),blocks:cases,samplesPerBackend:cases*10,
  tableGainTriples:32,scales:64,shapeMin:-128,shapeMax:127,historyMin:-32768,historyMax:32767,
  fullTableShapeScaleCases:tableCases,clampBoundaryBlocks:boundaryCases,randomGainBlocks:4096,
  outputClippedSamples:clipped,pitchClippedSamples:pitchClipped,exact:true,
  gainsPreserved:true,historyPreserved:true,guardsIntact:true,calleeSavedRegistersPreserved:true,
  zeroRegisterRestored:true,asmKernelCycles:times[1],cKernelCycles:times[2],
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
