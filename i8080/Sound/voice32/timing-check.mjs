import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { CPU8080 } from '../../Emulator/core8080.mjs';
const profileAt = process.argv.indexOf('--profile');
const profile = profileAt < 0 ? 'balloon' : process.argv[profileAt+1];
assert.ok(['balloon', 'owl'].includes(profile), 'Unknown voice profile');
const root = new URL(profile === 'owl' ? './owl/' : './', import.meta.url);
const read = name => readFileSync(new URL(name, root));
const name = profile === 'owl' ? 'owl-voice32' : 'dualcrc-voice32';
const rom = read(name+'.bin'), meta = JSON.parse(read(name+'.json'));
const sourcePcm = JSON.parse(read('pcm4.json'));
const pcm = Buffer.from(sourcePcm.packed_hex, 'hex');
const levels = Array.from({ length: pcm.length*2 }, (_, i) => (pcm[i>>1] >> (4*(i&1))) & 15);
const target = new URL('TIMING.json', root);
// Separate fixed instruction timing table for the emitted 8080 voice subset.
// Includes conditional JMP=10T on both paths, register MOV=5T, HLT=7T.
// Intel 8080 Programming Manual, Rev. B (1975), instruction timing table:
// https://whippleway.com/documents/Intel_8080_Programmers_Manual.pdf
// This verifies the documented instruction-level model, not electrical INTE delay.
const costs = new Map([
  [0x00,4],[0x07,4],[0x0f,4],[0x1d,5],[0x26,7],[0x31,10],
  [0x6f,5],[0x76,7],[0x78,5],[0x79,5],[0x7c,5],[0x7f,5],[0xb5,4],
  [0xc1,10],[0xc2,10],[0xc3,10],[0xca,10],[0xd1,10],[0xe1,10],
  [0xe6,7],[0xe9,5],[0xf3,4],[0xf6,7],[0xf9,5],[0xfb,4]
]);
function traceVoice(cpu, stop) {
  let t = 0, level = 0, count = 0; const pulses = [];
  do {
    const pc = cpu.pc, op = cpu.read(pc), cost = costs.get(op);
    assert.notEqual(cost, undefined, `opcode ${op.toString(16)} at ${pc.toString(16)}`);
    const before = cpu.t; cpu.step(); count++;
    assert.equal(cpu.t-before, cost); t += cost;
    const next = op === 0xfb ? 1 : op === 0xf3 ? 0 : level;
    if (next !== level) {
      if (next) pulses.push({ rise: t, pc });
      else pulses.at(-1).width = t-pulses.at(-1).rise;
      level = next;
    }
    assert.ok(count < 3000000);
  } while (!cpu.halted && !stop?.(cpu));
  return { t, count, pulses };
}
const cpu = new CPU8080(new Uint8Array(rom));
while (cpu.pc !== 0x1100 && !cpu.halted && cpu.count < 2500000) cpu.step();
assert.equal(cpu.pc, 0x1100);
const voiceStartT = cpu.t;
const full = traceVoice(cpu), pulses = full.pulses;
assert.equal(pulses.length, levels.length*2); assert.ok(cpu.halted);
let maxPhase = 0, maxWidth = 0, repeatMismatch = 0;
const widths = Array.from({length:16}, () => []), periods = new Map();
for (const [i,p] of pulses.entries()) {
  maxPhase = Math.max(maxPhase, Math.abs(p.rise-pulses[0].rise-i*109));
  maxWidth = Math.max(maxWidth, Math.abs(p.width-(4+4*levels[i>>1])));
  widths[levels[i>>1]].push(p.width);
  if (i&1 && p.width !== pulses[i-1].width) repeatMismatch++;
  if (i) { const d=p.rise-pulses[i-1].rise; periods.set(d,(periods.get(d)||0)+1); }
}
assert.equal(maxPhase,0); assert.equal(maxWidth,0); assert.equal(repeatMismatch,0);
let boundarySample = 0;
const boundaries = [];
for (const part of meta.segments.slice(0,-1)) {
  boundarySample += part.words*4;
  const i=boundarySample*2, d=pulses[i].rise-pulses[i-1].rise;
  assert.equal(d,109); boundaries.push({sample:boundarySample,period_t:d});
}
let exhaustive = 0;
for (let phase=0;phase<4;phase++) for(let current=0;current<16;current++) {
  for (const variant of phase===3 ? ['normal','wrap256','link','eof'] : ['normal']) {
    for (let next=0;next<(variant==='eof'?1:16);next++) {
      const memory = new Uint8Array(rom), word=0x39c0|next;
      memory[0x6000]=word&255; memory[0x6001]=word>>8;
      if (variant==='link') {memory.set([0x20,0x61],0x6000); memory.set([3,0,word&255,word>>8],0x6120);}
      if (variant==='eof') memory.set([0,0],0x6000);
      const c=new CPU8080(memory,{pc:parseInt(meta.labels[`P${phase}_L${current}`],16),sp:0x6000});
      c.setpair(0,phase===0 ? (0xa500|(next<<4)|7) : phase===1 ? (((0xa0|next)<<8)|0xe7) : phase===2 ? (((next<<4|5)<<8)|0xe7) : 0xa5e7);
      c.r[3]=variant==='wrap256'?0:['link','eof'].includes(variant)?1:2;
      const target=parseInt(meta.labels[`P${(phase+1)%4}_L${next}`],16);
      const r=traceVoice(c,x=>x.pc===target);
      assert.equal(r.t,218); assert.equal(r.pulses.length,2);
      assert.equal(r.pulses[1].rise-r.pulses[0].rise,109);
      for (const p of r.pulses) assert.equal(p.width,4+current*4);
      assert.equal(c.halted,variant==='eof'); assert.equal(c.memWrites,0);
      exhaustive++;
    }
  }
}
const rows=widths.map((v,q)=>({level:q,pulses:v.length,min_t:Math.min(...v),max_t:Math.max(...v),width_us:(4+4*q)/3.5,duty_percent:(4+4*q)/109*100}));
const silence = sourcePcm.silence_level ?? 8;
let tail=0; for(let i=levels.length-1;i>=0&&levels[i]===silence;i--)tail++;
const report={rom_sha256:meta.sha256,cpu_hz:3500000,output_model:'INTE at EI/DI instruction completion; no INT/WAIT/HOLD',
  timing_method:'Separate fixed 8080 opcode timing table, CPU8080 used for state/control flow',
  period_t:109,period_us:109/3.5,carrier_hz:3500000/109,pulses:pulses.length,
  intervals:Object.fromEntries(periods),maximum_grid_error_t:maxPhase,maximum_width_error_t:maxWidth,
  duplicate_pulse_mismatches:repeatMismatch,width_step_t:4,width_step_us:4/3.5,
  duty_step_percentage_points:4/109*100,code_dnl_lsb:0,code_inl_lsb:0,
  levels:rows,segment_boundary_count:boundaries.length,segment_boundaries:boundaries,
  exhaustive_level_transition_and_branch_cases:exhaustive,ending_silence_level:silence,ending_silence_samples:tail,
  ending_silence_seconds:tail*218/3500000,hardware_measured:false};
if (profile === 'owl') {
  report.startup = 'direct';
  report.first_rise_t_from_reset = voiceStartT+pulses[0].rise;
  assert.equal(report.first_rise_t_from_reset, 95);
}
if (process.argv.includes('--check')) assert.deepEqual(report, JSON.parse(readFileSync(target)));
else writeFileSync(target,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({pulses: report.pulses, maximum_grid_error_t: maxPhase, maximum_width_error_t: maxWidth, transition_cases: exhaustive}));

