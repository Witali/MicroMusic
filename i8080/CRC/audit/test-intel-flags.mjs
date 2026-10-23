// Intel 8080/8085 Assembly Language Programming Manual (Intel, 1977/1978),
// printed pp. 1-12, 3-18..3-30, 3-56..3-64. Test 8080, not 8085, rules.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const root = fileURLToPath(new URL('../', import.meta.url));
const parity = value => { let n = value, count = 0; while (n) { count += n & 1; n >>>= 1; } return 1 - (count & 1); };
let total = 0, failed = 0;
const firstFailures = [];
function check(actual, expected, label) {
  total++;
  if (actual !== expected) {
    failed++;
    if (firstFailures.length < 12) firstFailures.push({ label, actual, expected });
  }
}
function szp(cpu, value, label) {
  check(cpu.S, value >>> 7, label + ' S');
  check(cpu.Z, Number(value === 0), label + ' Z');
  check(cpu.P, parity(value), label + ' P');
}

for (const mode of ['32K_A15_UNUSED', '64K_A15_CONNECTED']) {
  const file = path.join(root, 'CRC16/integration/no-ram-diagnostics', mode, 'verify_8080.js');
  const source = readFileSync(file, 'utf8');
  const boundary = source.indexOf("const path=require('path');");
  assert.ok(boundary > 0, 'CPU/test separation changed');
  // Load the actual retained CPU class without running the file's ROM tests.
  const CPU = vm.runInNewContext(source.slice(0, boundary) + '\nCPU8080;', { require, console }, { filename: file });
  const cpu = new CPU(new Uint8Array(65536), '8080', 3500000, 0);
  cpu.nextSnapshot = Infinity;
  function instruction(bytes) {
    cpu.mem.set(bytes, 0); cpu.PC = 0; cpu.cycles = 0; cpu.halted = false;
    return cpu.step();
  }
  const before = failed;
  for (let a = 0; a < 256; a++) for (let operand = 0; operand < 256; operand++) {
    cpu.A = a; cpu.CY = 1; cpu.AC = 1;
    cpu.alu(4, operand);
    check(cpu.A, a & operand, mode + ' ANA value');
    check(cpu.CY, 0, mode + ' ANA CY');
    check(cpu.AC, Number(((a | operand) & 8) !== 0), mode + ' ANA AC');
    szp(cpu, a & operand, mode + ' ANA');
    for (const group of [2, 3, 7]) for (const cy of [0, 1]) {
      const borrow = group === 3 ? cy : 0;
      const difference = a - operand - borrow;
      // 8080 AC is the half carry of A + ~operand + 1-borrow.
      const halfSum = (a & 15) + ((~operand) & 15) + 1 - borrow;
      cpu.A = a; cpu.CY = cy;
      cpu.alu(group, operand);
      check(cpu.A, group === 7 ? a : difference & 255, mode + ' SUB/SBB/CMP value');
      check(cpu.CY, Number(difference < 0), mode + ' SUB/SBB/CMP CY');
      check(cpu.AC, Number(halfSum > 15), mode + ' SUB/SBB/CMP AC');
      szp(cpu, difference & 255, mode + ' SUB/SBB/CMP');
    }
  }
  for (let value = 0; value < 256; value++) for (const cy of [0, 1]) {
    for (const decrement of [false, true]) {
      cpu.B = value; cpu.CY = cy;
      check(instruction([decrement ? 0x05 : 0x04]), 5, 'INR/DCR register T');
      check(cpu.B, (value + (decrement ? -1 : 1)) & 255, 'INR/DCR value');
      check(cpu.CY, cy, 'INR/DCR preserves CY');
      check(cpu.AC, Number(decrement ? (value & 15) !== 0 : (value & 15) === 15), 'INR/DCR AC');
      szp(cpu, cpu.B, 'INR/DCR');
    }
    for (const opcode of [0x07, 0x0F, 0x17, 0x1F]) {
      cpu.A = value; cpu.CY = cy; cpu.S = 1; cpu.Z = 1; cpu.P = 0; cpu.AC = 1;
      check(instruction([opcode]), 4, 'rotate T');
      const right = opcode === 0x0F || opcode === 0x1F;
      const throughCarry = opcode === 0x17 || opcode === 0x1F;
      const outgoing = right ? value & 1 : value >>> 7;
      const incoming = throughCarry ? cy : outgoing;
      const expected = right ? (value >>> 1) | (incoming << 7) : ((value << 1) | incoming) & 255;
      check(cpu.A, expected, 'rotate value'); check(cpu.CY, outgoing, 'rotate CY');
      check(cpu.S, 1, 'rotate preserves S'); check(cpu.Z, 1, 'rotate preserves Z');
      check(cpu.P, 0, 'rotate preserves P'); check(cpu.AC, 1, 'rotate preserves AC');
    }
  }
  for (let value = 0; value < 65536; value++) {
    cpu.HL = value; cpu.S = 1; cpu.Z = 1; cpu.P = 0; cpu.AC = 1;
    check(instruction([0x29]), 10, 'DAD H T');
    check(cpu.HL, (value * 2) & 65535, 'DAD H value');
    check(cpu.CY, value >>> 15, 'DAD H CY');
    check(cpu.S, 1, 'DAD preserves S'); check(cpu.Z, 1, 'DAD preserves Z');
    check(cpu.P, 0, 'DAD preserves P'); check(cpu.AC, 1, 'DAD preserves AC');
  }
  for (const value of [0x25, 0x47]) {
    cpu.A = value; instruction([0xEE, 0x62]);
    const expectedP = parity(value ^ 0x62);
    instruction([0x4F]); // MOV C,A must preserve P before JPE.
    check(cpu.P, expectedP, 'XRI/MOV/JPE parity');
    check(instruction([0xEA, 0x34, 0x12]), 10, 'JPE T');
    check(cpu.PC, expectedP ? 0x1234 : 3, 'JPE target');
  }
  cpu.H = 0x78;
  for (let n = 1; n <= 8; n++) {
    instruction([0x24]); // INR H, followed by JP, as in gen_planes_57.
    const expectedH = 0x78 + n;
    instruction([0xF2, 0x34, 0x12]);
    check(cpu.H, expectedH, 'table-generator H');
    check(cpu.PC, expectedH < 0x80 ? 0x1234 : 3, 'JP tests S from INR H');
  }
  cpu.A = 0x3E; instruction([0x97]);
  check(cpu.AC, 1, 'Intel SUB A example, printed p. 3-64');
  instruction([0x27]); check(cpu.A, 6, 'DAA must observe AC after SUB A');
  cpu.A = 4; cpu.B = 2; cpu.CY = 1; instruction([0x98]);
  check(cpu.A, 1, 'Intel SBB example value'); check(cpu.AC, 1, 'Intel SBB example AC');
  cpu.HL = 0x1234; cpu.DE = 0xABCD;
  const flagsBeforeExchange = cpu.flags();
  check(instruction([0xEB]), 4, 'Intel XCHG: 4 T, printed p. 3-65');
  check(cpu.HL, 0xABCD, 'XCHG HL'); check(cpu.DE, 0x1234, 'XCHG DE');
  check(cpu.flags(), flagsBeforeExchange, 'XCHG preserves flags');
  cpu.mem[0x200] = 0xD5; cpu.mem[0x201] = 0xA7; cpu.SP = 0x200;
  check(instruction([0xF1]), 10, 'POP PSW T');
  check(cpu.A, 0xA7, 'POP PSW high byte A');
  check(cpu.flags(), 0xD7, 'POP PSW flags/reserved bits');
  check(cpu.SP, 0x202, 'POP PSW SP');
  console.log(`${mode}: ${failed - before} mismatches`);
}
console.log(JSON.stringify({ checks: total, mismatches: failed, firstFailures }, null, 2));
assert.equal(failed, 0, 'Intel 8080 flag or timing mismatch');
