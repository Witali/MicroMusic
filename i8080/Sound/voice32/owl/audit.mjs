import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { traceRom } from '../../dual-crc-voice/audit.mjs';
import { cReference } from '../reference.mjs';

const read = name => readFileSync(new URL(name, import.meta.url));
export async function auditOwl() {
  const rom = read('owl-voice32.bin'), meta = JSON.parse(read('owl-voice32.json'));
  const pcm = JSON.parse(read('pcm4.json')), packed = Buffer.from(pcm.packed_hex, 'hex');
  const { api } = await cReference({ suffix: '-owl' });
  const { result, voice, pulses } = traceRom(rom, meta);
  assert.equal(result.halted, true); assert.equal(result.writes, 0);
  assert.equal(voice.length, pcm.sample_count*2); assert.equal(pulses.length, voice.length);
  assert.deepEqual(result.voice.periods_t, { 109: voice.length-1 });
  assert.deepEqual(result.tones, []); assert.equal(result.ramp.pulses, 0);
  assert.equal(voice[0].rise, 95, 'RESET goes directly to PCM playback');
  const widths = [];
  for (let i = 0; i < pcm.sample_count; i++) {
    const expected = api.width(api.nibble(packed[i>>1], i&1)); widths.push(expected);
    assert.equal(voice[i*2].width, expected); assert.equal(voice[i*2+1].width, expected);
  }
  return { name: meta.name, sha256: createHash('sha256').update(rom).digest('hex'),
    startup: 'direct', startup_diagnostics: false, startup_beeps: 0, startup_ramp_pulses: 0,
    first_pwm_rise_t: voice[0].rise, first_pwm_rise_us: voice[0].rise/3.5,
    sample_count: pcm.sample_count, pulses: voice.length, periods_t: result.voice.periods_t,
    exact_c_reference_widths: true, sample_widths_sha256: createHash('sha256').update(Uint8Array.from(widths)).digest('hex'),
    instructions: result.instructions, t_states: result.t_states, halted: true, writes: 0,
    hardware_tested: false, active_interrupts_supported: false };
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await auditOwl();
  writeFileSync(new URL('AUDIT.json', import.meta.url), JSON.stringify(result, null, 2)+'\n');
  console.log(JSON.stringify(result));
}
