import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseHex} from '../lib/hex.js';
import {assertLpxRecordedSource} from './helpers/lpx-source-transition.mjs';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const json=path=>JSON.parse(read(path));
const sha=data=>createHash('sha256').update(data).digest('hex');
const textSha=path=>sha(read(path).toString('utf8').replaceAll('\r\n','\n'));
const folder='Codecs/LPX/research/lsf-compact-2026-11-10/';
const transition=json(folder+'source-transition.json');

test('LSF compaction binds new evidence and preserves the historical receipts',()=>{
  assert.equal(transition.complete,true);
  assert.equal(transition.baseline_revision,'0320c1014618188a3121fdfef0be55b30690d977');
  for(const [path,digest] of Object.entries(transition.receipts_sha256))
    assert.equal(textSha(path),digest,path);
  for(const [path,digest] of Object.entries(transition.preserved_receipts_sha256))
    assert.equal(textSha(path),digest,path+' historical receipt');
  for(const [path,digest] of Object.entries(transition.validation_source_sha256))
    assertLpxRecordedSource(path,digest);
  for(const [path,row] of Object.entries(transition.sources))
    assertLpxRecordedSource(path,row.current.text_lf_sha256);
});

test('all 22 universal and nine catalog Tiny profiles shrink without slowing full IRQ playback',()=>{
  const r=json(folder+'tiny.json');
  assert.equal(r.cases.length,31);
  assert.equal(r.cases.filter(row=>row.scope==='universal').length,22);
  assert.equal(r.cases.filter(row=>row.scope==='website').length,9);
  for(const row of r.cases){
    assert.equal(row.admitted,true,row.case);
    for(const [check,value] of Object.entries(row.checks)){
      // Universal unity-gain playback has an independent old C oracle;
      // catalog-gain published WAV comparisons belong to website builds.
      if(check==='public_wav_exact' && row.scope==='universal')continue;
      assert.equal(value,true,row.case+' '+check);
    }
    assert.equal(row.final.underruns,0,row.case);
    assert.ok(row.final.stack_margin>0,row.case);
    assert.ok(row.final.stack_bytes<=row.baseline.stack_bytes,row.case);
    assert.ok(row.final.cycles_with_irq<=row.baseline.cycles_with_irq,row.case);
    assert.equal(row.final.program_bytes-row.baseline.program_bytes,row.program_delta,row.case);
    assert.ok(row.program_delta<0,row.case);
    if(row.scope==='universal')assert.equal(row.program_delta,-48,row.case);
  }
});

test('the eight Mega C and ASM controls at e0939e89 retain exact real-time output with smaller programs',()=>{
  const r=json(folder+'mega.json');
  assert.equal(r.mega_cases.length,8);
  for(const [path,digest] of Object.entries(r.production_source_sha256))
    assertLpxRecordedSource(path,digest);
  for(const row of r.mega_cases){
    assert.equal(row.accepted_real_time,true);
    assert.equal(row.full_baseline_pwm_exact,true);
    assert.equal(row.underruns,0);
    assert.equal(row.before_program-row.after_program,6);
    assert.ok(row.after_cycles<=row.before_cycles);
    assert.ok(row.after_stack<=row.before_stack);
    assert.equal(row.irq_max,64);
  }
});

test('LSF compaction preserved the whole native corpus, floating mode, and shipped Nano images',()=>{
  const host=json(folder+'native-corpus.json');
  assert.equal(host.records_verified,181);assert.equal(host.segments_verified,306);
  assert.equal(host.verified_samples,15188029);assert.equal(host.complete,true);
  assert.equal(host.fixed_native_pcm16_exact,true);assert.equal(host.fixed_native_pwm_exact,true);
  assert.equal(host.native_failures,0);
  assert.equal(host.float_preprocessed_exact,true);assert.equal(host.float_complete_library_byte_exact,true);
  const nano=json(folder+'nano.json');
  assert.equal(nano.nano_images,8);assert.equal(nano.dialogue_images,1);
  assert.equal(nano.no_new_irq_measurement,true);assert.equal(nano.images.length,9);
  for(const [path,digest] of Object.entries(nano.current_source_sha256))
    assertLpxRecordedSource(path,digest);
  for(const row of nano.images){
    assert.equal(row.binary_exact,true);assert.equal(row.no_float_runtime_symbols,true);
    const bytes=read(row.source);
    assert.equal(sha(bytes),row.shipped_hex_sha256);
    assert.equal(sha(parseHex(bytes.toString(),30720)),row.current_binary_sha256);
    assert.equal(row.flash_bytes,row.shipped_flash_bytes);
  }
});

test('Tiny88 spectral anchor selection retains exact playback with IRQ and saves 10 program bytes',()=>{
  const directory='Codecs/LPX/research/tiny-spectrum-anchors-2026-11-13/';
  const receipt=json(directory+'source-transition.json');
  const report=json(directory+'measurements.json');
  assert.equal(textSha(directory+'measurements.json'),receipt.measurements_sha256);
  assert.equal(report.baseline_revision,receipt.baseline_revision);
  for(const [path,digest] of Object.entries(report.source_sha256))
    assertLpxRecordedSource(path,digest);
  assert.equal(report.cases.length,31);
  assert.equal(report.cases.filter(row=>row.scope==='universal').length,22);
  assert.equal(report.cases.filter(row=>row.scope==='website').length,9);
  for(const {case:name,scope,baseline,final,checks} of report.cases){
    for(const [check,value] of Object.entries(checks))assert.equal(value,true,name+' '+check);
    assert.equal(final.pwm_sha256,baseline.pwm_sha256,name);
    assert.equal(final.underruns,0,name);
    assert.equal(final.irq_max,baseline.irq_max,name);
    assert.equal(final.irq_max,scope==='universal'?38:44,name);
    assert.ok(final.cycles_with_irq<=baseline.cycles_with_irq,name);
    assert.ok(final.stack_bytes<=baseline.stack_bytes,name);
    assert.equal(final.program_excluding_audio_bytes-baseline.program_excluding_audio_bytes,
      scope==='universal'?-10:0,name);
    if(scope==='website')assert.equal(final.binary_sha256,baseline.binary_sha256,name);
  }
});
