import {test} from 'node:test';
import {assertLpxRecordedSource} from './helpers/lpx-source-transition.mjs';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const folder='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/';

test('one universal v9 decoder includes sparse80 under 5% program growth with exact IRQ playback',()=>{
  const r=JSON.parse(read(folder+'v9-sparse80-measurements.json'));
  assert.equal(r.schema,'lpx-v9-sparse80-admission-v1');
  assert.equal(r.baseline_revision,'e32e0c66');
  assert.deepEqual(r.profiles,[4,6,15]);
  assert.equal(r.parameters,'runtime LPX header');
  assert.equal(r.maximum_program_growth_percent,5);
  assert.equal(r.baseline_program_bytes,5384);
  assert.equal(r.maximum_program_bytes,5605);
  assert.ok(r.program_growth_percent<=5);
  assert.ok(r.same_queue_program_growth_percent<=2);
  assert.equal(r.queue,32);assert.equal(r.prefill,24);
  assert.equal(r.clock_hz,16000000);assert.equal(r.sample_hz,8000);
  assert.equal(r.physical_board_measured,false);assert.equal(r.cases.length,22);
  for(const [path,digest] of Object.entries(r.source_sha256))
    assertLpxRecordedSource(path,digest);
  for(const [path,digest] of Object.entries(r.binary_sha256))assert.equal(sha(read(path)),digest,path);
  assert.ok(r.cases.some(row=>row.profile===15&&row.case==='chego-2k'));
  for(const row of r.cases){
    const a=row.after;
    assert.ok(a.program_excluding_audio_bytes*100<=r.baseline_program_bytes*105);
    assert.ok(a.program_excluding_audio_bytes*100<=r.same_queue_baseline.program_excluding_audio_bytes*105);
    assert.equal(a.underruns,0);assert.equal(a.irq_max,38);assert.equal(row.pwm_exact,true);
    assert.ok(a.min_queue>0&&a.stack_margin>0&&a.flash_bytes<=8192);
    assert.equal(a.static_ram_bytes,433);
    assert.equal(a.static_ram_bytes+a.stack_bytes+a.stack_margin,511);
    assert.equal(a.decode_cycles,a.decode_cpu_cycles+a.decode_irq_cycles);
    assert.equal(a.decode_irq_cycles%38,0);
    assert.equal(row.total_active_cycles_per_sample,a.decode_active_cpu_mean+38);
    assert.ok(row.total_active_cycles_per_sample<2000);
    assert.ok(row.repack.file_bytes<=row.repack.input_bytes-9);
    assert.ok(row.repack.payload_bits<=row.repack.input_payload_bits);
    if(row.before){
      assert.equal(a.samples,row.before.samples);
      assert.equal(a.embedded_audio_bytes,row.before.embedded_audio_bytes);
    }
  }
  const example=r.cases.find(row=>row.case==='chego-2k');
  assert.ok(example.repack.file_bytes*64000/example.after.samples<=2000);
  assert.equal(example.repack.input_bytes,307);assert.equal(example.repack.file_bytes,297);
});
