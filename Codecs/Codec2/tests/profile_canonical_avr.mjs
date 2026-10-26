// Non-intrusive instruction/call profiling of the already verified linked image.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = resolve(root, '../../build/codec2/canonical');
const report = JSON.parse(readFileSync(join(root, 'reports/canonical-decoder.json')));
const hash = b => createHash('sha256').update(b).digest('hex');
const binary = readFileSync(join(build, 'atmega64a/decoder.bin'));
assert.equal(hash(binary), report.avr_build.binary_sha256);
const entries=readFileSync(join(build, 'atmega64a/symbols.txt'), 'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+(\w)\s+(.+)$/)).filter(Boolean).map(m=>[m[3],{at:parseInt(m[1],16),type:m[2]}]);
const symbols=new Map(entries);
// Keep duplicate static names from every translation unit in the PC map.
const counts=new Map();for(const [name,s] of entries)if(/[tT]/.test(s.type))counts.set(name,(counts.get(name)??0)+1);
const code=entries.filter(([,s])=>/[tT]/.test(s.type)).map(([name,s])=>[counts.get(name)>1?name+'@'+s.at.toString(16):name,s]).sort((a,b)=>a[1].at-b[1].at);
const address = n => { assert.ok(symbols.has(n), n); return symbols.get(n).at & 0xffff; };
function functionAt(pc) {
  let lo = 0, hi = code.length;
  while (lo + 1 < hi) { const mid = (lo + hi) >> 1; if (code[mid][1].at <= pc * 2) lo = mid; else hi = mid; }
  return code[lo][0];
}
const at = process.argv.indexOf('--frames');
const limit = at < 0 ? 5 : Number(process.argv[at + 1]);
assert.ok(Number.isInteger(limit) && limit > 0);
const memory = report.avr_build.manufacturer_header_memory, top = address('__stack'), end = address('__bss_end');
assert.equal(top, memory.RAMEND);
const results = [];
for (const record of report.avr_execution.results) {
  const stream=report.streams.find(s=>s.name===record.name);
  const source = readFileSync(stream.packet_path ? join(build,stream.packet_path) : join(root, 'AVR/Codec2_Tiny13_Quality_R2/tests', record.name));
  assert.equal(hash(source), record.packetSha256);
  const expected = readFileSync(join(build, record.name + '.avr.pcm'));
  assert.equal(hash(expected), record.outputSha256);
  const program = new Uint16Array((memory.FLASHEND + 1) / 2).fill(0xffff);
  new Uint8Array(program.buffer).set(binary);
  const cpu = new CPU(program, top - memory.RAMSTART + 1); cpu.SP = top;
  const status = address('codec2_decode_status'), calls = [], inclusive = new Map(), exclusive = new Map(), stages = new Map();
  let measuring = false, total = 0;
  const charge = (map, key, cycles) => map.set(key, (map.get(key) ?? 0) + cycles);
  function until(predicate) {
    const deadline = cpu.cycles + 150000000;
    while (!predicate()) {
      assert.ok(cpu.cycles < deadline);
      const pc = cpu.pc, opcode = program[pc], before = cpu.cycles;
      avrInstruction(cpu); cpu.tick();
      assert.ok(cpu.SP >= end - 1 && cpu.SP <= top);
      const cost = cpu.cycles - before;
      if (measuring) {
        total += cost; charge(exclusive, functionAt(pc), cost);
        for (const name of new Set(calls.map(c => c.name))) charge(inclusive, name, cost);
        const stage = calls.find(c => ['codec2_analysis_forward', 'codec2_weight_init', 'codec2_weight_dc', 'codec2_weight_pair', 'codec2_fixed_inverse', 'codec2_fixed_fifth', 'codec2_canonical_lsp_to_lpc'].includes(c.name));
        charge(stages, stage?.name ?? 'other', cost);
      }
      const absoluteCall = (opcode & 0xfe0e) === 0x940e;
      const relativeCall = (opcode & 0xf000) === 0xd000;
      const indirectCall = opcode === 0x9509 || opcode === 0x9519;
      // RCALL .+0 reserves two stack bytes; it does not introduce a function.
      if (absoluteCall || indirectCall || (relativeCall && cpu.pc !== pc + 1))
        calls.push({name: functionAt(cpu.pc), returnPC: pc + (absoluteCall ? 2 : 1)});
      if (opcode === 0x9508 || opcode === 0x9518) {
        assert.equal(calls.at(-1)?.returnPC, cpu.pc, `Unbalanced call at byte PC ${(pc * 2).toString(16)}`);
        calls.pop();
      }
    }
  }
  until(() => cpu.data[status] !== 0); assert.equal(cpu.data[status], 1);
  const frames = Math.min(limit, source.length / 8), output = Buffer.alloc(frames * 320);
  measuring = true;
  for (let frame = 0; frame < frames; ++frame) {
    cpu.data.set(source.subarray(frame * 8, frame * 8 + 8), address('codec2_decode_packet'));
    cpu.data[status] = 1; cpu.data[address('codec2_decode_command')] = 1;
    until(() => cpu.data[status] !== 1); assert.equal(cpu.data[status], 2);
    output.set(cpu.data.subarray(address('codec2_decode_pcm'), address('codec2_decode_pcm') + 320), frame * 320);
  }
  assert.deepEqual(output, expected.subarray(0, output.length));
  assert.equal(total, record.perFrameCycles.slice(0, frames).reduce((a, b) => a + b, 0));
  const ranked = map => [...map].sort((a, b) => b[1] - a[1]).map(([name, cycles]) => ({name, cycles, percent: cycles * 100 / total}));
  const result = {name: record.name, frames, samples: frames * 160, totalCycles: total, meanCycles: total / frames,
    stages: ranked(stages), inclusive: ranked(inclusive).slice(0, 30), exclusive: ranked(exclusive).slice(0, 30),
    packetSha256: hash(source), outputSha256: hash(output), binarySha256: hash(binary)};
  results.push(result); console.log(JSON.stringify(result));
}
const profile = JSON.stringify({simulator: 'avr8js 0.21.1', mcu: 'ATmega64A', results,
  profilerSha256: hash(readFileSync(fileURLToPath(import.meta.url))),
  scope: 'Prefix instruction profiling of verified binary; PCM/cycles checked against complete AVR output. Inclusive costs overlap. No IRQ.'}, null, 2) + '\n';
writeFileSync(join(build, 'profile.json'), profile);
if (process.argv.includes('--record')) writeFileSync(join(root, 'reports/canonical-profile.json'), profile);
