import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {AVRCore} from '../lib/avr-core.js';
import {parseHex} from '../lib/hex.js';

for(const name of ['rhythmic','lumiere-stereo','alicia','children','greensleeves','turkish-march'])
test(`${name}: embedded standalone core loads HEX and agrees with WASM`,()=>{
 const base=new URL(`../../ATtiny13A/Music/variants/${name}/`,import.meta.url),read=n=>readFileSync(new URL(n,base),'utf8');
 const html=read('player.html'),embedded=/<script>\s*([\s\S]*?)<\/script>/.exec(html)?.[1];
 assert.ok(embedded);assert.equal(embedded.trim(),read('avr_core.js').trim());
 const context={};runInNewContext(embedded+'\nglobalThis.Standalone=AVRCore;',context);
 const flash=read('synth.hex'),ep=read('eeprom.hex');
 assert.equal(typeof context.Standalone.fromHex,'function');
 const actual=context.Standalone.fromHex(flash,ep),expected=new AVRCore(parseHex(flash),parseHex(ep,64));
 const stereo=JSON.parse(read('build-report.json')).audioChannels===2;
 for(let i=0;i<7500;i++)assert.equal(stereo?actual.nextStereoDuty():actual.nextDuty(),stereo?expected.nextStereoDuty():expected.nextDuty(),`PWM frame ${i}`);
 assert.equal(actual.cyc,expected.cyc);assert.deepEqual(Array.from(actual.r),Array.from(expected.r));
 assert.deepEqual(Array.from(actual.data),Array.from(expected.data));assert.equal(expected.lost+expected.workLost,0);
 assert.throws(()=>context.Standalone.fromHex(':00000001FF',ep),/Incomplete/);
});
