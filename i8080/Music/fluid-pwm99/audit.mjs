import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CPU8080 } from '../../Emulator/core8080.mjs';
import { cReference } from '../fluid-pwm/reference.mjs';
const histogram = values => Object.fromEntries([...values].sort(([a], [b]) => a-b));
// Independent documented8080 instruction costs, Intel1975 Rev.B AppendixB.
const costs = new Map([[0,4],[1,10],[0x11,10],[0x31,10],[0xe1,10],[0x7d,5],[0x21,10],[0xe9,5],
  [0xf3,4],[0xfb,4],[0xc3,10],[0x24,5],[0xca,10],[0x25,5],[9,10],[0x44,5],[0x4d,5],
  [0x19,10],[0x54,5],[0x5d,5],[0x3d,5],[0x39,10],[0xf9,5],[0xb7,4],[0x68,5],[0x66,7],
  [0x6a,5],[0x6e,7],[0x26,7],[0x76,7],[0xf6,7],[0x7f,5]]);
export function stepClock(cpu) {
  const cost=costs.get(cpu.read(cpu.pc));assert.notEqual(cost,undefined,'Only measured documented opcodes');
  const before=cpu.t;cpu.step();assert.equal(cpu.t-before,cost);return cost;
}

export async function auditAll(hz = 3500000) {
  assert.ok([2000000,2500000,3500000].includes(hz));
  const root = new URL(hz === 3500000 ? './' : `./clocks/${hz}/`, import.meta.url);
  const read = name => readFileSync(new URL(name, root));
  const bank = JSON.parse(readFileSync(new URL(`../fluid-pwm/${hz===3500000?'':`clocks/${hz}/`}bank.json`,import.meta.url))), { api, compiler, options } = await cReference({suffix:'-pwm99'});
  for (const [id, item] of bank.banks.entries()) for (const [stage, wave] of item.waves.entries())
    for (const [i, q] of wave.entries()) api.set_wave(id, stage, i, q);
  const reports = [];
  for (const name of ['uniform26-fluid-pwm99', 'balanced27-fluid-pwm99']) {
    const meta = JSON.parse(read(name+'.json')), rom = read(name+'.bin');
    const entries = new Map(Object.entries(meta.labels).filter(([label]) => /^P\d_L\d+$/.test(label))
      .map(([label, pc]) => [parseInt(pc, 16), label.match(/^P(\d)_L(\d+)$/).slice(1).map(Number)]));
    const period = meta.period_t, levels = new Map(), periods = new Map(), widths = new Map();
    let cpu, slot = null, slots = 0, frames = 0, chunkIndex = 0, chunkFrame = 0, expected = 8, last = false, final = false, firstT = null, independentT=0;
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
          final = last && chunkIndex === meta.chunks.length-1;
          const lookup = last && !final ? meta.chunks[chunkIndex+1] : current;
          expected = api.frame(current.steps[0] ?? 0xff00, current.steps[1] ?? 0xff00,
            lookup.piano_register, lookup.piano_stage, lookup.guitar_stage, +final);
          output.push(expected); frames++;
        }
        if (phase === 2) {
          assert.equal(cpu.pair(0), api.phase_bc()); assert.equal(cpu.pair(1), api.phase_de());
          assert.equal(cpu.f.z,Number(last),'The decrement Z survives phase1 and dispatch to phase2');
        }
        assert.equal(cpu.t,independentT,'Independent instruction clock');
        assert.deepEqual(entry, [phase === 3 && last ? (final?5:4) : phase, expected], `slot ${slots}`);
        slot = { t: cpu.t, level: entry[1], edges: [] };
        levels.set(slot.level, (levels.get(slot.level)||0)+1); slots++;
      }
      independentT+=stepClock(cpu);
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
      halted: true, final_inte: cpu.inte, used_bytes: meta.used_bytes, soundfont_sha256: meta.soundfont_sha256,
      maximum_grid_error_t:0,maximum_width_error_t:0,independent_instruction_clock:true,z_live_across_phase1_checked:true });
  }
  return { cpu_hz: hz, period_t: 99, carrier_hz: hz/99, sample_rate_hz:hz/396, samples_per_wave: 256,
    reference: { compiler: compiler.split(/[\\/]/).at(-1), options, target: 'WASM portable C99 arithmetic, not an 8080 C cross-compile' },
    reports, hardware_tested: false, active_interrupts_supported: false };
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const at = process.argv.indexOf('--cpu-hz'), hz = at < 0 ? 3500000 : Number(process.argv[at+1]);
  const report = await auditAll(hz);
  writeFileSync(new URL((hz === 3500000 ? './' : `./clocks/${hz}/`) + 'AUDIT.json', import.meta.url), JSON.stringify(report, null, 2)+'\n');
  console.log(JSON.stringify(report.reports.map(r => ({ name: r.name, slots: r.pwm_slots, periods: r.slot_durations_t, exact_c: r.exact_c_reference }))));
}
