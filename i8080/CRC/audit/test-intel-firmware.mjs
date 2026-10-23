// Re-execute CRC firmware using the diagnostic CPU with Intel-correct AC flags.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const source = readFileSync(path.join(root, 'CRC16/integration/no-ram-diagnostics/64K_A15_CONNECTED/verify_8080.js'), 'utf8');
const boundary = source.indexOf("const path=require('path');");
assert.ok(boundary > 0);
const CPU = vm.runInNewContext(source.slice(0, boundary) + '\nCPU8080;', { require: createRequire(import.meta.url), console });
const read = name => new Uint8Array(readFileSync(path.join(root, name)));
function crcMSB(data, poly, width = 16, init = 0) {
  let crc = init;
  for (const byte of data) {
    crc ^= byte << (width - 8);
    for (let bit = 0; bit < 8; bit++) {
      const top = (crc >>> (width - 1)) & 1;
      crc = ((crc << 1) ^ (top ? poly : 0)) >>> 0;
      if (width === 16) crc &= 65535;
    }
  }
  return crc >>> 0;
}
function romFromCode(name, poly, width) {
  const code = read(name), rom = new Uint8Array(65536).fill(255);
  rom.set(code);
  const n = width / 8, residue = crcMSB(rom.subarray(0, 65536 - n), poly, width);
  for (let i = 0; i < n; i++) rom[65536 - n + i] = (residue >>> (8 * (n - i - 1))) & 255;
  assert.equal(crcMSB(rom, poly, width), 0);
  return rom;
}
let runs = 0;
function execute(label, rom, success, expectedCycles = null, ram = false) {
  const cpu = new CPU(rom, '8080', 3500000, 0);
  cpu.nextSnapshot = Infinity;
  // RESET does not clear general registers or S/Z/P/AC/CY.
  for (const reg of ['A', 'B', 'C', 'D', 'E', 'H', 'L']) cpu[reg] = 0xA5;
  cpu.S = cpu.Z = cpu.P = cpu.AC = cpu.CY = 1;
  cpu.SP = 0x6F01;
  const writes = new Set();
  cpu.writeMem = function(address, value) {
    assert.ok(ram && address >= 0x8000 && address < 0x8400, `${label}: unexpected write ${address.toString(16)}`);
    this.mem[address] = value & 255; writes.add(address);
  };
  while (!cpu.halted) {
    assert.ok(cpu.inst < 30000000, label + ': instruction limit');
    cpu.step();
  }
  assert.equal(cpu.inte, Number(success), label + ': INTE');
  if (expectedCycles !== null) assert.equal(cpu.cycles, expectedCycles, label + ': T states');
  runs++;
  console.log(`${label}: INTE=${cpu.inte}, ${cpu.cycles} T, ${cpu.inst} instructions`);
  return { cpu, writes };
}
const r16 = 'CRC16/research/';
const compact = r16 + '10_pair_0025_0047_v6_minimal/';
const fast = r16 + '09_pair_0025_0047_v5_fast/';
const profiles = [
  ['single_0009_33', r16 + '01_single_crc16_foundation/crc16_8080_fast33z_poly0009.bin', 0x0009, 16, 6164278],
  ['single_002D_39', r16 + '01_single_crc16_foundation/crc16_8080_fast39.bin', 0x002D, 16, 8785713],
  ['dual_0007_0009_66', r16 + '06_one_pass_v4_optimization/bin/optimized_66.bin', 0x000E003F, 32, 11738705],
  ['dual_0007_0021_66', r16 + '07_better_pair_0007_0021/dual_crc_0007_0021_onepass.bin', 0x002600E7, 32, 11738705],
  ['dual_0025_0047_42', compact + 'bin/bitwise_shared_parity.bin', 0x006209BB, 32, 50200714],
  ['dual_0025_0047_41_reset', compact + 'bin/bitwise_shared_parity_reset.bin', 0x006209BB, 32, 50200710],
  ['dual_0025_0047_57', compact + 'bin/bitwise_shared_parity_u4.bin', 0x006209BB, 32, 38404234],
  ['dual_0025_0047_75', fast + 'bin/fast75_peephole.bin', 0x006209BB, 32, 18882115],
  ['dual_0025_0047_82', fast + 'bin/fast_p47_rotate.bin', 0x006209BB, 32, 18292291]
];
for (const [label, name, poly, width, cycles] of profiles) {
  const rom = romFromCode(name, poly, width);
  execute(label, rom, true, cycles);
  rom[0x800] ^= 1; execute(label + ' damaged', rom, false);
}
const old = 'CRC32/research/04_crc32_ieee_castagnoli_comparison/';
const historicalCycles = {crc32_mpeg2_8080:58043088, crc32_mpeg2_8080_compact:68937832,
  crc32c_msb_8080:58069132, crc32c_msb_8080_compact:68937832};
for (const [name, cycles] of Object.entries(historicalCycles)) {
  const rom = read(old + name + '_ROM_64KiB.bin');
  execute(name, rom, true, cycles);
  rom[0x800] ^= 1; execute(name + ' damaged', rom, false);
}
for (const kib of [24, 32]) for (const profile of ['u1_halt', 'cachedB', 'u2_halt', 'u4_halt', 'u8_halt']) {
  const name = `crc32c_8080_${kib}k_${profile}`;
  const rom = read('CRC32/no-tables/' + name + '.bin');
  execute(name, rom, true);
  rom[0x800] ^= 1; execute(name + ' damaged', rom, false);
}
for (const kib of [24, 32]) {
  const name = `crc32c_8080_checked_${kib}k`;
  const rom = read('CRC32/checked-table/' + name + '.bin');
  execute(name, rom, true, kib === 24 ? 2873007 : 3810991);
  rom[0x100] ^= 1; execute(name + ' damaged table', rom, false);
}
for (const layout of ['planes', 'packed']) {
  const name = `gen_${layout}_57`;
  const { cpu, writes } = execute(name, read('CRC32/table-generator/' + name + '.bin'), false,
    layout === 'planes' ? 258322 : 255260, true);
  assert.equal(writes.size, 1024);
  for (let i = 0; i < 256; i++) {
    let expected = i;
    for (let b = 0; b < 8; b++) expected = ((expected >>> 1) ^ ((expected & 1) ? 0x82F63B78 : 0)) >>> 0;
    let actual = 0;
    for (let b = 0; b < 4; b++) actual |= cpu.mem[0x8000 + (layout === 'planes' ? i + 256 * b : i * 4 + b)] << (8 * b);
    assert.equal(actual >>> 0, expected);
  }
  assert.equal(cpu.SP, layout === 'planes' ? 0x6F01 : 0x8000);
}
console.log(`PASS: ${runs} firmware executions with Intel-correct flag rules`);
