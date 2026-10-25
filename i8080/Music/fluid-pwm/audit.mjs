import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CPU8080 } from '../../Emulator/core8080.mjs';
import { cReference } from './reference.mjs';
const histogram = values => Object.fromEntries([...values].sort(([a], [b]) => a-b));

export async function auditAll(hz = 3500000) {
  assert.ok([2000000,2500000,3500000].includes(hz));
  const root = new URL(hz === 3500000 ? './' : `./clocks/${hz}/`, import.meta.url);
  const read = name => readFileSync(new URL(name, root));
  const bank = JSON.parse(read('bank.json')), { api, compiler, options } = await cReference();
  for (const [id, item] of bank.banks.entries()) for (const [stage, wave] of item.waves.entries())
    for (const [i, q] of wave.entries()) api.set_wave(id, stage, i, q);
  const reports = [];
  for (const name of ['uniform26-fluid-pwm108', 'balanced27-fluid-pwm108']) {
    const meta = JSON.parse(read(name+'.json')), rom = read(name+'.bin');
    const entries = new Map(Object.entries(meta.labels).filter(([label]) => /^P\d_L\d+$/.test(label))
      .map(([label, pc]) => [parseInt(pc, 16), label.match(/^P(\d)_L(\d+)$/).slice(1).map(Number)]));
    const period = meta.period_t, levels = new Map(), periods = new Map(), widths = new Map();
    let cpu, slot = null, slots = 0, frames = 0, chunkIndex = 0, chunkFrame = 0, expected = 8, last = false, firstT = null;
    const output = [];
    function finishSlot(end) {
      if (!slot) return;
      assert.equal(end-slot.t, period);
      periods.set(end-slot.t, (periods.get(end-slot.t)||0)+1);
      assert.deepEqual(slot.edges, slot.level ? [[slot.t+4, 1], [slot.t+4+4*slot.level, 0]] : []);
      if (slot.level) widths.set(slot.level*4, (widths.get(slot.level*4)||0)+1);
    }
    const bus = { level: 0, advance() {}, edge(value, t) {
      if (value !== this.level) { this.level = value; assert.ok(slot); slot.edges.push([t, value]); }
    } };
    cpu = new CPU8080(new Uint8Array(rom), { audio: bus }); api.set_mix(meta.mix_minimum_sum, meta.mix_maximum_sum); api.reset();
    while (!cpu.halted && cpu.count < 100000000) {
      const entry = entries.get(cpu.pc);
      if (entry) {
        finishSlot(cpu.t);
        if (firstT === null) firstT = cpu.t;
        assert.equal(cpu.t-firstT, slots*period, 'No cumulative slot phase drift');
        const phase = slots%4;
        if (phase === 0) {
          if (frames) {
            chunkFrame++;
            if (chunkFrame === meta.chunks[chunkIndex].frames) { chunkIndex++; chunkFrame = 0; }
          }
          assert.equal(cpu.pair(0), api.phase_bc()); assert.equal(cpu.pair(1), api.phase_de());
          const current = meta.chunks[chunkIndex]; last = chunkFrame === current.frames-1;
          const final = last && chunkIndex === meta.chunks.length-1;
          const lookup = last && !final ? meta.chunks[chunkIndex+1] : current;
          expected = api.frame(current.steps[0] ?? 0xff00, current.steps[1] ?? 0xff00,
            lookup.piano_register, lookup.piano_stage, lookup.guitar_stage, +final);
          output.push(expected); frames++;
        }
        if (phase === 2) { assert.equal(cpu.pair(0), api.phase_bc()); assert.equal(cpu.pair(1), api.phase_de()); }
        assert.deepEqual(entry, [phase === 3 && last ? 4 : phase, expected], `slot ${slots}`);
        slot = { t: cpu.t, level: entry[1], edges: [] };
        levels.set(slot.level, (levels.get(slot.level)||0)+1); slots++;
      }
      cpu.step();
    }
    finishSlot(cpu.t);
    assert.ok(cpu.halted); assert.equal(cpu.memWrites, 0); assert.equal(cpu.ioWrites, 0); assert.equal(cpu.inte, 0);
    assert.equal(frames, meta.frames); assert.equal(slots, meta.frames*4);
    assert.equal(Math.min(...levels.keys()), 0); assert.equal(Math.max(...levels.keys()), 15);
    reports.push({ name, sha256: createHash('sha256').update(rom).digest('hex'),
      t_states: cpu.t, instructions: cpu.count, first_slot_t: firstT, frames, pwm_slots: slots,
      slot_durations_t: histogram(periods), high_widths_t: histogram(widths), levels: histogram(levels),
      sample_levels_sha256: createHash('sha256').update(Uint8Array.from(output)).digest('hex'),
      exact_c_reference: true, minimum_level: 0, maximum_level: 15, writes: 0, io_writes: 0,
      halted: true, final_inte: cpu.inte, used_bytes: meta.used_bytes, soundfont_sha256: meta.soundfont_sha256 });
  }
  return { cpu_hz: hz, period_t: 108, carrier_hz: hz/108, samples_per_wave: 256,
    reference: { compiler: compiler.split(/[\\/]/).at(-1), options, target: 'WASM portable C99 arithmetic, not an 8080 C cross-compile' },
    reports, hardware_tested: false, active_interrupts_supported: false };
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const at = process.argv.indexOf('--cpu-hz'), hz = at < 0 ? 3500000 : Number(process.argv[at+1]);
  const report = await auditAll(hz);
  writeFileSync(new URL((hz === 3500000 ? './' : `./clocks/${hz}/`) + 'AUDIT.json', import.meta.url), JSON.stringify(report, null, 2)+'\n');
  console.log(JSON.stringify(report.reports.map(r => ({ name: r.name, slots: r.pwm_slots, periods: r.slot_durations_t, exact_c: r.exact_c_reference }))));
}
