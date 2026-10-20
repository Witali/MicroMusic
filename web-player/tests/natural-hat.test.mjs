import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-core.js';
const folder=new URL('../../ATtiny13A/Music/variants/natural-hat/',import.meta.url);
const read=name=>readFileSync(new URL(name,folder));
const report=JSON.parse(read('build-report.json'));
const parentFolder=new URL('../foreground-pwm/',folder);
const parentReport=JSON.parse(readFileSync(new URL('build-report.json',parentFolder)));
const image=(where=folder)=>new AVRCore(readFileSync(new URL('synth.bin',where)),read('eeprom.bin'));

test('direct SRAM instructions and skipping a two-word store use AVR instruction boundaries and cycles',()=>{
  const words=[0xe50a,0x9300,96,0x9110,96,0xfd10,0x9300,159,0xea25,0x9320,159,0x9130,159];
  const rom=Buffer.alloc(words.length*2);words.forEach((v,i)=>rom.writeUInt16LE(v,i*2));
  const c=new AVRCore(rom);c.c=c.z=c.t=1;
  for(let i=0;i<7;i++)c.step();
  assert.equal(c.r[17],0x5a);assert.equal(c.r[19],0xa5);
  assert.equal(c.ram[0],0x5a);assert.equal(c.ram[63],0xa5);
  assert.equal(c.pc,13);assert.equal(c.cyc,13);assert.equal(c.c,1);assert.equal(c.z,1);assert.equal(c.t,1);
  const invalid=new AVRCore(Uint8Array.of(0,0x91,160,0));
  assert.throws(()=>invalid.step(),/Data address/);
});

test('actual 16-bit noise routine visits all 65535 nonzero states before repeating',()=>{
  const c=image(),seen=new Set();c.r[14]=167;
  const start=report.labels['.L298']/2,end=report.labels['.L2a0']/2+2;
  let expected=167;
  for(let i=0;i<65535;i++){
    c.pc=start;while(c.pc!==end)c.step();
    expected=((expected<<1)&65535)^((expected&32768)?45:0);
    const state=c.r[14]|c.ram[0]<<8;
    assert.equal(state,expected);assert.ok(state!==0&&!seen.has(state));seen.add(state);
  }
  assert.equal(expected,167);assert.equal(seen.size,65535);
});

function nextCommit(c,labels,muted=false){
  const entry=labels.audio_step/2,done=(labels.idle+6)/2;
  while(c.pc!==entry||c.inIRQ)c.step();
  if(muted)c.r[21]=4;
  const before=c.cyc;
  do{c.step();}while(c.pc!==done||c.inIRQ);
  return c.cyc-before;
}

test('noise changes preserve the entire tonal stream, EEPROM and score',()=>{
  const c=image(),parent=image(parentFolder);
  for(let i=0;i<37500;i++){
    nextCommit(c,report.labels,true);nextCommit(parent,parentReport.labels,true);
    assert.equal(c.r[18],parent.r[18],`Muted percussion sample ${i}`);
    for(const r of [1,2,3,4,5,6,7,8,9,10,11,12,13,15,19,20,22,23,24,25,28,29])assert.equal(c.r[r],parent.r[r],`R${r}`);
  }
  for(const file of ['eeprom.bin','score.inc','score.json','waveforms.json'])assert.deepEqual(read(file),readFileSync(new URL(file,parentFolder)));
  assert.equal(c.maxIRQ,12);assert.equal(c.lost+c.workLost,0);
});

test('new noise and score controls fit the foreground, Flash and SRAM budgets',t=>{
  const c=image(),sections=new Set(),tokens=new Set();let maximum=0;
  let stackBytes=0,maxStackBytes=0;
  const step=c.step.bind(c);
  c.step=()=>{
    const word=c.rom[c.pc*2]|c.rom[c.pc*2+1]<<8,irqs=c.irqCount;step();
    if((word&0xf000)===0xd000)stackBytes+=2;
    if((word&0xfe0f)===0x920f)stackBytes++;
    if((word&0xfe0f)===0x900f)stackBytes--;
    if(word===0x9508||word===0x9518)stackBytes-=2;
    stackBytes+=(c.irqCount-irqs)*2;maxStackBytes=Math.max(maxStackBytes,stackBytes);
    assert.ok(stackBytes>=0&&stackBytes<=63,'One byte reserved for noise, remaining SRAM for the hardware stack');
  };
  const entry=report.labels.audio_step/2,done=(report.labels.idle+6)/2;
  for(let n=0;n<950;n++){
    while(c.pc!==entry||c.inIRQ)c.step();
    c.r[15]=c.r[23]=255;c.r[22]=1;
    const before=c.cyc;
    do{
      if(c.pc===report.labels.read_event/2&&!c.inIRQ)tokens.add(c.rom[c.r[30]|c.r[31]<<8]);
      c.step();
    }while(c.pc!==done||c.inIRQ);
    maximum=Math.max(maximum,c.cyc-before);sections.add(c.r[28]);
  }
  for(let n=0;n<15;n++)assert.ok(sections.has(n));
  for(const token of [0xf2,0xf4,0xf6,0xf8,0xff])assert.ok(tokens.has(token));
  for(let n=0;n<75000;n++)maximum=Math.max(maximum,nextCommit(c,report.labels));
  assert.ok(read('synth.bin').length<=1024);assert.ok(maximum<480,`${maximum} cycles`);
  assert.equal(c.maxIRQ,12);assert.equal(c.lost+c.workLost,0);
  assert.equal(c.ram.subarray(1,c.minSP-0x60+1).some(x=>x!==0),false,'Only bottom SRAM byte is used by noise');
  t.diagnostic(JSON.stringify({maximumForegroundCyclesIncludingPreemption:maximum,isrCycles:c.maxIRQ,maxStackBytes,lostEvents:c.lost+c.workLost}));
});

test('measured hihat spectrum moves closer to FluidR3 while bass drum stays identical',()=>{
  const {instruments}=JSON.parse(read('percussion-measurements.json'));
  assert.ok(instruments[42]['natural-hat'].spectralDistance<instruments[42]['foreground-pwm'].spectralDistance*.7);
  assert.deepEqual(instruments[35]['natural-hat'].bandPower,instruments[35]['foreground-pwm'].bandPower);
});
