import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../',import.meta.url);
const directory='Codecs/LPX/research/avr-fixed-rate-2026-11-18/';
const read=path=>readFileSync(new URL(path,root));
const json=path=>JSON.parse(read(path));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');

test('one compiled LPX rate keeps all 132 matched IRQ outputs and the host reference',()=>{
  const report=json(directory+'measurements.json');
  assert.equal(report.default_firmware_rate,8000);
  assert.equal(report.firmware_rate_selection,'compile-time');
  assert.equal(report.frontend_tests.tests,8);assert.equal(report.frontend_tests.passed,true);
  assert.equal(report.cases.length,132);
  for(const target of ['attiny88','atmega328p'])for(const rate of [8000,12000,16000]){
    const rows=report.cases.filter(r=>r.target===target&&r.rate===rate);
    assert.equal(rows.length,22);assert.equal(new Set(rows.map(r=>r.case)).size,22);
    assert.equal(rows.filter(r=>r.accepted).length,target==='atmega328p'||rate===8000?22:rate===12000?9:2);
    for(const row of rows){
      assert.equal(row.sample_hz,rate);assert.equal(row.sample_clock_policy,'compile-time-nearest-fixed-divider');
      assert.equal(row.pwm_sha256,row.before.pwm_sha256);
      assert.equal(row.underruns,row.before.underruns);
      assert.equal(row.program_excluding_audio_bytes,row.before.program_excluding_audio_bytes-(target==='attiny88'?36:40));
    }
  }
  const wide=json(directory+'wideband.json');assert.equal(wide.cases.length,8);
  assert.ok(wide.cases.every(r=>r.model_exact&&r.accepted&&r.underruns===0));
});

test('all 18 WebUI LPX images use smaller fixed8k builds and exact unchanged audio',()=>{
  const report=json(directory+'web-rebuild.json');assert.equal(report.cases.length,18);
  assert.equal(report.all_audio_stream_assets_unchanged,true);
  for(const [path,digest] of Object.entries(report.protected_asset_sha256))assert.equal(sha(read(path)),digest);
  assert.equal(report.independent_rebuild.all_binaries_exact,true);
  assert.equal(report.independent_rebuild.all_no_float_runtime_symbols,true);
  assert.equal(report.independent_rebuild.all_declared_sizes_exact,true);
  assert.equal(report.cases.reduce((n,r)=>n+r.after.samples,0),345470);
  for(const row of report.cases){
    assert.equal(row.sample_rate,8000);assert.deepEqual(row.supported_sample_rates,[8000]);
    assert.equal(row.exact_old_recorded_c_public_pwm,true);
    assert.equal(row.after.accepted,true);assert.equal(row.after.underruns,0);
    assert.equal(row.after.stream,row.before.stream);
    assert.equal(row.after.ram,row.before.ram);assert.equal(row.after.stack,row.before.stack);
    assert.equal(row.after.program,row.before.program-(row.family==='tiny'?36:row.family==='nano'?40:44));
    assert.equal(sha(read(row.source)),row.hex_sha256);
  }
  for(const path of ['web-player/firmware-atmega328p.json','web-player/firmware-lpx-attiny88.json',
      'web-player/audio/lpx-dialogue/manifest.json']){
    const catalog=json(path);assert.equal(catalog.sampleRateSelection,'compile-time');
    assert.deepEqual(catalog.supportedSampleRates,[8000]);
  }
  for(const path of ['web-player/app.js','web-player/index.html','web-player/lib/tiny88-preview.js'])
    assert.match(read(path).toString(),/20261118-lpx-fixed-rate/);
});
