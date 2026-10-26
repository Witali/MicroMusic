import {test} from 'node:test';
import assert from 'node:assert/strict';
import {coreProbeCases,crc16,decodeCoreProbe} from '../scripts/lib/avr-core-probe-cases.mjs';
const descriptor={buildId:[1,2,3,4]};
const seal=p=>{p[7]=0;const crc=crc16([...p.subarray(0,14),...p.subarray(16)]);p[14]=crc;p[15]=crc>>8;p[7]=0xa5;return p;};
function packet(overhead=5){
  const p=new Uint8Array(64);p.set([65,86,82,49,1,12,12,0,...descriptor.buildId,overhead&255,overhead>>8]);
  coreProbeCases.forEach((c,n)=>{const delta=(overhead+c.cycles)&65535;p.set([c.result,c.sreg,delta&255,delta>>8],16+4*n);});
  return seal(p);
}
test('CRC16-CCITT-FALSE matches the published check value',()=>{
  assert.equal(crc16(new TextEncoder().encode('123456789')),0x29b1);
});
test('core acquisition record preserves all case values, flags and calibrated cycles',()=>{
  for(const overhead of [5,65534]){
    const result=decodeCoreProbe(packet(overhead),descriptor);
    assert.equal(result.passedCases,12);assert.equal(result.passed,true);assert.equal(result.overheadTicks,overhead);
    assert.deepEqual(result.cases.map(c=>c.cycles),[1,1,1,1,1,1,1,1,3,3,4,8]);
    assert.equal('hardwareTested' in result,false,'Decoding alone must not claim hardware evidence');
  }
});
test('single-bit corruption at every record bit is rejected, including completion and CRC',()=>{
  const original=packet();
  for(let bit=0;bit<512;bit++){
    const p=original.slice();p[bit>>3]^=1<<(bit&7);
    assert.throws(()=>decodeCoreProbe(p,descriptor),undefined,'bit '+bit);
  }
});
test('wrong size, incomplete/stale runs and wrong build IDs fail closed',()=>{
  for(const n of [0,63,65])assert.throws(()=>decodeCoreProbe(new Uint8Array(n),descriptor),/64/);
  const p=packet();p[7]=0;assert.throws(()=>decodeCoreProbe(p,descriptor),/incomplete/);
  assert.throws(()=>decodeCoreProbe(packet(),{buildId:[4,3,2,1]}),/build ID/);
  assert.throws(()=>decodeCoreProbe(packet(),null),/build ID/);
  for(const at of [0,4,5]){const p=packet();p[at]++;seal(p);assert.throws(()=>decodeCoreProbe(p,descriptor),/Unsupported/);}
});
test('valid CRC cannot hide result, SREG or timing failures or a forged pass count',()=>{
  for(const at of [16,17,18,19]){
    const p=packet();p[at]^=1;seal(p);
    assert.throws(()=>decodeCoreProbe(p,descriptor),/pass count/);
    p[6]=11;seal(p);const result=decodeCoreProbe(p,descriptor);
    assert.equal(result.passed,false);assert.equal(result.passedCases,11);assert.equal(result.cases[0].passed,false);
  }
});
