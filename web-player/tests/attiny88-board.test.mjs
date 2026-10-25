import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRenderer} from '../lib/engines.js';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as WASM} from '../lib/avr-core.js';

const variants=['rhythmic','lumiere-stereo','alicia','children','turkish-march',
  'greensleeves','cancion-del-mariachi','cancion-del-mariachi-polyphonic','cancion-del-mariachi-sparse'];
const folder=id=>new URL('../../ATtiny88/Music/variants-micronucleus/'+id+'/',import.meta.url);
const read=(id,name)=>readFileSync(new URL(name,folder(id)));
const report=id=>JSON.parse(read(id,'build-report.json'));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const clock={target:'attiny88',cpuHz:16000000};
const entry=id=>{
  const meta=report(id);
  return {id,device:'attiny88',board:'mh-et-live-16mhz',cpuHz:meta.cpuHz,
    pwmHz:meta.pwmHz,audioChannels:meta.audioChannels,flashHex:read(id,'synth.hex').toString()};
};
function render(renderer,frames,blocks){
  const output=new Float32Array(frames*renderer.channels);let at=0,n=0;
  while(at<frames){const count=Math.min(blocks[n++%blocks.length],frames-at);
    output.set(renderer.render(count),at*renderer.channels);at+=count;}
  return output;
}
const sameCPU=(a,b)=>{
  assert.deepEqual(a.data,b.data);assert.deepEqual(Array.from(a.irqFrames),Array.from(b.irqFrames));
  for(const key of ['pc','cyc','timer','timerDivisor','prescalerAt','overflowAt','irqDelay',
    'irqStart','irqCount','lost','maxIRQ','writes','leftWrites','inIRQ','minSP','workLost',
    'duty','dutyLeft','eempeUntil','clkprUntil','timerTemp','wdtUntil'])assert.equal(a[key],b[key],key);
};

for(const id of variants){
  test(`${id}: Micronucleus image includes its complete sample bank in application Flash`,()=>{
    const meta=report(id),binary=read(id,'synth.bin'),bank=meta.wavetableStorage;
    assert.equal(meta.board,'mh-et-live-16mhz');assert.equal(meta.cpuHz,16000000);
    assert.equal(meta.pwmHz,62500);assert.equal(meta.synthesisHz,31250);
    assert.equal(meta.controlClock.virtualSamples,3);assert.equal(meta.controlClock.physicalSamples,5);
    assert.equal(meta.controlClock.divider,256);assert.equal(meta.controlTickHz,18750/256);
    assert.equal(meta.applicationFlashLimit,6012);assert.ok(binary.length<=6012);
    assert.equal(meta.flashBytes,binary.length);assert.equal(hash(binary),meta.flashSha256);
    assert.equal(meta.eepromBytes,0);assert.equal(bank.space,'flash');assert.equal(bank.bytes,64);
    assert.equal(bank.alignment,256);assert.equal(bank.address&255,0);
    assert.equal(hash(binary.subarray(bank.address,bank.address+64)),bank.sha256);
    assert.equal(existsSync(new URL('eeprom.bin',folder(id))),false);
    assert.equal(existsSync(new URL('eeprom.hex',folder(id))),false);
    assert.equal(meta.wavetableHighStepThreshold,614);
    const reads=Object.entries(meta.labels).filter(([name])=>/^tiny88_flash_read_\d+$/.test(name));
    assert.ok(reads.length>0);
    for(const [,address]of reads){const word=binary[address]|binary[address+1]<<8;
      assert.equal(word&0xfe0f,0x9004,'Each embedded-bank read is an actual LPM');}
    // EERE is unsupported in the USB image: it must work after Flash-only upload.
    for(let address=0;address<meta.codeBytes;address+=2)
      assert.notEqual(binary[address]|binary[address+1]<<8,0x9af8,'No SBI EECR,EERE remains');
  });

  test(`${id}: both engines render two seconds at 16 MHz with erased EEPROM and identical PCM`,async()=>{
    const e=entry(id),a=await createRenderer(e,48000,{filtered:false},'js'),
      b=await createRenderer(e,48000,{filtered:false},'wasm');
    const actual=render(a,96000,[16384]),expected=render(b,96000,[1,127,4096,17,8192]);
    assert.deepEqual(actual,expected);sameCPU(a.core,b.core);
    let energy=0,stereoDifference=0;
    for(let n=0;n<actual.length;n++){assert.ok(Number.isFinite(actual[n]));energy+=actual[n]*actual[n];
      if(a.channels===2&&!(n&1))stereoDifference+=Math.abs(actual[n]-actual[n+1]);}
    assert.ok(energy>1,'Actual firmware produces sound');
    if(a.channels===2){assert.ok(stereoDifference>1);assert.equal(a.core.leftWrites,a.core.writes);}
    for(const {core:c}of [a,b]){
      assert.equal(c.cpuHz,16000000);assert.ok(c.eeprom.every(value=>value===255));
      assert.equal(c.lost+c.workLost,0);assert.ok(c.minSP>=0x100);
      assert.ok(Math.abs(c.cyc-32000000)<20000,'CPU advances at the board clock');
      assert.ok(Math.abs(c.irqCount-125000)<20,'Timer1 emits 62.5 kHz PWM writes');
      assert.equal(c.data[0x61],0);assert.equal(c.data[0x60],0);assert.equal(c.data[0x54],0);
      assert.equal(c.data[0x80],a.channels===2?0xa1:0x21);assert.equal(c.data[0x81],9);
      assert.equal(c.data[0x6f],1);assert.equal(c.data[0x24]&(a.channels===2?6:4),a.channels===2?6:4);
    }
  });

  test(`${id}: Flash-only sound is independent of EEPROM contents after a bootloader-style handoff`,()=>{
    const binary=read(id,'synth.bin'),stereo=id==='lumiere-stereo';
    const cores=[new JS(binary,null,clock),new WASM(binary,
      Uint8Array.from({length:64},(_,n)=>(n*67+15)&255),clock)];
    for(const c of cores){c.data[0x54]=8;c.data[0x60]=0x2b;c.sp=0x17f;}
    let energy=0;
    for(let n=0;n<32768;n++){
      const a=stereo?cores[0].nextStereoDuty():cores[0].nextDuty();
      const b=stereo?cores[1].nextStereoDuty():cores[1].nextDuty();assert.equal(a,b);
      energy+=Math.abs((a&255)-128);
    }
    assert.ok(energy>1);sameCPU(...cores);
    for(const c of cores){assert.equal(c.data[0x54],0);assert.equal(c.data[0x60],0);
      assert.equal(c.lost+c.workLost,0);assert.ok(c.minSP>=0x100);}
  });
}

test('16 MHz stereo resampling handles multiple PWM samples per low-rate audio frame',async()=>{
  const e=entry('lumiere-stereo'),controls={volume:.65,cutoff:9000};
  const a=await createRenderer(e,22050,controls,'js'),b=await createRenderer(e,22050,controls,'wasm');
  for(const count of [4096,17,8192]){
    const actual=a.render(count),expected=b.render(count);let max=0;
    for(let n=0;n<actual.length;n++)max=Math.max(max,Math.abs(actual[n]-expected[n]));
    assert.ok(max<2e-7,'JS/WASM filtered PCM matches');sameCPU(a.core,b.core);
    for(const r of [a,b])r.setAudioControls({volume:.2,cutoff:4000});
  }
});

test('Turkish bass note with a sub-256 DDS increment stays audible; only a full zero word is a rest',()=>{
  const meta=report('turkish-march'),binary=read('turkish-march','synth.bin');
  for(const Core of [JS,WASM])for(const increment of [244,0]){
    const patch=meta.frequencyPatches.find(p=>p.space==='flash'&&p.table==='chord_steps'&&p.targetWord===increment);
    assert.ok(patch,'Retained bass/rest word '+increment+' exists in the real score');
    const c=new Core(binary,null,clock),address=0x165;
    c.pc=meta.labels.initialize_voice/2;c.r[26]=address&255;c.r[27]=address>>8;
    c.r[25]=218;c.r[29]=0;c.r[30]=patch.targetAddress&255;c.r[31]=patch.targetAddress>>8;
    c.pushPC(0);let instructions=0;
    while(c.pc!==0){c.step();assert.ok(++instructions<100);}
    assert.equal(c.data[address],increment?218:0,'A low-valued nonzero word must not clear the envelope');
    assert.equal(c.data[address+3]|c.data[address+4]<<8,increment);assert.equal(c.sp,0x2ff);
  }
});
