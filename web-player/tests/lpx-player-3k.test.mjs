import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {assertLpxRecordedSource} from './helpers/lpx-source-transition.mjs';

const root=new URL('../../',import.meta.url);
const directory='Codecs/LPX/research/avr-player-3k-2026-11-17/';
const read=path=>readFileSync(new URL(path,root));
const json=path=>JSON.parse(read(path));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');

test('the complete three-rate Nano player fits 3 KiB and keeps exact IRQ playback',()=>{
  const report=json(directory+'sampling-rates.json');
  assert.equal(report.physical_board_measured,false);
  assert.equal(report.higher_rate_fixtures,'header-retagged timing probes');
  assert.equal(report.cases.length,132);
  const paired=json(directory+'rates-measurements.json');
  const before=new Map(paired.cases.map(row=>[row.target+'/'+row.case,row.before]));
  for(const [path,digest] of Object.entries(report.source_lf_sha256))assertLpxRecordedSource(path,digest);
  for(const target of ['atmega328p','attiny88'])for(const rate of [8000,12000,16000]){
    const rows=report.cases.filter(row=>row.target===target&&row.rate===rate);
    assert.equal(rows.length,22);
    assert.equal(new Set(rows.map(row=>row.case)).size,22);
    if(target==='atmega328p'||rate===8000)assert.ok(rows.every(row=>row.accepted));
    for(const row of rows){
      assert.ok(row.irq_max<=before.get(target+'/'+row.case).irq_max);
      assert.ok((target==='atmega328p'?[35,36]:[35]).includes(row.irq_max));
      assert.equal(row.irq_entry_cycles,4);
      assert.equal(row.irq_reti_complete,true);
      assert.equal(row.producer_calls,row.decode_calls);
      assert.equal(row.producer_unpublished_decode_calls,0);
      assert.equal(row.samples,row.producer_calls+row.underruns);
      assert.equal(row.static_ram_bytes,target==='atmega328p'?417:418);
      assert.ok(row.stack_bytes<=(target==='atmega328p'?24:27));
      if(target==='atmega328p')assert.ok(row.program_excluding_audio_bytes<=3072);
      assert.equal(row.sample_period_cycles,rate===8000?2000:rate===16000?1000:target==='atmega328p'?1333:1336);
      assert.equal(row.actual_sample_hz,16000000/row.sample_period_cycles);
      if(row.accepted){assert.equal(row.underruns,0);assert.equal(row.pwm_exact,true);}
      else{assert.equal(target,'attiny88');assert.notEqual(rate,8000);assert.ok(row.underruns>0);}
    }
  }
  assert.equal(paired.cases.length,44);
  for(const row of paired.cases){
    assert.equal(row.after.pwm_sha256,row.before.pwm_sha256);
    for(const key of ['producer_cpu_mean','producer_cpu_max','producer_active_cpu_mean','producer_active_cpu_max'])
      assert.ok(row.after[key]+row.after.irq_max<=row.before[key]+row.before.irq_max,key);
  }
});

test('rate-aware source encoding and selectable C/ASM controls retain their evidence',()=>{
  const report=json(directory+'rate-contract/final.json');
  assert.equal(report.frontend.tests,7);assert.equal(report.frontend.passed,true);
  assert.equal(report.exhaustive_fs.rate_field_checks,1048576);
  assert.equal(report.exhaustive_fs.passed,true);
  assert.equal(report.total_irq_runs,20);
  assert.ok(report.disabled8k_controls.every(row=>row.binary_exact_vs_optimized_pre_rate&&row.pwm_exact_vs_optimized_pre_rate));
  for(const [name,digest] of Object.entries(report.artifact_sha256))assert.equal(sha(read(directory+'rate-contract/'+name)),digest);
  for(const [path,digest] of Object.entries(report.source_lf_sha256))assertLpxRecordedSource(path,digest);
  const gain=json(directory+'final-gain-proof.json');
  assert.equal(gain.cases.length,4);
  for(const row of gain.cases){
    assert.equal(row.cases,32768);assert.equal(row.error,0);assert.equal(row.zero_error,0);
    assert.equal(row.done,1);assert.ok(row.irqs>0);
  }
});

test('all 18 WebUI images retain exact media and the single-stream Nano size cap',()=>{
  const report=json(directory+'web-rebuild.json');
  assert.equal(report.cases.length,18);
  assert.equal(report.release_checks.total_samples,345470);
  assert.equal(report.release_checks.all_whole_producer_mean_peak_no_slower,true);
  assert.equal(report.independent_rebuild.all_binaries_exact,true);
  assert.equal(report.independent_rebuild.all_no_float_runtime_symbols,true);
  assert.equal(Object.keys(report.protected_asset_sha256).length,26);
  for(const [path,digest] of Object.entries(report.protected_asset_sha256))assert.equal(sha(read(path)),digest);
  const nano=json('web-player/firmware-atmega328p.json');
  for(const row of report.cases){
    assert.equal(row.pwm_exact,true);assert.equal(row.after.accepted,true);assert.equal(row.after.underruns,0);
    assert.equal(row.after.stream,row.before.stream);
    assert.ok(row.after.ram<=row.before.ram);assert.ok(row.after.stack<=row.before.stack);
    assert.equal(sha(read(row.source)),row.hex_sha256);
    if(row.family==='nano'){
      assert.ok(row.after.program<=3072);
      const variant=nano.variants.find(v=>v.clipId+'-'+v.id===row.id);
      assert.equal(variant.programFlashBytes,row.after.program);
      assert.equal(row.after.flash,row.before.flash-60);
    }else if(row.family==='tiny')assert.ok(row.after.flash<=6012);
  }
  const vectors=json(directory+'irq-vectors.json');
  assert.equal(vectors.cases.length,132);
  assert.ok(vectors.cases.every(row=>row.irq_delta===0));
  assert.equal(vectors.groups.atmega328p.isr_body_cycles,29);
  assert.equal(vectors.groups.attiny88.isr_body_cycles,29);
  const arithmetic=json(directory+'arithmetic-audit.json');
  assert.equal(arithmetic.passed,true);
  assert.equal(arithmetic.whole_c_fallback_control_valid_pwm,true);
  assert.equal(arithmetic.selection_cases,12);
  assert.ok(arithmetic.atmega328_328p_control_binary_identity.every(row=>row.binary_identical));
  for(const [name,digest] of Object.entries(arithmetic.evidence_sha256))assert.equal(sha(read(directory+name)),digest);
  for(const path of ['web-player/app.js','web-player/index.html','web-player/lib/tiny88-preview.js'])
    assert.match(read(path).toString(),/20261117-lpx-3k-rates/);
});
