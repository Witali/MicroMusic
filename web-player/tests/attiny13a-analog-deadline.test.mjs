import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';

// Candidate-module selection permits cross-worktree checks against the complete
// root runtime without copying production changes into this test-only branch.
const deviceURL=process.env.MICROMUSIC_DEVICE_MODULE
  ? pathToFileURL(process.env.MICROMUSIC_DEVICE_MODULE)
  : new URL('../lib/attiny13a.js',import.meta.url);
const {ATtiny13A}=await import(deviceURL.href);
const firmware=flash(
  {instructions:[avr.rjmp(0,16)]},
  {at:5,instructions:[avr.rjmp(5,64)]},
  {at:16,instructions:[...Array.from({length:40},()=>avr.inc(16)),avr.rjmp(56,56)]},
  {at:64,instructions:[avr.sts(0x60,16),avr.reti()]},
);
const table=Array(128).fill(0);table[0]=10000000;
function prepare(physical,future){
  const c=new ATtiny13A(firmware,null,{
    oscillatorHz:10000000,fuseLow:0x72,comparatorPropagationHalf:4,fastIdle:false,
    ...(physical?{osccalHz:table}:{}),
  });
  c.pc=16;c.writeIO(IO.ACSR,8);c.sreg=128; // Comparator toggle IRQ enabled.
  // Current input schedules propagation; future input first schedules its own
  // queue edge. Both must update the deadline seen by generated CPU blocks.
  const at=future?(physical?2000000n:40n):0n;
  if(physical)c.setAnalogPs({at,pin:0,microvolts:3000000});
  else c.setAnalog({at,pin:0,microvolts:3000000});
  // Do not read I/O here: avr_read_io refreshes the native deadline and would
  // accidentally hide the missing refresh in the analog-injection bridges.
  return c;
}
function semanticSnapshot(c){
  const {idleCycles,...state}=c.state(); // Optimization accounting may differ.
  return {state,pc:c.pc,cycles:c.cyc,sp:c.sp,sreg:c.sreg,
    data:Array.from(c.data),eeprom:Array.from(c.eeprom),irqFrames:Array.from(c.irqFrames)};
}

for(const physical of [false,true])for(const future of [false,true]){
  test(`${physical?'physical ps':'legacy half-clock'} ${future?'future':'current-time'} analog input interrupts a generated block at the step-oracle boundary`,()=>{
    const batched=prepare(physical,future),stepped=prepare(physical,future);
    batched.run(40);for(let n=0;n<40;n++)stepped.step();
    // Under this explicit propagation profile the ISR observes4/24 INCs,
    // before the mainline could retire the whole32-instruction fast block.
    assert.equal(stepped.data[0x60],future?24:4);
    assert.equal(batched.data[0x60],stepped.data[0x60],'analog input must refresh the generated block deadline without an intervening I/O read');
    assert.deepEqual(semanticSnapshot(batched),semanticSnapshot(stepped));
    assert.equal(batched.state().deviceFault,0);
  });
}
