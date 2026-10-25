import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { traceRom } from '../dual-crc-voice/audit.mjs';
import { cReference } from './reference.mjs';

const read = name => readFileSync(new URL(name, import.meta.url));
export async function auditAll() {
  const meta = JSON.parse(read('dualcrc-voice32.json')), pcm = JSON.parse(read('pcm4.json'));
  const packed = Buffer.from(pcm.packed_hex, 'hex');
  const { api, compiler, options } = await cReference();
  const expected = Array.from({ length: pcm.sample_count }, (_, i) => api.width(api.nibble(packed[i >> 1], i & 1)));
  const originalMeta = JSON.parse(read('../dual-crc-voice/original-manifest.json'));
  const baseline = traceRom(read('../../Emulator/tests/roms/diagnostic_dualcrc.bin'), originalMeta).result;
  const { result, voice } = traceRom(read('dualcrc-voice32.bin'), meta);
  assert.equal(result.halted, true);
  assert.equal(result.writes, 0);
  assert.equal(voice.length, pcm.sample_count*2);
  assert.deepEqual(result.voice.periods_t, { 109: voice.length-1 });
  for (const [i, pulse] of voice.entries()) assert.equal(pulse.width, expected[i >> 1], `pulse ${i}`);
  assert.deepEqual(result.tones, baseline.tones, 'All inherited diagnostic beeps');
  assert.deepEqual(result.ramp, baseline.ramp, 'Original soft start');
  // traceRom also serves the old five-phase DPCM engine. Its old sample/phase
  // terminology does not describe this four-nibble, two-pulse PCM engine.
  delete result.voice.phases;
  delete result.voice.exact_original_widths;
  delete result.voice.samples;
  result.voice.pcm_samples = pcm.sample_count;
  result.voice.pulses = voice.length;
  result.voice.exact_c_reference_widths = true;
  const faults = [];
  for (let bank = 0; bank < 8; bank++) {
    const rom = new Uint8Array(read('dualcrc-voice32.bin')), at = bank*4096+0x900;
    rom[at] ^= 1;
    const failed = traceRom(rom, meta).result;
    assert.equal(failed.halted, true); assert.equal(failed.pc, 0xf86);
    assert.equal(failed.voice.samples, 0);
    faults.push({ bank, address: at, detected_before_voice: true });
  }
  return { cpu_hz: meta.cpu_hz, period_t: 109, carrier_hz: meta.carrier_hz,
    sample_rate_hz: meta.sample_rate_hz, samples: pcm.sample_count, pulses: voice.length,
    exact_c_reference_widths: true, width_sha256: createHash('sha256').update(Uint8Array.from(expected)).digest('hex'),
    reference: { compiler: compiler.split(/[\\/]/).at(-1), options, target: 'WASM; portable C99 arithmetic, not an 8080 cross-compile' },
    result, corruption_tests: faults, hardware_tested: false, active_interrupts_supported: false };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const report = await auditAll();
  writeFileSync(new URL('AUDIT.json', import.meta.url), JSON.stringify(report, null, 2)+'\n');
  console.log(JSON.stringify({ samples: report.samples, pulses: report.pulses,
    periods: report.result.voice.periods_t, exact_c_reference_widths: report.exact_c_reference_widths,
    halted: report.result.halted, writes: report.result.writes }));
}
