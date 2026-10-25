// Compare the actual segmented controllers to the independent original tap rule.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/short-pitch-unit');
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
function functionAddress(re){const v=[...symbols].filter(([n])=>re.test(n));assert.equal(v.length,1);return v[0][1];}
const entries=new Set([functionAddress(/^speex_nb3_short_innovation(?:\.|$)/),
  functionAddress(/^speex_nb3_short_innovation_c_test(?:\.|$)/)]);
const binary=readFileSync(join(build,'short-pitch.bin')),program=new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),command=address('short_command'),status=address('short_status');
const exc=address('short_exc')+84,packet=address('short_packet');
const preserved=[...Array.from({length:16},(_,i)=>i+2),28,29];
const cycles=[null,{min:Infinity,max:0,calls:0},{min:Infinity,max:0,calls:0}];
const pitchCycles=Array.from({length:24},(_,i)=>({pitch:17+i,
  backends:[null,...Array.from({length:2},()=>({min:Infinity,max:0,total:0,calls:0}))]}));
let currentPitch=17;
let active=null,backend=0,seed=0x319e72b1,blocks=0,pitchClipped=0,outputClipped=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
  assert.ok(cpu.cycles<deadline,'Short-pitch mailbox timeout');
  if(entries.has(cpu.pc*2)){
    assert.equal(active,null);active={sp:cpu.SP,ticks:cpu.cycles,regs:preserved.map(r=>cpu.data[r])};
  }
  avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=address('__bss_end'),'Stack/static collision');
  if(active && cpu.SP===active.sp+2){
    assert.deepEqual(preserved.map(r=>cpu.data[r]),active.regs,'Callee-saved controller registers');
    assert.equal(cpu.data[1],0,'Zero register at controller return');
    const ticks=cpu.cycles-active.ticks;cycles[backend].min=Math.min(cycles[backend].min,ticks);
    cycles[backend].max=Math.max(cycles[backend].max,ticks);cycles[backend].calls++;
    const row=pitchCycles[currentPitch-17].backends[backend];
    row.min=Math.min(row.min,ticks);row.max=Math.max(row.max,ticks);row.total+=ticks;row.calls++;
    active=null;
  }
}}
until(()=>cpu.data[status]===1);
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const gains=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number);
const corrections=upstream.match(/exc_gain_quant_scal1\[2\]=\{([^}]+)\}/)[1].split(',').map(Number);
const scales=gains.flatMap(g=>corrections.map(c=>Math.floor(c*Math.floor(28406*g/32768)/16384)));
function table(file,name,size){return readFileSync(join(root,'vendor/speex-1.2.1/libspeex',file),'utf8')
  .match(new RegExp(name+'\\['+size+'\\]\\s*=\\s*\\{([^}]+)\\}'))[1]
  .split(',').filter(v=>v.trim()).map(Number);}
const pitchTable=table('gain_table_lbr.c','gain_cdbk_lbr',128);
const shapes=table('exc_10_32_table.c','exc_10_32_table',320);
const history=new Int16Array(41),expected=new Int16Array(40),edges=[-32768,32767,-32767,0,-1,1,-32000,32000];
for(let pitch=17;pitch<=40;pitch++)for(let gain=0;gain<32;gain++)for(let s=0;s<64;s++){
  currentPitch=pitch;
  const scale=scales[s],g=[2,1,0].map(t=>pitchTable[4*gain+t]+32);
  const indices=Array.from({length:4},(_,v)=>(s*3+gain*5+pitch*7+v*11)&31);
  const bits=((indices[0]<<15)|(indices[1]<<10)|(indices[2]<<5)|indices[3])*16+10;
  cpu.data[packet]=0x56;cpu.data[packet+1]=bits>>>16;cpu.data[packet+2]=bits>>>8;
  cpu.data[packet+3]=bits;cpu.data[packet+4]=0x78;
  const packetBefore=cpu.data.slice(packet,packet+5);
  for(let i=0;i<41;i++)history[i]=blocks%4===0?edges[(blocks+i)%8]:(random()<<16)>>16;
  for(let j=0;j<40;j++){
    let raw=0;
    for(let tap=0;tap<3;tap++){
      const pp=pitch+1-tap;
      let value=0;
      if(j<pp)value=history[41+j-pp];
      else if(j<pp+pitch)value=history[41+j-pp-pitch];
      assert.ok(Number.isInteger(value),'Original negative source is inside history');
      raw+=g[tap]*value*128;
    }
    const adaptive=Math.max(-262144000,Math.min(262144000,raw));pitchClipped+=raw!==adaptive;
    const shape=4*shapes[10*indices[(j/10)|0]+j%10];
    const innovation=((shape*(scale>>14)+Math.floor(shape*(scale&16383)/16384))*128)|0;
    const y=((2*adaptive+innovation+8192)|0)>>14;
    expected[j]=Math.max(-32767,Math.min(32767,y));outputClipped+=y!==expected[j];
  }
  cpu.data[address('short_pitch')]=pitch;cpu.data[address('short_gain')]=gain;
  cpu.dataView.setInt32(address('short_scale'),scale,true);
  for(backend=1;backend<=2;backend++){
    for(let i=0;i<41;i++)cpu.dataView.setInt16(exc-82+2*i,history[i],true);
    cpu.dataView.setUint16(exc-84,0x1357,true);cpu.dataView.setUint16(exc+80,0x2468,true);
    for(let j=0;j<40;j++)cpu.dataView.setInt16(exc+2*j,0x55aa,true);
    cpu.data[status]=1;cpu.data[command]=backend;until(()=>cpu.data[status]===2);
    assert.equal(active,null);
    for(let j=0;j<40;j++)assert.equal(cpu.dataView.getInt16(exc+2*j,true),expected[j],`backend ${backend}, pitch ${pitch}, gain ${gain}, scale ${s}, sample ${j}`);
    for(let i=0;i<41;i++)assert.equal(cpu.dataView.getInt16(exc-82+2*i,true),history[i],'Read-only negative history');
    assert.equal(cpu.dataView.getUint16(exc-84,true),0x1357);assert.equal(cpu.dataView.getUint16(exc+80,true),0x2468);
    assert.deepEqual(cpu.data.slice(packet,packet+5),packetBefore,'Read-only packet and guards');
    assert.equal(cpu.data[address('short_zero')],0);assert.equal(cpu.data[address('short_char')],2);
    assert.equal(cpu.data[address('short_bit')],4);assert.equal(cpu.data[address('short_overflow')],0);
  }
  blocks++;
}
assert.equal(blocks,24*32*64);assert.equal(cycles[1].calls,blocks);assert.equal(cycles[2].calls,blocks);
assert.ok(pitchClipped>10000 && outputClipped>1000);
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:'AVR GCC 7.3.0 mixed Os/O2/O3, LTO, fwrapv',
  binarySha256:createHash('sha256').update(binary).digest('hex'),blocks,samplesPerBackend:blocks*40,
  pitches:24,pitchMin:17,pitchMax:40,gainCodes:32,scales:64,shapeCodes:32,
  historyMin:-32768,historyMax:32767,pitchClipped,outputClipped,exact:true,
  historyPreserved:true,packetPreserved:true,guardsIntact:true,bitConsumptionExact:true,
  indexParsingOutsideMeasuredController:true,
  calleeSavedRegistersPreserved:true,zeroRegisterRestored:true,asmControllerCycles:cycles[1],
  cControllerCycles:cycles[2],perPitch:pitchCycles.map(({pitch,backends})=>({pitch,
    asm:{...backends[1],mean:Number((backends[1].total/backends[1].calls).toFixed(3))},
    c:{...backends[2],mean:Number((backends[2].total/backends[2].calls).toFixed(3))}})),
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
