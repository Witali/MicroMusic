import assert from 'node:assert/strict';
import test from 'node:test';
import {PIC16F1503} from '../web/pic16-core.mjs';

/* Independently originated assertions from gpsim's PIC16F1503 regression:
 * https://github.com/jonathan-stark/gpsim/blob/master/regression/p1xf18xx/p16f1503.asm
 * Compared against the Microchip DS40001607D register definitions, because
 * an external simulator's tests are useful evidence, not silicon authority.
 * This file does NOT execute gpsim or its original regression binary.
 */
const cpu=()=>new PIC16F1503();
const masks=[
  ['PIR1',0x011,0xCB], ['PIR2',0x012,0x6C],
  ['PIE1',0x091,0xCB], ['PIE2',0x092,0x6C],
];
for(const [name,addr,mask] of masks){
  test(`gpsim reference ${name}: reserved bits read as zero`,()=>{
    const c=cpu();c.setMemory(addr,0xFF);
    assert.equal(c.getMemory(addr),mask);
    c.setMemory(addr,0);assert.equal(c.getMemory(addr),0);
  });
}
test('gpsim reference TRISA: RA3 input-only regardless of writes',()=>{
  const c=cpu();c.setMemory(0x08c,0x00);
  assert.equal(c.getMemory(0x08c),0x08);
  c.setMemory(0x08c,0xff);assert.equal(c.getMemory(0x08c),0x3f);
});
test('gpsim reference INTCON: IOCIF not software-writeable',()=>{
  const c=cpu();c.setMemory(0x0b,0x7f);assert.equal(c.getMemory(0x0b),0x7e);
});
test('PIC16F1503 official OSCSTAT: 16MHz ready nominal bits only',()=>{
  const c=cpu();assert.equal(c.foscHz,500000);
  c.setMemory(0x099,0x78);c.advanceCycles(4);
  assert.equal(c.foscHz,16000000);
  assert.equal(c.getMemory(0x09a)&0x1f,0x13);
  // gpsim 2017 regression expects 0x19; that sets reserved bit 3
  // and drops LFIOFR (bit 1). Official DS40001607D is authoritative.
});
test('PWM3 still enabled when TRISA2 clears while RA3 remains input',()=>{
 const c=cpu();c.setMemory(0x08c,0);c.setMemory(0x18c,0);c.setMemory(0x619,0xc0);
 assert.equal(c.pwmOutputEnabled,true);
});
test('ISR sees only the implemented PIR1 flags',()=>{
 const c=cpu();c.setMemory(0x011,0x34);c.setMemory(0x091,0xff);c.setMemory(0x0b,0xc0);
 assert.equal(c.getMemory(0x011),0x00);
 assert.equal(c.getMemory(0x091),0xcb);
 assert.equal(c.irqCount,0);
});
for(const [name,bsr,file,value,expected] of [
 ['PIR1',0,0x11,0xFF,0xCB],
 ['PIE1',1,0x11,0xFF,0xCB],
 ['TRISA',1,0x0C,0x00,0x08],
 ['INTCON',0,0x0B,0x7F,0x7E]
]){
 test(`real PIC opcodes honor ${name} implemented-bit mask`,()=>{
  // MOVLB bank, MOVLW literal, MOVWF file, MOVF file,W.
  const code=new Uint16Array(2048).fill(0);
  code.set([0x0020|bsr,0x3000|value,0x0080|file,0x0800|file]);
  const c=new PIC16F1503(code);
  for(let i=0;i<4;i++)assert.equal(c.step(),1);
  assert.equal(c.W,expected);
  assert.equal(c.getMemory((bsr<<7)|file),expected);
 });
}
