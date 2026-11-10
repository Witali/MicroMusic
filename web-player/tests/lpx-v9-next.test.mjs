import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const folder='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/';

test('v9 word metadata shrinks program/SRAM while C reference, data, CPU time and IRQ output stay exact',()=>{
  const r=JSON.parse(read(folder+'v9-next-measurements.json'));
  const current=JSON.parse(read(folder+'v9-measurements.json'));
  assert.equal(r.schema,'lpx-v9-next-admission-v1');assert.equal(r.baseline_revision,'f7481ef9');
  assert.equal(r.physical_board_measured,false);assert.equal(r.cases.length,14);
  assert.equal(r.queue,44);assert.equal(r.clock_hz,16000000);assert.equal(r.sample_hz,8000);
  for(const [path,digest] of Object.entries(r.source_sha256))
    assert.equal(sha(read(path).toString('utf8').replaceAll('\r\n','\n')),digest,path);
  assert.deepEqual(r.c_reference_validation,{backend_define:'LPX4_ENABLE_ASM=0',batch_tests:5,
    core_tests:4,compact_versions:[5,9],public_count_bits:32,v9_stored_count_bits:16});
  for(const row of r.cases){
    const {before:b,after:a}=row;
    assert.equal(b.program_excluding_audio_bytes-a.program_excluding_audio_bytes,34);
    assert.equal(b.static_ram_bytes-a.static_ram_bytes,2);
    assert.equal(a.embedded_audio_bytes,b.embedded_audio_bytes);assert.equal(a.samples,b.samples);
    assert.equal(a.stack_bytes,b.stack_bytes);assert.equal(a.stack_margin,b.stack_margin+2);
    assert.equal(a.decode_cpu_cycles,b.decode_cpu_cycles);assert.equal(a.decode_mean,b.decode_mean);
    assert.equal(a.underruns,0);assert.equal(a.irq_max,42);assert.equal(row.pwm_exact,true);
    assert.ok(a.min_queue>0&&a.flash_bytes<=8192);
    assert.match(row.data_sha256,/^[a-f0-9]{64}$/);
    for(const item of [a,b]){
      assert.equal(item.decode_cycles,item.decode_cpu_cycles+item.decode_irq_cycles);
      assert.equal(item.decode_irq_cycles%42,0);
    }
    const matched=current.cases.find(item=>item.case===row.case);
    assert.equal(row.pwm_sha256,matched.pwm_sha256);
    assert.equal(a.program_excluding_audio_bytes,matched.after.program_excluding_audio_bytes);
  }
});
