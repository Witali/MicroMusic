// Execute linked GNU AVR machine code against records from the pinned upstream.
// Decoder front end only: no waveform synthesis and no active-IRQ admission.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = resolve(root, '../../build/codec2/frontend');
const frames = readFileSync(join(build, 'frames.bin'));
const expected = readFileSync(join(build, 'expected.bin'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const evidence = JSON.parse(readFileSync(join(build, 'host-and-build.json'), 'utf8'));
assert.equal(hash(frames), evidence.inputs_sha256);
assert.equal(hash(expected), evidence.expected_sha256);
assert.equal(frames.length % 8, 0);
assert.equal(expected.length, frames.length / 8 * 34);
const results = [];

for (const [mcu, flash, sram, base] of [['attiny13', 1024, 64, 0x60], ['atmega328p', 32768, 2048, 0x100]]) {
  const directory = join(build, mcu);
  const binary = readFileSync(join(directory, 'frontend.bin'));
  assert.equal(hash(binary), evidence[mcu].binary_sha256);
  assert.ok(binary.length <= flash);
  const symbols = new Map(readFileSync(join(directory, 'symbols.txt'), 'utf8').split(/\r?\n/)
    .map(s => s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m => [m[2], parseInt(m[1], 16)]));
  function address(name) {
    assert.ok(symbols.has(name), `Missing symbol ${name}`);
    return symbols.get(name) & 0xffff;
  }
  const status = address('codec2_test_status'), command = address('codec2_test_command');
  const packet = address('codec2_test_packet'), output = address('codec2_test_params');
  const end = address('__bss_end');
  const program = new Uint16Array(flash / 2).fill(0xffff);
  new Uint8Array(program.buffer).set(binary);
  // AVR8js's CPU uses a common 0x100 data prefix. For Tiny13, initialize SP
  // at the physical 0x9f top and explicitly check stack bounds/collision.
  const cpu = new CPU(program, sram);
  cpu.SP = base + sram - 1;
  let minimumSP = base + sram - 1;
  function until(predicate, limit = 100000) {
    const deadline = cpu.cycles + limit;
    while (!predicate()) {
      assert.ok(cpu.cycles < deadline, `${mcu}: timeout at byte PC ${(cpu.pc * 2).toString(16)}`);
      avrInstruction(cpu);
      cpu.tick();
      if (cpu.SP > 0) {
        assert.ok(cpu.SP <= base + sram - 1, `${mcu}: stack outside physical SRAM`);
        assert.ok(cpu.SP >= end - 1, `${mcu}: stack collision`);
        minimumSP = Math.min(minimumSP, cpu.SP);
      }
    }
  }
  until(() => cpu.data[status] === 1);
  let maximumCycles = 0;
  for (let i = 0; i < frames.length / 8; ++i) {
    cpu.data.set(frames.subarray(i * 8, i * 8 + 8), packet);
    cpu.data[status] = 1;
    cpu.data[command] = 1;
    const start = cpu.cycles;
    until(() => cpu.data[status] !== 1);
    assert.equal(cpu.data[status], 2, `${mcu}: API error`);
    maximumCycles = Math.max(maximumCycles, cpu.cycles - start);
    assert.deepEqual(Buffer.from(cpu.data.subarray(output, output + 34)),
      expected.subarray(i * 34, i * 34 + 34), `${mcu}: packet ${i}`);
  }
  results.push({mcu, packets: frames.length / 8, mismatches: 0, flashBytes: binary.length,
    staticSramBytes: end - base, stackBytes: base + sram - 1 - minimumSP,
    freeSramAtPeak: minimumSP - end + 1, maximumCycles, includesInterrupts: false,
    binarySha256: hash(binary)});
  console.log(JSON.stringify(results.at(-1)));
}
writeFileSync(join(build, 'avr-execution.json'), JSON.stringify({simulator: 'avr8js 0.21.1',
  inputsSha256: hash(frames), expectedSha256: hash(expected), results}, null, 2) + '\n');
