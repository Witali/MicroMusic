import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { CPU8080 } from '../../Emulator/core8080.mjs';
import { cReference } from './reference.mjs';

const root = new URL('./', import.meta.url);
const read = name => readFileSync(new URL(name, root));
const json = name => JSON.parse(read(name));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const tick = (hist, value) => { hist[value] = (hist[value] || 0) + 1; };
const marker = value => value === null ? 0xff00 : value;

export function traceOriginal(source, reference) {
  const rom = read(source.source);
  assert.equal(hash(rom), source.original_sha256);
  const cpu = new CPU8080(rom), periods = [{}, {}, {}, {}], levels = [];
  let last = null, frame = 0, note = 0, used = 0;
  reference.reset();
  while (!cpu.halted && cpu.count < 60000000) {
    const pc = cpu.pc;
    if (pc >= 0x2c00 && pc < 0x3000 && (pc & 15) === 0) {
      const stage = (pc >> 8) - 0x2c, level = (pc & 255) >> 4;
      if (last) tick(periods[last.stage], cpu.t-last.t);
      last = { stage, t: cpu.t };
      if (stage === 0) {
        const row = source.notes[note];
        const expected = reference.frame(...row.steps.map(marker));
        assert.equal(level, expected, `${source.name} original frame ${frame}`);
        levels.push(level); frame++; used++;
        if (used === row.groups) { used = 0; note++; }
      } else assert.equal(level, levels.at(-1));
    }
    cpu.step();
  }
  assert.equal(cpu.halted, true); assert.equal(cpu.memWrites, 0);
  assert.equal(frame, source.notes.reduce((n, row) => n+row.groups, 0));
  assert.equal(note, source.notes.length);
  return { sha256: hash(rom), frames: frame, periods_t_by_phase: periods,
    duration_t: cpu.t, level_sha256: hash(Uint8Array.from(levels)), writes: cpu.memWrites };
}

export function traceOptimized(name, reference) {
  const rom = read(name+'.bin'), meta = json(name+'.json');
  assert.equal(rom.length, 32768); assert.equal(hash(rom), meta.sha256);
  let pc = 0, last = null, stage = 0, currentLevel = 0, frame = 0, chunk = 0, used = 0;
  let start = null, pulseStart = null, slotRises = 0, width = 0;
  const periods = {}, widths = {}, levels = [], counters = new Set();
  const bus = { level: 0, advance() {}, edge(value, t) {
    if (value === this.level) return;
    this.level = value;
    if (value) { pulseStart = t; slotRises++; assert.equal(t, last+4); }
    else { width = t-pulseStart; assert.equal(width, currentLevel*4); tick(widths, width); }
  } };
  const cpu = new CPU8080(rom, { audio: bus });
  reference.reset();
  function finishSlot() {
    assert.equal(bus.level, 0, `${name}: high output at end of slot`);
    assert.equal(slotRises, currentLevel ? 1 : 0);
    if (!currentLevel) tick(widths, 0);
  }
  while (!cpu.halted && cpu.count < 60000000) {
    pc = cpu.pc;
    if (pc >= 0x1000 && pc < 0x1500 && (pc & 15) === 0) {
      if (last !== null) { finishSlot(); assert.equal(cpu.t-last, meta.period_t); tick(periods, cpu.t-last); }
      stage = (pc >> 8)-0x10;
      currentLevel = (pc & 255) >> 4;
      slotRises = 0; width = 0;
      last = cpu.t; start ??= cpu.t;
      if (stage === 0) {
        const row = meta.chunks[chunk];
        const expected = reference.frame(...row.steps.map(marker));
        assert.equal(currentLevel, expected, `${name} frame ${frame}`);
        levels.push(currentLevel); frame++; used++;
        counters.add(cpu.r[7]);
        if (used === row.frames) { used = 0; chunk++; }
      } else assert.equal(currentLevel, levels.at(-1));
    }
    cpu.step();
  }
  finishSlot();
  assert.equal(cpu.t-last, meta.period_t, `${name}: last full slot`);
  assert.equal(stage, 4); assert.equal(cpu.halted, true);
  assert.equal(cpu.memWrites, 0); assert.equal(cpu.ioWrites, 0); assert.equal(cpu.inte, 0);
  assert.equal(frame, meta.frames); assert.equal(chunk, meta.chunks.length);
  assert.equal(cpu.sp, meta.score_at+meta.score_bytes);
  assert.equal(cpu.pair(0), reference.phase_bc()); assert.equal(cpu.pair(1), reference.phase_de());
  assert.deepEqual(Object.keys(periods), [String(meta.period_t)]);
  return { sha256: hash(rom), frames: frame, slots: frame*4, periods_t: periods, widths_t: widths,
    duration_t: cpu.t-start, instructions: cpu.count, level_sha256: hash(Uint8Array.from(levels)),
    pc: cpu.pc, sp: cpu.sp, writes: cpu.memWrites, halted: cpu.halted,
    note_boundary_error_max_t: Math.max(...meta.notes.map(note => Math.abs(note.duration_error_t))),
    pitch_error_max_cents: Math.max(...meta.notes.flatMap(note => note.pitch_error_cents).filter(value => value !== null).map(Math.abs)) };
}

export async function auditAll() {
  const { api, options } = await cReference();
  const sources = json('source-score.json').tunes, reports = [];
  assert.equal(api.asm_enabled(), 0, 'C is the default backend');
  for (const source of sources) {
    const original = traceOriginal(source, api);
    const optimized = traceOptimized(source.name+'-pwm108', api);
    reports.push({ name: source.name, original, optimized });
  }
  return { cpu: 'Intel 8080, documented instruction timings', cpu_hz: 3500000, period_t: 108,
    carrier_hz: 3500000/108, reference: { language: 'C99', target: 'wasm32-unknown-unknown', options },
    interrupt_input: 'inactive; INTE is audio', wait_states: 0, hardware_tested: false,
    active_interrupts_supported: false, buffer: 'no producer/consumer buffer; direct cycle-timed output', reports };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await auditAll();
  writeFileSync(new URL('AUDIT.json', root), JSON.stringify(result, null, 2)+'\n');
  for (const report of result.reports) console.log(report.name, JSON.stringify(report.optimized));
}
