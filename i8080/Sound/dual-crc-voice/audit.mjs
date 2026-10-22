import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { CPU8080 } from '../../Emulator/core8080.mjs';

const root = new URL('./', import.meta.url);
const originalMeta = JSON.parse(readFileSync(new URL('original-manifest.json', root)));
const baseline = readFileSync(new URL('../../Emulator/tests/roms/diagnostic_dualcrc.bin', root));
const histogram = values => Object.fromEntries([...values.reduce((map, n) => map.set(n, (map.get(n) || 0) + 1), new Map())].sort((a, b) => a[0] - b[0]));
const expected = [], deltas = [];
let predictor = 8;
for (const segment of originalMeta.voice_segment_links) {
  for (let at = parseInt(segment.from, 16); at < parseInt(segment.from, 16) + segment.bytes; at += 2) {
    const c = baseline[at], b = baseline[at + 1];
    for (const symbol of [c & 7, (c >> 3) & 7, ((c >> 6) & 3) | ((b & 1) << 2), (b >> 1) & 7, (b >> 4) & 7]) {
      deltas.push(symbol - 4); predictor += symbol - 4;
      assert.ok(predictor >= 0 && predictor < 16);
      expected.push(4 + 4 * predictor);
    }
  }
}
assert.equal(expected.length, 63085);

export function traceRom(rom, meta, { maxInstructions = 5000000 } = {}) {
  const rampStart = parseInt(meta.ramp_start, 16), voiceStart = parseInt(meta.voice_code_start, 16);
  const stages = meta.ramp_stage_pc.map(pc => parseInt(pc, 16));
  const pulses = [], toneStarts = [], stageStarts = [];
  let cpu, section = 'diagnostics', pc = 0, stage = -1, rampT = null, voiceT = null, xchg = 0;
  const bus = { level: 0, advance() {}, edge(level, t) {
    if (level === this.level) return;
    this.level = level;
    if (level) pulses.push({ rise: t, pc, section, stage });
    else {
      assert.ok(pulses.length && pulses.at(-1).width === undefined);
      pulses.at(-1).width = t - pulses.at(-1).rise;
    }
  } };
  cpu = new CPU8080(new Uint8Array(rom), { audio: bus, mode: 'inte' });
  while (!cpu.halted && cpu.count < maxInstructions) {
    pc = cpu.pc;
    if (pc === rampStart && rampT === null) { section = 'ramp'; rampT = cpu.t; }
    if (pc === voiceStart && voiceT === null) { section = 'voice'; voiceT = cpu.t; }
    const index = stages.indexOf(pc);
    if (section === 'ramp' && index >= 0) { stage = index; stageStarts.push({ stage, t: cpu.t }); }
    if (pc === 0xf8b && (toneStarts.length === 0 || pulses.length - toneStarts.at(-1).pulse >= toneStarts.at(-1).count)) {
      toneStarts.push({ t: cpu.t, pulse: pulses.length, count: cpu.r[0] });
    }
    if (cpu.read(pc) === 0xeb) xchg++;
    cpu.step();
  }
  const voice = pulses.filter(p => p.section === 'voice'), ramp = pulses.filter(p => p.section === 'ramp');
  const periods = voice.slice(1).map((p, i) => p.rise - voice[i].rise);
  const result = { sha256: createHash('sha256').update(rom).digest('hex'), instructions: cpu.count, t_states: cpu.t,
    pc: cpu.pc, sp: cpu.sp, halted: cpu.halted, writes: cpu.memWrites, xchg,
    ramp_start_t: rampT, voice_start_t: voiceT,
    ramp: { duration_t: voiceT === null ? null : voiceT - rampT, pulses: ramp.length,
      periods_t: histogram(ramp.slice(1).map((p, i) => p.rise - ramp[i].rise)),
      stage_durations_t: stageStarts.map((s, i) => (stageStarts[i + 1]?.t ?? voiceT) - s.t) },
    voice: { samples: voice.length, duration_t: voiceT === null ? null : cpu.t - voiceT,
      widths_t: histogram(voice.map(p => p.width)), periods_t: histogram(periods),
      phases: Array.from({ length: 5 }, (_, phase) => histogram(periods.filter((_, i) => i % 5 === phase))),
      exact_original_widths: voice.length === expected.length && voice.every((p, i) => p.width === expected[i]),
      mean_period_t: periods.length ? periods.reduce((a, b) => a + b, 0) / periods.length : null },
    tones: toneStarts.map(t => { const list = pulses.slice(t.pulse, t.pulse + t.count); return {
      count: list.length, widths_t: histogram(list.map(p => p.width)),
      periods_t: histogram(list.slice(1).map((p, i) => p.rise - list[i].rise)) }; }) };
  return { result, voice, pulses };
}

export function auditAll({ verbose = false } = {}) {
  const reports = [];
  for (const name of ['original', 'dualcrc-uniform159', 'dualcrc-uniform152']) {
    const meta = name === 'original' ? originalMeta : JSON.parse(readFileSync(new URL(`${name}.json`, root)));
    const rom = name === 'original' ? baseline : readFileSync(new URL(`${name}.bin`, root));
    const { result } = traceRom(rom, meta);
    assert.equal(result.halted, true, name);
    assert.equal(result.writes, 0, name);
    assert.equal(result.voice.exact_original_widths, true, name);
    assert.equal(result.tones.length, 12, name);
    assert.deepEqual(result.tones.map(t => t.count), [90, ...Array(8).fill(8), 90, 90, 90]);
    if (name !== 'original') {
      assert.deepEqual(result.voice.periods_t, { [meta.period_t]: 63084 }, name);
      assert.deepEqual(result.ramp, reports[0].ramp, 'Original soft start preserved');
    }
    reports.push({ name, ...result });
    if (verbose) console.log(name, JSON.stringify({ voice: result.voice, halted: result.halted, writes: result.writes }));
  }
  // Corruption anywhere in each physical bank must stop before speech.
  const faults = [];
  for (let bank = 0; bank < 8; bank++) {
    const rom = new Uint8Array(readFileSync(new URL('dualcrc-uniform152.bin', root)));
    const at = bank * 4096 + 0x900;
    rom[at] ^= 1;
    const meta = JSON.parse(readFileSync(new URL('dualcrc-uniform152.json', root)));
    const { result } = traceRom(rom, meta);
    assert.equal(result.voice.samples, 0);
    assert.equal(result.halted, true);
    assert.equal(result.pc, 0xf86);
    faults.push({ address: at.toString(16), detected: true, voice_samples: result.voice.samples });
  }
  return { cpu_hz: 3500000, expected_samples: expected.length,
    sample_widths_sha256: createHash('sha256').update(Uint8Array.from(expected)).digest('hex'),
    reports, corruption_tests: faults, hardware_tested: false };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const report = auditAll({ verbose: true });
  writeFileSync(new URL('AUDIT.json', root), JSON.stringify(report, null, 2) + '\n');
}
