// Isolated C/ASM primitive equivalence and ABI; no C decoder is run or timed.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';
const dir = resolve(process.argv[2]);
const binary = readFileSync(join(dir, 'rng.bin'));
const metadata = JSON.parse(readFileSync(join(dir, 'input.json')));
assert.equal(createHash('sha256').update(binary).digest('hex'), metadata.binarySha256);
const symbols = new Map(readFileSync(join(dir, 'symbols.txt'), 'utf8').split(/\r?\n/)
  .map(line => line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean)
  .map(match => [match[2], parseInt(match[1], 16) & 65535]));
const at = name => { assert.ok(symbols.has(name), name); return symbols.get(name); };
const [input, output, command, status, entry, end] = [
  'rng_input', 'rng_result', 'rng_command', 'rng_status', 'rng_test_asm', '__bss_end'].map(at);
const program = new Uint16Array(16384).fill(65535);
new Uint8Array(program.buffer).set(binary);
const cpu = new CPU(program, 2048);
const preserved = [...Array.from({length: 16}, (_, i) => i + 2), 28, 29];
let snapshot = null, returns = 0, minCycles = Infinity, maxCycles = 0, muls = 0;
function until(predicate) {
  const deadline = cpu.cycles + 10000;
  while (!predicate()) {
    assert.ok(cpu.cycles < deadline, 'Primitive timeout');
    const pc = cpu.pc, opcode = cpu.progMem[pc];
    if (pc * 2 === entry) {
      assert.equal(snapshot, null);
      const original = preserved.map(reg => cpu.data[reg]);
      const values = preserved.map(reg => (returns * 73 + reg * 19) & 255);
      preserved.forEach((reg, i) => { cpu.data[reg] = values[i]; });
      snapshot = {sp: cpu.SP, values, original, start: cpu.cycles, muls: 0};
    }
    if ((opcode & 0xfc00) === 0x9c00 || (opcode & 0xff00) === 0x0200 || (opcode & 0xff00) === 0x0300) {
      ++muls;
      if (snapshot) ++snapshot.muls;
    }
    avrInstruction(cpu); cpu.tick();
    assert.ok(cpu.SP >= end, 'Stack collision');
    if (opcode === 0x9508 && snapshot && cpu.SP === snapshot.sp + 2) {
      assert.deepEqual(preserved.map(reg => cpu.data[reg]), snapshot.values, 'Callee-saved ABI');
      assert.equal(cpu.data[1], 0, 'r1 restored');
      assert.equal(snapshot.muls, 7, 'Exactly seven hardware multiplies');
      const elapsed = cpu.cycles - snapshot.start;
      minCycles = Math.min(minCycles, elapsed); maxCycles = Math.max(maxCycles, elapsed);
      preserved.forEach((reg, i) => { cpu.data[reg] = snapshot.original[i]; });
      snapshot = null; ++returns;
    }
  }
}
until(() => cpu.data[status] === 1);
const seeds = new Set([0, 1, 0xffffffff, 1000, 0x7fffffff, 0x80000000, 0x00ffffff]);
for (let bit = 0; bit < 32; ++bit) {
  const power = (2 ** bit) >>> 0;
  seeds.add(power); seeds.add((power - 1) >>> 0); seeds.add((power + 1) >>> 0);
}
for (let word = 0; word < 65536; ++word) {
  seeds.add((((word * 40503) & 65535) * 65536 + word) >>> 0);
  seeds.add((word * 65536 + 65535) >>> 0);
}
let state = 0x11223344;
for (let i = 0; i < 4096; ++i) {
  state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
  seeds.add(state >>> 0);
}
let asmMuls = 0, cMuls = 0;
for (const value of seeds) {
  const expected = Number((1664525n * BigInt(value) + 1013904223n) & 0xffffffffn);
  for (const kind of [1, 2]) {
    cpu.dataView.setUint32(input, value, true);
    cpu.data[status] = 1; cpu.data[command] = kind;
    const before = muls;
    until(() => cpu.data[status] === 2);
    assert.equal(cpu.dataView.getUint32(output, true), expected, 'Seed ' + value + ' backend ' + kind);
    assert.equal(cpu.dataView.getUint32(input, true), value);
    assert.equal(cpu.data[1], 0);
    if (kind === 1) asmMuls += muls - before;
    else cMuls += muls - before;
  }
}
assert.equal(returns, seeds.size);
const result = {binarySha256: metadata.binarySha256, scope: 'Isolated exact LCG primitive; C decoder not executed or timed',
  seeds: seeds.size, allLowWordsCovered: true, allHighWordsCovered: true, cAndAsmExact: true,
  calleeSavedAndR1Returns: returns, arbitraryCalleeSavedPatterns: true, asmMulsPerSeed: asmMuls / seeds.size,
  genericCMulsPerSeed: cMuls / seeds.size, asmFunctionMinCycles: minCycles, asmFunctionMaxCycles: maxCycles,
  includesInterrupts: false, physicalBoardTested: false};
writeFileSync(join(dir, 'verification.json'), JSON.stringify(result, null, 2) + '\n');
console.log('PASS', JSON.stringify(result));
