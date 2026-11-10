import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseHex} from '../lib/hex.js';
import {assertLpxRecordedSource} from './helpers/lpx-source-transition.mjs';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const textSha=path=>sha(read(path).toString('utf8').replaceAll('\r\n','\n'));
const folder='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/';
const json=path=>JSON.parse(read(path));
const transition=json(folder+'c-numeric-transition.json');

test('numeric source transition preserves receipts and source bindings from 0320c101',()=>{
  assert.equal(transition.complete,true);
  assert.equal(transition.baseline_revision,'393b2de271568890d7b483f7602a2f59452d1a68');
  for(const [path,digest] of Object.entries(transition.historical_receipts_sha256))
    assert.equal(textSha(path),digest,path+' unchanged historical receipt');
  for(const [path,digest] of Object.entries(transition.current_receipts_sha256))
    assert.equal(textSha(path),digest,path+' current evidence');
  for(const [path,row] of Object.entries(transition.sources)){
    assertLpxRecordedSource(path,row.current.text_lf_sha256);
  }
  assert.equal(transition.fixed_c_float_selector_equivalence.length,4);
  for(const row of transition.fixed_c_float_selector_equivalence){
    assert.equal(row.binary_exact,true);
    assert.equal(row.current_binary_sha256,row.frozen_candidate_binary_sha256);
  }
});

test('the 0320c101 fixed C and ASM receipt retains all four complete IRQ playbacks',()=>{
  const r=json(folder+'c-realtime-measurements.json');
  assert.equal(r.schema,'lpx-atmega328p-c-realtime-v1');
  assert.equal(r.clock_hz,16000000);assert.equal(r.sample_hz,8000);
  assert.equal(r.queue,32);assert.equal(r.prefill,24);
  assert.equal(r.physical_board_measured,false);assert.equal(r.cases.length,8);
  for(const [path,digest] of Object.entries(r.production_source_sha256))
    assertLpxRecordedSource(path,digest);
  for(const row of r.cases){
    assert.equal(row.accepted_real_time,true);assert.equal(row.underruns,0);
    assert.equal(row.pwm_exact,true);assert.equal(row.dequeued_pwm_exact,true);
    assert.equal(row.total_active_cycles_per_sample,row.decode_active_cpu_mean+row.irq_max);
    assert.equal(row.irq_max,64);assert.ok(row.total_active_cycles_per_sample<2000);
    assert.equal(row.backend_macro,Number(row.backend==='asm'));
    assert.ok(row.compiler_options.includes('-DLPX4_ENABLE_ASM='+Number(row.backend==='asm')));
    assert.ok(!row.compiler_options.some(flag=>flag.startsWith('-DLPX4_FIXED_')));
  }
  assert.equal(Math.max(...r.cases.filter(row=>row.backend==='c').map(row=>row.program_excluding_audio_bytes)),4895);
});

test('numeric mode integration rebuilt eighteen fixed ASM images equal to shipped firmware',()=>{
  const r=json(folder+'c-asm-equivalence.json');
  assert.equal(r.builds_performed,true);assert.equal(r.cases.length,18);
  assert.equal(r.new_irq_measurement,false);assert.equal(r.source_header_overrides,false);
  assert.equal(r.all_binaries_exact,true);assert.equal(r.all_no_float_runtime_symbols,true);
  for(const [path,digest] of Object.entries(r.current_source_sha256))
    assertLpxRecordedSource(path,digest);
  const catalogs=[json('web-player/firmware-lpx-attiny88.json'),json('web-player/firmware-atmega328p.json')];
  for(const row of r.cases){
    assert.equal(row.binary_exact,true);assert.equal(row.no_float_runtime_symbols,true);
    assert.equal(row.current_binary_sha256,row.shipped_binary_sha256);
    const source=row.family==='dialogue'?json('web-player/audio/lpx-dialogue/manifest.json').firmware:
      catalogs[row.family==='tiny'?0:1].variants.find(v=>v.clipId+'-'+v.id===row.id).source;
    const data=read('web-player/'+source);
    assert.equal(sha(data),row.shipped_hex_sha256);
    assert.equal(sha(parseHex(data.toString(),row.family==='tiny'?8192:30720)),row.current_binary_sha256);
  }
});

test('arithmetic and historical whole-corpus evidence retain independent exact comparisons',()=>{
  const math=json(folder+'c-realtime-math-measurements.json');
  assert.equal(math.verification.cases,600435);
  assert.equal(math.verification.math_header_sha256,sha(read('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4Math.h')));
  assert.ok(math.verification.results.every(row=>row.passed&&row.irqs>100));
  const r=json('Codecs/LPX/research/c-fixed-realtime-2026-11-10/corpus.json');
  assert.equal(r.complete,true);assert.equal(r.records_complete,181);assert.equal(r.segments_verified,306);
  assert.equal(r.verification_samples,15188029);assert.equal(r.total_underruns,0);
  assert.equal(r.all_old_native_pwm_exact,true);assert.equal(r.all_irq_r0_r1_preserved,true);
  assert.ok(r.maximum_mean_cpu_with_complete_irq<2000);
  assert.equal(r.candidate_math_sha256,textSha('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4Math.h'));
});
