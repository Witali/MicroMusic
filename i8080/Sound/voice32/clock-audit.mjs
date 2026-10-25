// Full low-clock ROM execution, C arithmetic reference and diagnostic faults.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { traceRom } from '../dual-crc-voice/audit.mjs';
import { cReference } from './reference.mjs';

const read = name => readFileSync(new URL(name, import.meta.url));
const { api } = await cReference({ suffix: '-clocks' });
const baseline = traceRom(read('dualcrc-voice32.bin'), JSON.parse(read('dualcrc-voice32.json'))).result;
for (const hz of [2000000,2500000]) for (const profile of ['balloon','owl']) {
  const root = `${profile === 'owl' ? 'owl/' : ''}clocks/${hz}/`;
  const name = profile === 'owl' ? 'owl-voice32' : 'dualcrc-voice32';
  const rom = read(root+name+'.bin'), meta = JSON.parse(read(root+name+'.json'));
  const pcm = JSON.parse(read(root+'pcm4.json')), source = JSON.parse(read(root+'SOURCE.json'));
  const packed = Buffer.from(pcm.packed_hex,'hex');
  assert.equal(createHash('sha256').update(rom).digest('hex'),meta.sha256);
  assert.equal(source.canonical_sha256,createHash('sha256').update(read(root+source.canonical_wav)).digest('hex'));
  assert.equal(meta.cpu_hz,hz); assert.equal(pcm.sample_rate_hz,hz/218);
  assert.ok(Math.abs(source.source_duration_error_seconds)<.0005);
  assert.ok(Math.abs(source.resampler_clock_error_ppm)<50);
  assert.equal(source.clipped_source_samples,0);
  const { result, voice, pulses } = traceRom(rom,meta);
  assert.ok(result.halted); assert.equal(result.writes,0);
  assert.equal(voice.length,pcm.sample_count*2);
  assert.deepEqual(result.voice.periods_t,{109:voice.length-1});
  for (const [i,p] of voice.entries()) {
    const q = api.nibble(packed[i>>2],(i>>1)&1);
    assert.equal(p.width,api.width(q));
    assert.equal(p.rise-voice[0].rise,i*109);
  }
  const faults=[];
  if (profile === 'balloon') {
    assert.deepEqual(result.tones.map(t=>t.count),baseline.tones.map(t=>t.count));
    const period=meta.retimed_startup.tone_period_t;
    for (const tone of result.tones) {
      assert.deepEqual(tone.periods_t,{[period]:tone.count-1});
      assert.deepEqual(tone.widths_t,{[period/2]:tone.count});
    }
    assert.ok(Math.abs(result.ramp.duration_t/hz-baseline.ramp.duration_t/3500000)<.004);
    for (let bank=0;bank<8;bank++) {
      const bad=new Uint8Array(rom); bad[bank*4096+0x900]^=1;
      const failed=traceRom(bad,meta).result;
      assert.ok(failed.halted); assert.equal(failed.pc,0xf86); assert.equal(failed.voice.samples,0);
      faults.push({bank,detected_before_voice:true});
    }
  } else {
    assert.equal(pulses.length,voice.length); assert.equal(voice[0].rise,95);
    assert.deepEqual(result.tones,[]); assert.equal(result.ramp.pulses,0);
  }
  const report={cpu_hz:hz,sha256:meta.sha256,sample_rate_hz:hz/218,carrier_hz:hz/109,
    samples:pcm.sample_count,pulses:voice.length,maximum_grid_error_t:0,maximum_width_error_t:0,
    exact_c_reference_widths:true,source_duration_error_seconds:source.source_duration_error_seconds,
    ramp_seconds:profile==='balloon'?result.ramp.duration_t/hz:0,
    tone_hz:meta.retimed_startup?.tone_hz??null,corruption_tests:faults,
    t_states:result.t_states,instructions:result.instructions,halted:true,writes:0,
    hardware_tested:false,active_interrupts_supported:false};
  const target=new URL(root+'AUDIT.json',import.meta.url);
  if (process.argv.includes('--check')) assert.deepEqual(report,JSON.parse(readFileSync(target)));
  else writeFileSync(target,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({profile,...report,corruption_tests:faults.length}));
}
