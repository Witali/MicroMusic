// Execute both MUL and no-MUL AVR C builds against the same native integer results.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = resolve(root, '../../build/codec2/lpc');
const meta = JSON.parse(readFileSync(join(build, 'build.json'), 'utf8'));
const vectors = readFileSync(join(build, 'avr-vectors.bin'));
const expected = readFileSync(join(build, 'avr-expected.bin'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
assert.equal(hash(vectors), meta.avr_vectors_sha256);
assert.equal(hash(expected), meta.avr_expected_sha256);
assert.equal(vectors.length, meta.avr_vector_count * 20);
assert.equal(expected.length, meta.avr_vector_count * 44);
const results = [];
for (const mcu of ['attiny88', 'atmega328p']) {
  const directory = join(build, mcu);
  const binary = readFileSync(join(directory, 'lpc.bin'));
  const memory = meta.mcus[mcu].manufacturer_header_memory;
  const capacity = memory.FLASHEND + 1;
  assert.equal(hash(binary), meta.mcus[mcu].binary_sha256);
  assert.ok(binary.length <= capacity);
  const symbols = new Map(readFileSync(join(directory, 'symbols.txt'), 'utf8').split(/\r?\n/)
    .map(s => s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m => [m[2], parseInt(m[1], 16)]));
  function address(name) {
    assert.ok(symbols.has(name), `Missing symbol ${name}`);
    return symbols.get(name) & 0xffff;
  }
  const base = memory.RAMSTART, top = address('__stack'), end = address('__bss_end');
  assert.equal(top, memory.RAMEND);
  const input = address('codec2_lpc_test_lsp'), output = address('codec2_lpc_test_ak');
  const status = address('codec2_lpc_test_status'), command = address('codec2_lpc_test_command');
  const program = new Uint16Array(capacity / 2).fill(0xffff);
  new Uint8Array(program.buffer).set(binary);
  const cpu = new CPU(program, top - base + 1);
  cpu.SP = top;
  let minimumSP = top;
  function until(predicate, limit = 2000000) {
    const deadline = cpu.cycles + limit;
    while (!predicate()) {
      assert.ok(cpu.cycles < deadline, `${mcu}: timeout at byte PC ${(cpu.pc * 2).toString(16)}`);
      avrInstruction(cpu); cpu.tick();
      assert.ok(cpu.SP <= top && cpu.SP >= end - 1, `${mcu}: stack collision or invalid SP`);
      minimumSP = Math.min(minimumSP, cpu.SP);
    }
  }
  until(() => cpu.data[status] === 1);
  let maximumCycles = 0, totalCycles = 0;
  for (let i = 0; i < meta.avr_vector_count; ++i) {
    cpu.data.set(vectors.subarray(i * 20, i * 20 + 20), input);
    cpu.data[status] = 1;
    cpu.data[command] = 1;
    const start = cpu.cycles;
    until(() => cpu.data[status] === 2);
    maximumCycles = Math.max(maximumCycles, cpu.cycles - start);
    totalCycles += cpu.cycles - start;
    assert.deepEqual(Buffer.from(cpu.data.subarray(output, output + 44)),
      expected.subarray(i * 44, i * 44 + 44), `${mcu}: vector ${i}`);
  }
  // nm sees the table in Flash, and no SRAM copy of the 322-byte LUT exists.
  assert.ok(symbols.get('codec2_cosine_quarter_q15') < 0x800000);
  const result = {mcu, vectors: meta.avr_vector_count, mismatches: 0, flashBytes: binary.length,
    staticSramBytes: end - base, stackBytes: top - minimumSP, freeSramAtPeak: minimumSP - end + 1,
    maximumCycles, meanCycles: totalCycles / meta.avr_vector_count, binarySha256: hash(binary), includesInterrupts: false};
  results.push(result);
  console.log(JSON.stringify(result));
}
writeFileSync(join(build, 'avr-execution.json'), JSON.stringify({simulator: 'avr8js 0.21.1',
  vectorsSha256: hash(vectors), expectedSha256: hash(expected), results}, null, 2) + '\n');
