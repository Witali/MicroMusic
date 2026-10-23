import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/iir');
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const program=new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(readFileSync(join(build,'iir.bin')));
const cpu=new CPU(program,2048),status=address('iir_status'),command=address('iir_command');
const samples=address('iir_samples'),coef=address('iir_coef'),zero=address('iir_zero');
function until(predicate){const end=cpu.cycles+30000;while(!predicate()){
  assert.ok(cpu.cycles<end,'LPC mailbox timeout');avrInstruction(cpu);cpu.tick();
}}
let seed=0x8b271e4d;
function next(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
const mem=new Int32Array(10),den=new Int16Array(10),expected=new Int16Array(40);
until(()=>cpu.data[status]===1);
let minCycles=Infinity,maxCycles=0,clipped=0,wraps=0;
for(let block=0;block<4096;block++){
  for(let j=0;j<10;j++){
    den[j]=block%3?next():next()%1001-500;
    cpu.dataView.setInt16(coef+2*j,den[j],true);
  }
  for(let i=0;i<40;i++){
    const input=(next()<<16)>>16;
    cpu.dataView.setInt16(samples+2*i,input,true);
    const raw=input+(((mem[0]+4096)|0)>>13),y=Math.max(-32767,Math.min(32767,raw));
    clipped+=y!==raw;expected[i]=y;
    for(let j=0;j<9;j++){
      const value=mem[j+1]-den[j]*y;mem[j]=value;
      wraps+=value!==mem[j];
    }
    mem[9]=-den[9]*y;
  }
  cpu.data[status]=1;cpu.data[command]=1;const before=cpu.cycles;
  until(()=>cpu.data[status]===2);
  for(let i=0;i<40;i++)assert.equal(cpu.dataView.getInt16(samples+2*i,true),expected[i],`block ${block}, sample ${i}`);
  assert.equal(cpu.data[zero],0,'GCC zero register');
  const cycles=cpu.cycles-before;minCycles=Math.min(minCycles,cycles);maxCycles=Math.max(maxCycles,cycles);
}
assert.ok(clipped>10000&&wraps>1000,'Exercise saturation and overflow');
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:'AVR GCC 7.3.0 -O3 -flto -fwrapv',
  blocks:4096,samples:4096*40,clipped,wraps,exact:true,inPlace:true,zeroRegisterRestored:true,
  minMailboxCycles:minCycles,maxMailboxCycles:maxCycles,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));

// Independent upstream arithmetic, all 64 NB3 gains and all signed-byte shapes.
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const gains=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number);
const corrections=upstream.match(/exc_gain_quant_scal1\[2\]=\{([^}]+)\}/)[1].split(',').map(Number);
const scales=gains.flatMap(g=>corrections.map(c=>Math.floor(c*Math.floor(28406*g/32768)/16384)));
const scaleAddress=address('innovation_scale'),pitchAddress=address('innovation_pitch');
let innovationCases=0,innovationClipped=0,cInnovationMin=Infinity,cInnovationMax=0;
const pitchEdges=[-8388608,8388607,-2048001,-2048000,2048000,2048001,-1,0,1];
for(const scale of scales)for(let index=0;index<256;index++){
  cpu.dataView.setInt32(scaleAddress,scale,true);cpu.data[address('innovation_index')]=index;
  for(let i=0;i<10;i++){
    const shape=(index+i)%256-128,pitch=i<9?pitchEdges[i]:(next()<<8)>>8;
    const value=shape*4;
    const upstream=((value*(scale>>14)+Math.floor(value*(scale&16383)/16384))*128)|0;
    assert.equal(upstream,(Math.floor(shape*scale/4096)*128)|0,'Bounded transformation exact');
    const adaptive=Math.max(-262144000,Math.min(262144000,pitch*128));
    const raw=((((2*adaptive+upstream)|0)+8192)|0)>>14;
    expected[i]=Math.max(-32767,Math.min(32767,raw));innovationClipped+=expected[i]!==raw;
    for(let byte=0;byte<3;byte++)cpu.data[pitchAddress+3*i+byte]=(pitch>>>(8*byte))&255;
  }
  for (const backendCommand of [2,3]) {
    cpu.data[status]=1;cpu.data[command]=backendCommand;const before=cpu.cycles;
    until(()=>cpu.data[status]===2);
    for(let i=0;i<10;i++)assert.equal(cpu.dataView.getInt16(samples+2*i,true),expected[i],`innovation backend ${backendCommand}, gain ${scale}, shape ${(index+i)%256-128}`);
    assert.equal(cpu.data[zero],0,'GCC zero register after innovation');
    if (backendCommand===3) {
      cInnovationMin=Math.min(cInnovationMin,cpu.cycles-before);
      cInnovationMax=Math.max(cInnovationMax,cpu.cycles-before);
    }
  }
  innovationCases+=10;
}
const innovationReport={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:report.compiler,
  gains:scales.length,scaleMin:Math.min(...scales),scaleMax:Math.max(...scales),shapeMin:-128,shapeMax:127,
  samples:innovationCases,clipped:innovationClipped,exact:true,zeroRegisterRestored:true,
  pitchFormat:'signed24le unscaled',pitchSanitizationVerified:true,
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification-innovation.json'),JSON.stringify(innovationReport,null,2)+'\n');
console.log(JSON.stringify(innovationReport,null,2));
const cInnovationReport={...innovationReport,backend:'c',
  minMailboxCycles:cInnovationMin,maxMailboxCycles:cInnovationMax};
writeFileSync(join(build,'verification-innovation-c.json'),JSON.stringify(cInnovationReport,null,2)+'\n');
console.log(JSON.stringify(cInnovationReport,null,2));
let cSaturationCases=0;
function checkCSaturation(v) {
  cpu.dataView.setInt32(scaleAddress,v,true);cpu.data[status]=1;cpu.data[command]=4;
  until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt16(samples,true),Math.max(-32767,Math.min(32767,v>>14)),`C Q14 saturation ${v}`);
  assert.equal(cpu.data[zero],0,'GCC zero register after C saturation');cSaturationCases++;
}
for(let word=-32768;word<=32767;word++)for(const remainder of [0,1,8191,8192,16383])
  checkCSaturation(word*16384+remainder);
for(let i=0;i<131072;i++)checkCSaturation(next()|0);
for(const edge of [-2147483648,2147483647,536854528,-536854528])
  for(let offset=-32;offset<=32;offset++)checkCSaturation((edge+offset)|0);
const cSaturationReport={mcu:report.mcu,simulator:report.simulator,compiler:report.compiler,
  samples:cSaturationCases,exact:true,fullSigned32Inputs:true,zeroRegisterRestored:true,
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification-c-q14-saturation.json'),JSON.stringify(cSaturationReport,null,2)+'\n');
console.log(JSON.stringify(cSaturationReport,null,2));
