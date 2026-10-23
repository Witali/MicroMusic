import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

// CKDIV8 gives1.2MHz at the explicit9.6MHz source fixture. BOD is disabled.
// These are CPU EEPROM operations; no external programmer is involved.
const make=(uv,mode=0)=>{
  const eeprom=new Uint8Array(64).fill(255);if(mode===1)eeprom[4]=0;
  return new ATtiny13A(Uint8Array.of(255,207),eeprom,{vccMicrovolts:uv,fuseLow:0x6a});
};
function start(c,mode){
  c.writeIO(IO.EEARL,4);c.writeIO(IO.EEDR,42);
  c.writeIO(IO.EECR,(mode<<4)|4);c.writeIO(IO.EECR,(mode<<4)|2);
}
for(const uv of [1800000,1899999])for(const mode of [0,1,2])
  test(`fixed supply ${uv}uV diagnoses uncertainty for EEPROM mode${mode} without a power profile`,()=>{
    const c=make(uv,mode),before=c.eeprom[4];
    assert.throws(()=>start(c,mode),/peripheral fault 5, detail 128/);
    assert.equal(c.state().powerResetEnabled,undefined);assert.equal(c.state().deviceFault,5);
    assert.equal(c.eeprom[4],before,'retain the last-known byte, not a fabricated failure pattern');
    c._exports.avr_clock(10000);c._exports.avr_read_io(IO.EECR);
    assert.equal(c.eeprom[4],before,'later clock/read must not complete the uncertain write');
  });
for(const uv of [1900000,5000000])for(const mode of [0,1,2])
  test(`fixed supply ${uv}uV retains documented EEPROM mode${mode} completion`,()=>{
    const c=make(uv,mode);start(c,mode);c.clock(10000);
    assert.equal(c.eeprom[4],mode===1?255:42);assert.equal(c.state().deviceFault,0);
  });
test('the EEPROM low-voltage write erratum does not reject a fixed-supply read',()=>{
  const eeprom=new Uint8Array(64).fill(255);eeprom[4]=42;
  const c=new ATtiny13A(Uint8Array.of(255,207),eeprom,{vccMicrovolts:1800000,fuseLow:0x6a});
  c.writeIO(IO.EEARL,4);c.writeIO(IO.EECR,1);
  assert.equal(c.readIO(IO.EEDR),42);assert.equal(c.state().deviceFault,0);
});
