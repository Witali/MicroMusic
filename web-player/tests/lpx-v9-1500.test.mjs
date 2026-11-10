import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const folder='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/';

test('v9 reduces decoder plus IRQ work without growing program/data; unmet 1500 target is reported',()=>{
  const r=JSON.parse(read(folder+'v9-1500-measurements.json'));
  const matched=JSON.parse(read(folder+'v9-measurements.json'));
  assert.equal(r.schema,'lpx-v9-1500-admission-v1');
  assert.equal(r.baseline_revision,'883b54cc');
  assert.equal(r.clock_hz,16000000);assert.equal(r.sample_hz,8000);
  assert.equal(r.target_cycles_per_sample,1500);
  assert.equal(r.queue,44);assert.equal(r.parameters,'runtime LPX header');
  assert.equal(r.physical_board_measured,false);assert.equal(r.cases.length,14);
  for(const [path,digest] of Object.entries(r.source_sha256))
    assert.equal(sha(read(path).toString('utf8').replaceAll('\r\n','\n')),digest,path);
  for(const row of r.cases){
    const {before:b,after:a}=row;
    assert.equal(b.program_excluding_audio_bytes-a.program_excluding_audio_bytes,6);
    assert.equal(a.embedded_audio_bytes,b.embedded_audio_bytes);
    assert.equal(a.flash_bytes,b.flash_bytes-6);
    assert.equal(a.static_ram_bytes,b.static_ram_bytes);
    assert.equal(a.stack_bytes,b.stack_bytes);assert.equal(a.stack_margin,b.stack_margin);
    assert.ok(a.decode_cpu_cycles<b.decode_cpu_cycles);
    assert.equal(a.underruns,0);assert.equal(a.irq_max,42);
    assert.ok(a.min_queue>0);assert.equal(row.pwm_exact,true);
    assert.equal(row.after_total_active_cycles_per_sample,a.decode_active_cpu_mean+a.irq_max);
    assert.equal(row.before_total_active_cycles_per_sample,b.decode_active_cpu_mean+b.irq_max);
    assert.ok(row.after_total_active_cycles_per_sample<row.before_total_active_cycles_per_sample);
    assert.ok(row.after_total_active_cycles_per_sample<=1575);
    assert.equal(row.meets_1500_mean_target,row.after_total_active_cycles_per_sample<=1500);
    assert.equal(row.pwm_sha256,matched.cases.find(x=>x.case===row.case).pwm_sha256);
    for(const item of [a,b]){
      assert.equal(item.decode_cycles,item.decode_cpu_cycles+item.decode_irq_cycles);
      assert.equal(item.decode_irq_cycles%42,0);
    }
  }
  assert.equal(r.all_cases_meet_target,r.cases.every(row=>row.meets_1500_mean_target));
  assert.equal(r.cases.filter(row=>row.meets_1500_mean_target).length,6);
});
