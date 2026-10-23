import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {rr,immediate,out,put} from './helpers/avr-test-state.mjs';

// DS40002307A chapters11,13,14,16,17. Source-only machine-code fixtures;
// no AVR compiler, binary fixtures or per-instruction JS callbacks are needed.
const deviceURL=process.env.MICROMUSIC_DEVICE_MODULE
  ? pathToFileURL(process.env.MICROMUSIC_DEVICE_MODULE)
  : new URL('../lib/attiny13a.js',import.meta.url);
const {ATtiny13A}=await import(deviceURL.href);
const IO={ADCSRB:3,ADCL:4,ADCH:5,ADCSRA:6,ADMUX:7,ACSR:8,
  PCMSK:0x15,EECR:0x1c,EEDR:0x1d,EEARL:0x1e,OCR0B:0x29,
  TCCR0A:0x2f,TCNT0:0x32,TCCR0B:0x33,MCUCR:0x35,OCR0A:0x36,
  SPMCSR:0x37,TIFR:0x38,GIFR:0x3a};
const ldi=(d,k)=>immediate(0xe000,d,k);
const jump=(from,to)=>0xc000|((to-from-1)&0xfff);
function image(words){
  const rom=new Uint8Array(1024).fill(255);
  words.forEach((word,pc)=>put(rom,pc,word));put(rom,words.length,0xcfff);
  return rom;
}
const make=(words=[],options={})=>new ATtiny13A(image(words),null,{fuseLow:0x7a,...options});
const write=(address,value)=>[ldi(16,value),out(address,16)];
const adcValue=c=>c.readIO(IO.ADCL)|(c.readIO(IO.ADCH)<<8);
const at=c=>c.state().baseHalf;

for(const [source,flag,compare] of [[3,4,IO.OCR0A],[4,2,null],[5,8,IO.OCR0B]])
test(`Timer0 source${source} triggers ADC from flag edges without enabling its IRQ`,()=>{
  const c=make([
    ...write(IO.ADMUX,1),...write(IO.ADCSRB,source),...write(IO.ADCSRA,0xa0),
    ...write(IO.TCNT0,source===4?250:0),...(compare===null?[]:write(compare,2)),
    ...write(IO.TCCR0B,1),
  ]);
  c.setAnalog({at:0n,pin:2,microvolts:2500000});c.runUntil(200n);
  assert.equal(c.readIO(IO.TIFR)&flag,flag);assert.equal(c.readIO(IO.ADCSRA)&0x10,0x10);
  assert.equal(adcValue(c),512);assert.equal(c.state().irqs,0);
  c.writeIO(IO.ADCSRA,0xb0);c.runUntil(at(c)+800n);
  assert.equal(c.readIO(IO.ADCSRA)&0x10,0,'Held timer flag cannot retrigger');
  c.writeIO(IO.TIFR,flag);c.runUntil(at(c)+700n);
  assert.equal(c.readIO(IO.ADCSRA)&0x10,0x10);assert.equal(adcValue(c),512);
  assert.equal(c.state().deviceFault,0);
});

test('comparator ACI routes to ADC without ACIE and retriggers after ACI W1C',()=>{
  const c=make([...write(IO.ADMUX,1),...write(IO.ADCSRB,1),...write(IO.ADCSRA,0xa0)]);
  c.setAnalog({at:0n,pin:2,microvolts:1250000});
  c.setAnalog({at:21n,pin:0,microvolts:2000000});c.runUntil(200n);
  assert.equal(c.readIO(IO.ACSR)&0x38,0x30);assert.equal(adcValue(c),256);
  assert.equal(c.readIO(IO.ADCSRA)&0x10,0x10);assert.equal(c.state().irqs,0);
  c.writeIO(IO.ADCSRA,0xb0);c.runUntil(at(c)+100n);
  assert.equal(c.readIO(IO.ADCSRA)&0x10,0);
  c.writeIO(IO.ACSR,0x10);c.setAnalog({at:at(c)+1n,pin:0,microvolts:0});
  c.runUntil(at(c)+100n);assert.equal(c.readIO(IO.ACSR)&0x30,0x10);
  assert.equal(c.readIO(IO.ADCSRA)&0x10,0x10);assert.equal(adcValue(c),256);
});

for(const [source,pinMask,flag] of [[2,2,0x40],[6,1,0x20]])
test(`external interrupt source${source} triggers ADC even with its vector disabled`,()=>{
  const c=make([...write(IO.ADMUX,1),...write(IO.ADCSRB,source),...write(IO.ADCSRA,0xa0),
    ...write(IO.MCUCR,3),...write(IO.PCMSK,pinMask)]);
  c.setAnalog({at:0n,pin:2,microvolts:5000000});
  c.injectPins({at:41n,mask:pinMask,levels:pinMask});c.runUntil(220n);
  assert.equal(c.readIO(IO.GIFR)&flag,flag);assert.equal(c.readIO(IO.ADCSRA)&0x10,0x10);
  assert.equal(adcValue(c),1023);assert.equal(c.state().irqs,0);
});

test('EEPROM programming advances while CPU runs and EERE charges four extra cycles',()=>{
  const c=make();c.writeIO(IO.EEARL,3);c.writeIO(IO.EEDR,0x5a);
  c.writeIO(IO.EECR,4,4);const before=c.state().cycles;
  assert.equal(c.writeIO(IO.EECR,2,2),2);assert.equal(c.state().cycles-before,2);
  assert.equal(c.readIO(IO.EECR)&2,2);assert.equal(c.eeprom[3],255);
  c.runUntil(100000n);assert.equal(c.readIO(IO.EECR)&2,0);assert.equal(c.eeprom[3],0x5a);
  c.writeIO(IO.EEDR,0);const readBefore=c.state().cycles;
  assert.equal(c.writeIO(IO.EECR,1,1),4);assert.equal(c.state().cycles-readBefore,4);
  assert.equal(c.readIO(IO.EEDR),0x5a);assert.equal(c.state().deviceFault,0);
});

function flashRewrite(){
  const words=[ldi(30,0),ldi(31,1),...write(IO.SPMCSR,3),0x95e8];
  // Program page0x100 with LDI r20,0x5a; RJMP self. Initial translated code
  // instead sets0x11, so executing a stale compiled block gives a distinct result.
  for(const [offset,word] of [[0,ldi(20,0x5a)],[2,0xcfff]])words.push(
    ldi(30,offset),ldi(16,word&255),rr(0x2c00,0,16),
    ldi(16,word>>8),rr(0x2c00,1,16),...write(IO.SPMCSR,1),0x95e8,
  );
  words.push(ldi(30,0),...write(IO.SPMCSR,5),0x95e8);
  words.push(jump(words.length,128));
  const rom=image(words);put(rom,128,ldi(20,0x11));put(rom,129,0xcfff);
  return rom;
}
test('SPM erase/write halts translated CPU and replaces generated code before execution',()=>{
  const c=new ATtiny13A(flashRewrite(),null,{fuseLow:0x7a,fuseHigh:0xef,spmCommandCycles:4});
  const original=c._translated;assert.equal(c._exports.avr_device_generation(),0n);
  c.runUntil(200000n);
  assert.equal(c._exports.avr_device_generation(),2n);assert.notEqual(c._translated,original);
  assert.deepEqual(Array.from(c.rom.slice(256,260)),[0x4a,0xe5,0xff,0xcf]);
  assert.equal(c.r[20],0x5a);assert.equal(c.state().sleeping,false);
  assert.equal(c.state().deviceFault,0);
});
test('SELFPRGEN-disabled fuse leaves Flash and its compiled generation unchanged',()=>{
  const c=new ATtiny13A(flashRewrite(),null,{fuseLow:0x7a,fuseHigh:0xff,spmCommandCycles:4});
  const original=c._translated;c.runUntil(1000n);
  assert.equal(c._exports.avr_device_generation(),0n);assert.equal(c._translated,original);
  assert.equal(c.r[20],0x11);assert.equal(c.state().deviceFault,0);
});

test('SPM invalidates native wait-loop metadata together with generated code',()=>{
  const rom=flashRewrite();put(rom,128,0xcfff);
  const c=new ATtiny13A(rom,null,{fuseLow:0x7a,fuseHigh:0xef,spmCommandCycles:4});
  assert.equal(c.idle[128],1);c.runUntil(200000n);
  assert.equal(c.r[20],0x5a);assert.equal(c.idle[128],0);
  assert.equal(c.state().deviceFault,0);
});

test('fuse/lock LPM recognizes RFLB before charging its own three cycles',()=>{
  for(const [z,expected] of [[0,0x7a],[1,0xff],[3,0xff]])for(const gap of [0,2,3]){
    const words=[ldi(30,z),ldi(31,0),...write(IO.SPMCSR,9),...Array(gap).fill(0),0x9005|(20<<4)];
    const c=make(words);c.run(5+gap);
    assert.equal(c.r[20],gap<3?expected:c.rom[z],`${z}/${gap}`);
    assert.equal(c.r[30],z+1);assert.equal(c.state().cycles,7+gap);
  }
});
