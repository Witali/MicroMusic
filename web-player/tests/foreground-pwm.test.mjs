import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { AVRCore } from '../lib/avr-core.js';
const folder=new URL('../../ATtiny13A/Music/variants/foreground-pwm/',import.meta.url);
const read=name=>readFileSync(new URL(name,folder));
const report=JSON.parse(read('build-report.json'));

test('SET, CLT and T-flag branches preserve foreground carry and zero flags',()=>{
  const words=[0x9468,0xf40e,0x94e8,0xf40e,0xe603,0xe007];
  const bytes=Buffer.alloc(words.length*2);words.forEach((w,i)=>bytes.writeUInt16LE(w,i*2));
  const c=new AVRCore(bytes);c.c=c.z=1;
  for(let i=0;i<5;i++)c.step();
  assert.equal(c.r[16],7);assert.equal(c.t,0);assert.equal(c.c,1);assert.equal(c.z,1);assert.equal(c.cyc,6);
});

test('foreground commits match the parent synth, ISR outputs only complete samples in twelve cycles',t=>{
  const parent=new URL('../fluid-instruments/',folder);
  const reference=new AVRCore(readFileSync(new URL('synth.bin',parent)),read('eeprom.bin'));
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin'));
  const commit=(report.labels.write_pwm+2)/2,completed=(report.labels.idle+6)/2;
  let samples=0,published=128,writes=0,started=null,maxWork=0,stackBytes=0,maxStackBytes=0;
  while(samples<2*37500){
    if(c.pc===report.labels.audio_step/2&&!c.inIRQ)started=c.cyc;
    const at=c.pc,word=c.rom[at*2]|c.rom[at*2+1]<<8,irqs=c.irqCount;
    c.step();
    if((word&0xf000)===0xd000)stackBytes+=2;
    if((word&0xfe0f)===0x920f)stackBytes++;
    if((word&0xfe0f)===0x900f)stackBytes--;
    if(word===0x9508||word===0x9518)stackBytes-=2;
    stackBytes+=(c.irqCount-irqs)*2;
    maxStackBytes=Math.max(maxStackBytes,stackBytes);
    assert.ok(stackBytes>=0&&stackBytes<=64,'Hardware stack SRAM budget');
    if(at===commit)published=c.r[18];
    if(c.writes!==writes){assert.equal(c.duty,published,'IRQ saw a partial mix');writes=c.writes;}
    if(c.pc===completed&&!c.inIRQ){
      assert.equal(c.r[18],reference.nextDuty(),`Committed sample ${samples}`);
      if(started!==null)maxWork=Math.max(maxWork,c.cyc-started);
      samples++;started=null;
    }
  }
  assert.equal(c.lost,0);assert.equal(c.workLost,0);assert.equal(c.maxIRQ,12);
  assert.ok(maxWork>300&&maxWork<480,`${maxWork} foreground cycles`);
  assert.deepEqual(read('eeprom.bin'),readFileSync(new URL('eeprom.bin',parent)));
  for(const name of ['score.inc','score.json','waveforms.json'])assert.deepEqual(read(name),readFileSync(new URL(name,parent)));
  t.diagnostic(JSON.stringify({committedSamples:samples,maxForegroundCyclesIncludingPreemption:maxWork,maxIsrCycles:c.maxIRQ,maxStackBytes,lostIrq:c.lost,lostWorkTicks:c.workLost}));
});

test('foreground processes all playlist entries and note-off tokens without losing work ticks',()=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),sections=new Set(),tokens=new Set();
  const entry=report.labels.audio_step/2,readEvent=report.labels.read_event/2,completed=(report.labels.idle+6)/2;
  for(let n=0;n<950;n++){
    let steps=0;
    while((c.pc!==entry||c.inIRQ)&&steps++<2000)c.step();
    assert.ok(steps<2000);
    c.r[15]=c.r[23]=255;c.r[22]=1;
    do{
      if(c.pc===readEvent&&!c.inIRQ)tokens.add(c.rom[c.r[30]|c.r[31]<<8]);
      c.step();
    }while(c.pc!==completed||c.inIRQ);
    sections.add(c.r[28]);
  }
  assert.equal(c.lost,0);assert.equal(c.workLost,0);assert.equal(c.maxIRQ,12);
  for(let n=0;n<15;n++)assert.ok(sections.has(n));
  for(const token of [0xf2,0xf4,0xf6,0xf8,0xff])assert.ok(tokens.has(token));
});
