import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATmega328P,ATMEGA328P_PROFILE,resolveATmega328PProfile,tickATmega328P} from '../lib/atmega328p.js';
import {createRenderer} from '../lib/engines.js';
import {timerProgram,speechEntry} from './helpers/atmega-speech-fixture.mjs';

test('ATmega328P owns real AVR5 memory geometry and cannot masquerade as Tiny88',async()=>{
  assert.equal(ATMEGA328P_PROFILE.flashBytes,32768);assert.equal(ATMEGA328P_PROFILE.ramEnd,0x8ff);
  assert.equal(ATMEGA328P_PROFILE.sramStart,0x100);assert.equal(ATMEGA328P_PROFILE.eepromBytes,1024);
  const core=new ATmega328P(timerProgram());
  assert.equal(core.cpu.data.length,2304);assert.equal(core.cpu.progBytes.length,32768);
  assert.equal(core.eeprom.memory.length,1024);assert.equal(core.cpu.SP,0x8ff);
  for(const target of ['attiny88','attiny13a',null])assert.throws(()=>resolveATmega328PProfile(target));
  assert.throws(()=>new ATmega328P(timerProgram(),null,{cpuHz:8000000}));
  assert.throws(()=>new ATmega328P(new Uint8Array(32769)));
  assert.throws(()=>new ATmega328P(timerProgram(),new Uint8Array(1025)));
  assert.throws(()=>new ATmega328P(timerProgram(),null,{pwmOutput:'OC0B'}));
  for(const engine of ['js','wasm','transpiled','device'])await assert.rejects(createRenderer(speechEntry(),48000,{},engine),/requires the AVR8js/);
  for(const device of ['attiny13a','attiny88'])await assert.rejects(createRenderer({...speechEntry(),device},48000,{},'avr8js'),/only ATmega328P/);
});

test('SEI/RETI defer one instruction while clock events progress and IRQ entry costs four cycles',()=>{
  const core=new ATmega328P(timerProgram()),cpu=core.cpu;
  const irq={address:0x16,flagRegister:0x36,flagMask:2,enableRegister:0x6f,enableMask:2};
  cpu.data[0x6f]=2;cpu.setInterruptFlag(irq);cpu.data[0x5f]=128;
  let event=0;cpu.addClockEvent(()=>event++,1);cpu.cycles=1;
  assert.equal(tickATmega328P(cpu,false),false);assert.equal(event,1);assert.equal(cpu.pc,0);
  const before=cpu.cycles;
  assert.equal(tickATmega328P(cpu,true),true);assert.equal(cpu.cycles-before,4);assert.equal(cpu.pc,0x16);
  assert.equal(cpu.SP,0x8fd);assert.equal(cpu.interruptsEnabled,false);
});

for(const pwmOutput of ['OC2B','OC1A'])test(pwmOutput+': independent sample/PWM timers, MUL and GPIO execute together with active IRQ',()=>{
  const core=new ATmega328P(timerProgram(pwmOutput),null,{pwmOutput}),writes=[];
  core.onPwmWrite=(value,cycles)=>writes.push([value,cycles]);
  const captured=core.captureAudio(240,48000);
  assert.equal(core.data[0x100],67);assert.equal(core.data[0x101],1,'17 * 19 uses the AVR MUL result');
  assert.equal(writes[0][0],128);assert.ok(writes.length>=39);
  for(let n=1;n<writes.length;n++)assert.equal(writes[n][0],n*19&255);
  const periods=writes.slice(2).map((write,index)=>write[1]-writes[index+1][1]);
  // IRQ delivery occurs at instruction/event boundaries; there is no drift
  // from the independent 2000-cycle sample clock.
  assert.ok(periods.every(cycles=>cycles>=1996&&cycles<=2004));
  assert.ok(Math.abs(writes.at(-1)[1]-writes[1][1]-(writes.length-2)*2000)<=4);
  assert.equal(core.state().timerLost,0);assert.ok(core.state().irqs>=39);
  assert.ok(core.state().maxISR>=9);assert.equal(core.state().minimumSP,0x8fd);
  assert.ok(core.state().pinEdges>400);assert.ok(captured.physical.every(Number.isFinite));
  assert.ok(captured.physical.some(value=>value!==captured.registers[0]));
  assert.ok(captured.registers.some(value=>value>0));assert.ok(captured.registers.some(value=>value<0));
});

test('Arduino resampling, physical PWM/filtering and control smoothing preserve arbitrary block boundaries',async()=>{
  const entry=speechEntry(),a=await createRenderer(entry,48000,{},'avr8js'),b=await createRenderer(entry,48000,{},'avr8js');
  assert.equal(a.physicalAudio,true);assert.equal(a.engine,'avr8js');
  const expected=a.render(400),parts=[];
  for(const count of [1,17,128,254])parts.push(...b.render(count));
  assert.deepEqual(Float32Array.from(parts),expected);assert.deepEqual(b.core.state(),a.core.state());
  const before=b.core.cyc;b.setAudioControls({cutoff:3000,volume:0});assert.equal(b.core.cyc,before);
  assert.ok(b.render(1000).every(Number.isFinite));
  for(const count of [0,-1,1.5,16385,NaN])assert.throws(()=>b.render(count),/block size/);
  for(const rate of [7999,192001,NaN])await assert.rejects(createRenderer(entry,rate,{},'avr8js'),/sample rate/);
});
