import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const folder='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/';

test('v9 preserves every measured waveform while shrinking data and universal code with IRQs',()=>{
  const r=JSON.parse(read(folder+'v9-measurements.json'));
  const old=JSON.parse(read(folder+'universal-measurements.json'));
  assert.equal(r.schema,'lpx-v9-attiny88-admission-v1');
  assert.equal(r.parameters,'runtime LPX header');assert.equal(r.physical_board_measured,false);
  assert.equal(r.clock_hz,16000000);assert.equal(r.sample_hz,8000);assert.equal(r.queue,44);
  assert.equal(r.cases.length,14);
  assert.equal(r.pulse_pair_irq_check.pairs,400);
  assert.equal(r.pulse_pair_irq_check.pwm_exact,true);
  assert.equal(r.pulse_pair_irq_check.after.samples,16000);
  assert.equal(r.pulse_pair_irq_check.after.underruns,0);
  assert.equal(r.pulse_pair_irq_check.after.irq_max,42);
  for(const [path,digest] of Object.entries(r.source_sha256))
    assert.equal(sha(read(path).toString('utf8').replaceAll('\r\n','\n')),digest,path);
  for(const row of r.cases){
    const {before:b,after:a,repack:p}=row;
    assert.equal(row.pwm_exact,true);
    assert.equal(row.pwm_sha256,old.cases.find(x=>x.case===row.case).pwm_sha256);
    assert.equal(p.version,9);assert.equal(p.source_version,5);
    assert.ok(p.payload_bits<=p.input_payload_bits);
    assert.ok(p.file_bytes<=p.input_bytes-9);
    assert.equal(a.embedded_audio_bytes,p.file_bytes);assert.equal(b.embedded_audio_bytes,p.input_bytes);
    assert.equal(a.flash_bytes,a.program_excluding_audio_bytes+a.embedded_audio_bytes);
    assert.ok(a.program_excluding_audio_bytes<b.program_excluding_audio_bytes);
    assert.ok(a.program_excluding_audio_bytes>=5424&&a.program_excluding_audio_bytes<=5425);
    assert.ok(a.decode_active_irq_mean<=b.decode_active_irq_mean);
    assert.equal(a.samples,b.samples);assert.equal(a.samples,p.samples);
    assert.equal(a.static_ram_bytes,447);assert.equal(a.stack_bytes,60);assert.equal(a.stack_margin,4);
    assert.equal(a.irq_max,42);assert.equal(a.underruns,0);assert.ok(a.min_queue>0);
    assert.ok(a.flash_bytes<=8192&&a.output_gap_min>=1980&&a.output_gap_max<=2020);
  }
});
