import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const baseline=JSON.parse(readFileSync(new URL('./fixtures/avr-profile-baseline.json',import.meta.url)));
const root=new URL('../../',import.meta.url);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const read=path=>readFileSync(new URL(path,root));

for(const saved of baseline.entries.filter(e=>e.target==='attiny13a')){
  test(saved.variant+': offline player bundles all shared dependencies and preserves pre-refactor PWM',()=>{
    const folder='ATtiny13A/Music/variants/'+saved.variant+'/';
    const {AVRCore,AVR_PROFILES}=require(fileURLToPath(new URL(folder+'avr_core.js',root)));
    assert.equal(AVR_PROFILES.attiny88.flashBytes,8192);
    assert.ok(read(folder+'player.html').includes(read(folder+'avr_core.js')));
    const report=JSON.parse(read(folder+'build-report.json'));
    assert.equal(report.standaloneCoreSources.normalization,'UTF-8, LF');
    for(const [path,hash] of Object.entries(report.standaloneCoreSources.sha256))
      assert.equal(sha(read(path).toString().replace(/\r\n/g,'\n')),hash,path);
    const cpu=AVRCore.fromHex(read(folder+'synth.hex').toString(),read(folder+'eeprom.hex').toString());
    const pwm=Buffer.alloc(baseline.frames*2);
    for(let i=0;i<baseline.frames;i++)
      pwm.writeUInt16LE(report.audioChannels===2?cpu.nextStereoDuty():cpu.nextDuty(),i*2);
    assert.equal(sha(pwm),saved.pwmSha256);assert.equal(sha(cpu.data),saved.dataSha256);
  });
}

test('the generated offline core also accepts the ATtiny88 profile and its larger HEX image',()=>{
  const {AVRCore}=require(fileURLToPath(new URL('ATtiny13A/Music/variants/rhythmic/avr_core.js',root)));
  const folder='ATtiny88/Music/variants/rhythmic/';
  const cpu=AVRCore.fromHex(read(folder+'synth.hex').toString(),read(folder+'eeprom.hex').toString(),{target:'attiny88'});
  const saved=baseline.entries.find(e=>e.target==='attiny88'&&e.variant==='rhythmic');
  const pwm=Buffer.alloc(baseline.frames*2);
  for(let i=0;i<baseline.frames;i++)pwm.writeUInt16LE(cpu.nextDuty(),i*2);
  assert.equal(sha(pwm),saved.pwmSha256);assert.equal(sha(cpu.data),saved.dataSha256);
});
