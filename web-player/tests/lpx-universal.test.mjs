import {assertHistoricalReceipt} from './helpers/lpx-receipt-history.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const folder='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/';

test('historical universal Tiny88 receipt binds playback and IRQ results to e32e0c66',()=>{
  const receipt=JSON.parse(read(folder+'universal-measurements.json'));
  assert.equal(receipt.schema,'lpx-attiny88-universal-v1');
  assert.equal(receipt.parameters,'runtime LPX header');
  assert.equal(receipt.queue,44);assert.equal(receipt.prefill,33);
  assert.equal(receipt.cases.length,14);assert.equal(receipt.physical_board_measured,false);
  assertHistoricalReceipt('universal-measurements.json',receipt);
  assert.deepEqual(receipt.cases.slice(0,8).map(row=>row.case),[
    'chego-compact','chego-quality','otvechaesh-compact','otvechaesh-quality',
    'vinni-compact','vinni-quality','bread-compact','bread-quality']);
  for(const row of receipt.cases){
    assert.equal(row.pwm_exact,true);assert.equal(row.underruns,0);
    assert.ok(row.samples>0&&row.flash_bytes<=8192&&row.min_queue>0);
    assert.ok(row.program_excluding_audio_bytes>=5471&&row.program_excluding_audio_bytes<=5472);
    assert.equal(row.static_ram_bytes+row.stack_bytes+row.stack_margin,511);
    assert.equal(row.irq_max,42);assert.equal(row.irq_entry_cycles,4);assert.equal(row.irq_reti_complete,true);
    assert.ok(row.output_gap_min>=1980&&row.output_gap_max<=2020&&row.decode_mean<2000);
    assert.match(row.pwm_sha256,/^[a-f0-9]{64}$/);
  }
});

test('C, ASM and forced-generic arithmetic receipts bind the same independent AVR cases to current source',()=>{
  const receipt=JSON.parse(read(folder+'universal-math-measurements.json'));
  const {build,verification:v}=receipt;
  assert.equal(build.saturated_products,true);assert.equal(build.mul16_unroll,2);
  assert.equal(v.cases,600435);
  assert.equal(v.coverage.pwm130_signed16_exhaustive,true);
  assert.equal(v.coverage.pitch_signed8_gain5_exhaustive,true);
  assert.equal(v.coverage.synthesis_signed16_exhaustive,true);
  assert.equal(v.coverage.attenuation_dynamic_exhaustive,true);
  assert.deepEqual(v.coverage.history_layouts,[10,11]);
  assert.equal(sha(JSON.stringify(build,null,2)+'\n'),v.build_sha256);
  for(const [field,path] of [
    ['math_header_sha256','src/Lpx4Math.h'],['multiply_header_sha256','src/Lpx4MultiplyAvr.h'],
    ['probe_sha256','tests/avr25_math.cpp'],['observer_sha256','tests/verify_avr25_math.mjs'],
  ])assert.equal(sha(read('Codecs/LPX/01_ACTIVE_Q0_CODEC/'+path)),v[field],path);
  assert.deepEqual(v.results.map(row=>row.backend),['c','asm','generic']);
  for(const row of v.results){assert.equal(row.cases,v.cases);assert.equal(row.passed,true);assert.ok(row.irqs>100);}
  assert.equal(build.backends.c.binary_sha256,build.backends.generic.binary_sha256);
  const legacy=receipt.retained_default_probe;
  assert.equal(legacy.build.saturated_products,false);
  assert.equal(legacy.verification.cases,168982);
  assert.equal(legacy.verification.math_header_sha256,v.math_header_sha256);
  assert.equal(legacy.verification.observer_sha256,v.observer_sha256);
  assert.equal(sha(JSON.stringify(legacy.build,null,2)+'\n'),legacy.verification.build_sha256);
  assert.ok(legacy.verification.results.every(row=>row.passed&&row.irqs>100));
});

test('shared universal state reset saves 100 bytes with identical measured playback',()=>{
  const receipt=JSON.parse(read(folder+'universal-measurements.json'));
  const change=receipt.size_optimization;
  assert.equal(change.baseline_revision,'85d354a9565a4f2cc6cfff47726b33cf076ff1ff');
  assert.equal(change.program_bytes_saved_per_case,100);
  assert.equal(change.reset_function_bytes_before,122);assert.equal(change.reset_function_bytes_after,22);
  assert.equal(change.baseline_cases.length,receipt.cases.length);
  assert.ok(change.identical_fields.includes('decode_active_irq_mean'));
  assert.ok(change.identical_fields.includes('decode_max'));
  assert.ok(change.identical_fields.includes('pwm_sha256'));
  for(const row of change.measured_after_cases){
    const current=receipt.cases.find(item=>item.case===row.case);
    assert.equal(row.program_excluding_audio_bytes-current.program_excluding_audio_bytes,change.followup_program_bytes_saved_per_case);
    const before=change.baseline_cases.find(item=>item.case===row.case);
    assert.equal(before.program_excluding_audio_bytes-row.program_excluding_audio_bytes,100);
    for(const field of change.identical_fields)assert.equal(row[field],before[field],row.case+': '+field);
  }
  assert.equal(change.portable_input_switch_checks.reduce((sum,row)=>sum+row.cases,0),10400);
  assert.ok(change.portable_input_switch_checks.every(row=>row.exact));
});
