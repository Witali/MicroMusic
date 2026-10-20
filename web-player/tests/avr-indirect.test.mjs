// Post-increment forms from Microchip DS40002198A §§5.66/5.67/5.114.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore} from '../lib/avr-core.js';
const cpu=word=>new AVRCore(Uint8Array.of(word&255,word>>8));

for(const [name,word,pointer] of [['LD r16,X+',0x910d,26],['LD r16,Y+',0x9109,28]]){
  test(`${name}: reads registers, I/O and SRAM, preserves SREG, increments and costs two clocks`,()=>{
    for(const address of [0,7,24,32,56,94,96,127,159])for(let flags=0;flags<256;flags++){
      const c=cpu(word);c.data[address]=0xa5;c.r[pointer]=address;c.r[pointer+1]=0;c.sreg=flags;
      const expected=c.data[address];c.step();
      assert.equal(c.r[16],expected);assert.equal(c.r[pointer]|c.r[pointer+1]<<8,address+1);
      assert.equal(c.sreg,flags);assert.equal(c.cyc,2);assert.equal(c.pc,1);
    }
  });
}

test('ST r16,X+: writes register file and SRAM, preserves flags and increments at the RAM boundary',()=>{
  for(const address of [0,7,24,96,127,159])for(let flags=0;flags<256;flags++){
    const c=cpu(0x930d);c.r[26]=address;c.r[27]=0;c.r[16]=0xa5;c.sreg=flags;c.step();
    assert.equal(c.data[address],0xa5);assert.equal(c.r[26]|c.r[27]<<8,address+1);
    assert.equal(c.sreg,flags);assert.equal(c.cyc,2);assert.equal(c.pc,1);
  }
});

test('ST X+ uses the same peripheral bus as OUT',()=>{
  const c=cpu(0x930d);c.writeIO(0x2f,35);c.writeIO(0x33,1);
  c.r[26]=32+0x29;c.r[16]=201;c.step();
  assert.equal(c.duty,201);assert.equal(c.writes,1);assert.equal(c.cyc,2);
  const d=cpu(0x930d);d.io[0x38]=14;d.r[26]=32+0x38;d.r[16]=2;d.step();
  assert.equal(d.io[0x38],12,'TOV0 uses write-one-to-clear through the data bus');
});

test('post-increment rejects undefined pointer-register operands and invalid data addresses',()=>{
  for(const [word,pointer] of [[0x91ad,26],[0x91bd,26],[0x91c9,28],[0x91d9,28],[0x93ad,26],[0x93bd,26]]){
    const c=cpu(word);c.r[pointer]=96;assert.throws(()=>c.step(),/Undefined/);
  }
  for(const word of [0x910d,0x930d]){
    const c=cpu(word);c.r[26]=160;assert.throws(()=>c.step(),/out of range/);
  }
});
