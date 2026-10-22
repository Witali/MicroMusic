const fs=require('fs'),path=require('path'),assert=require('assert');
const {AVRCore}=require('./avr_emulator.js');
const dir=path.join(__dirname,'samples','demo');
const hex=fs.readFileSync(path.join(dir,'firmware.hex'),'utf8');
const expected=fs.readFileSync(path.join(dir,'expected_pcm.raw'));
const cpu=AVRCore.fromHex(hex);
for(let i=0;i<expected.length;i++){const out=cpu.takeSample();assert.strictEqual(out,expected[i],'PCM mismatch at sample '+i)}
assert.equal(cpu.missedOverflows,0);
console.log('Synthetic demo passed:',expected.length,'audio samples, no Timer0 misses');
