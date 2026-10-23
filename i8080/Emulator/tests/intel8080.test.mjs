import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { CPU8080, AudioBus, is8080Opcode } from '../core8080.mjs';

const cpu = (code, memoryMode = 'allram', audio = null) => new CPU8080(Uint8Array.from(code), { memoryMode, audio, mode: audio?.mode || 'inte' });
const parity = v => { let ones = 0; for (let bit = 0; bit < 8; bit++) ones += (v >> bit) & 1; return 1 - (ones % 2); };

test('Intel SUB and SBB examples, AC propagation into DAA', () => {
  let c = cpu([0x97]); c.r[7] = 0x3e; c.step();
  assert.equal(c.r[7], 0); assert.deepEqual(c.f, { s: 0, z: 1, p: 1, cy: 0, ac: 1 });
  c = cpu([0x98]); c.r[7] = 0xa4; c.r[0] = 0x02; c.f.cy = 1; c.step();
  assert.equal(c.r[7], 0xa1); assert.equal(c.f.ac, 1);
  c = cpu([0xaf, 0x9f, 0x27]); c.step(); c.step(); c.step(); assert.equal(c.r[7], 6);
  c = cpu([0x27]); c.r[7] = 0x9b; c.step(); assert.equal(c.r[7], 1); assert.equal(c.f.cy, 1); assert.equal(c.f.ac, 1);
});

test('Exhaustive ALU results and all five flags (1,048,576 input combinations)', () => {
  const c = cpu([0]);
  let cases = 0;
  for (let op = 0; op < 8; op++) for (let a = 0; a < 256; a++) for (let b = 0; b < 256; b++) for (let carry = 0; carry < 2; carry++) {
    c.r[7] = a; c.f.cy = carry; c.alu(op, b);
    let value, cy = 0, ac = 0;
    if (op < 2) { const n = a + b + (op ? carry : 0); value = n & 255; cy = +(n > 255); ac = +((a % 16) + (b % 16) + (op ? carry : 0) >= 16); }
    else if (op < 4 || op === 7) { const borrow = op === 3 ? carry : 0; value = (a - b - borrow) & 255; cy = +(a < b + borrow); ac = +((a % 16) >= (b % 16) + borrow); }
    else if (op === 4) { value = a & b; ac = +(((a | b) & 8) !== 0); }
    else value = op === 5 ? a ^ b : a | b;
    const f = c.f;
    if (c.r[7] !== (op === 7 ? a : value) || f.cy !== cy || f.ac !== ac || f.z !== +(value === 0) || f.s !== +(value >= 128) || f.p !== parity(value)) {
      assert.fail(`ALU ${op} A=${a} operand=${b} carry=${carry}`);
    }
    cases++;
  }
  assert.equal(cases, 1048576);
});

test('INR/DCR on every register and M preserve CY, with Intel AC polarity', () => {
  const c = cpu(new Uint8Array(65536));
  for (const increment of [true, false]) for (let reg = 0; reg < 8; reg++) for (let value = 0; value < 256; value++) for (let carry = 0; carry < 2; carry++) {
    c.pc = 0; c.setpair(2, 0x2000); c.mem[0] = (increment ? 4 : 5) + reg * 8;
    if (reg === 6) c.mem[0x2000] = value; else c.r[reg] = value;
    c.f.cy = carry; c.step();
    assert.equal(c.get(reg), (value + (increment ? 1 : -1)) & 255);
    assert.equal(c.f.cy, carry); assert.equal(c.f.ac, +(increment ? value % 16 === 15 : value % 16 !== 0));
  }
});

// Intel instruction table: fixed 8080 T-states. Conditional RET/CALL use the
// not-taken entry here and have separately checked taken costs of 11 / 17 T.
const timingRows = [
  '4 10 7 5 5 5 7 4 - 10 7 5 5 5 7 4',
  '- 10 7 5 5 5 7 4 - 10 7 5 5 5 7 4',
  '- 10 16 5 5 5 7 4 - 10 16 5 5 5 7 4',
  '- 10 13 5 10 10 10 4 - 10 13 5 5 5 7 4',
  '5 5 5 5 5 5 7 5 5 5 5 5 5 5 7 5',
  '5 5 5 5 5 5 7 5 5 5 5 5 5 5 7 5',
  '5 5 5 5 5 5 7 5 5 5 5 5 5 5 7 5',
  '7 7 7 7 7 7 7 7 5 5 5 5 5 5 7 5',
  '4 4 4 4 4 4 7 4 4 4 4 4 4 4 7 4',
  '4 4 4 4 4 4 7 4 4 4 4 4 4 4 7 4',
  '4 4 4 4 4 4 7 4 4 4 4 4 4 4 7 4',
  '4 4 4 4 4 4 7 4 4 4 4 4 4 4 7 4',
  '5 10 10 10 11 11 7 11 5 10 10 - 11 17 7 11',
  '5 10 10 10 11 11 7 11 5 - 10 10 11 - 7 11',
  '5 10 10 18 11 11 7 11 5 5 10 4 11 - 7 11',
  '5 10 10 4 11 11 7 11 5 5 10 4 11 - 7 11',
];
const timings = timingRows.flatMap(row => row.split(' ').map(s => s === '-' ? null : Number(s)));
test('All 256 bytes: 244 documented timings and 12 deliberate traps', () => {
  assert.equal(timings.filter(t => t !== null).length, 244);
  for (let op = 0; op < 256; op++) {
    const c = cpu([op, 0x34, 0x12]); c.sp = 0x8000; c.setpair(2, 0x2000);
    assert.equal(is8080Opcode(op), timings[op] !== null);
    if (timings[op] === null) { assert.throws(() => c.step(), /Undocumented/); continue; }
    if ((op & 0xc7) === 0xc0 || (op & 0xc7) === 0xc4) {
      const k = (op >> 3) & 7, field = ['z', 'cy', 'p', 's'][k >> 1];
      c.f[field] = (k & 1) ? 0 : 1;
    }
    assert.equal(c.step(), timings[op], `opcode ${op.toString(16)}`);
  }
});

test('Every conditional JMP/CALL/RET, taken and not taken; return-address writes', () => {
  for (let k = 0; k < 8; k++) for (const taken of [false, true]) for (const kind of ['jump', 'call', 'ret']) {
    const op = (kind === 'jump' ? 0xc2 : kind === 'call' ? 0xc4 : 0xc0) + 8 * k;
    const c = cpu([op, 0x34, 0x12]); c.sp = 0x4000; c.mem[0x4000] = 0x78; c.mem[0x4001] = 0x56;
    c.f[['z', 'cy', 'p', 's'][k >> 1]] = +(taken === !!(k & 1));
    c.step();
    assert.equal(c.pc, taken ? kind === 'ret' ? 0x5678 : 0x1234 : kind === 'ret' ? 1 : 3);
    assert.equal(c.t, kind === 'jump' ? 10 : kind === 'call' ? taken ? 17 : 11 : taken ? 11 : 5);
    assert.equal(c.sp, 0x4000 + (taken ? kind === 'call' ? -2 : kind === 'ret' ? 2 : 0 : 0));
    if (taken && kind === 'call') assert.equal(c.read16(c.sp), 3);
  }
});

test('Independent implementation: all documented opcodes over 32 seeded states', () => {
  const text = readFileSync(new URL('../../CRC/CRC16/integration/no-ram-diagnostics/64K_A15_CONNECTED/verify_8080.js', import.meta.url), 'utf8');
  const context = { require: () => ({}), Uint8Array, Float32Array, Math };
  vm.runInNewContext(text.split("const path=require('path');")[0] + '\nthis.ReferenceCPU = CPU8080;', context);
  let cases = 0;
  for (let op = 0; op < 256; op++) {
    if (!is8080Opcode(op) || op === 0x27) continue; // DAA has its own BCD/Intel tests.
    for (let seed = 0; seed < 32; seed++) {
      const image = new Uint8Array(65536); for (let i = 0; i < image.length; i++) image[i] = (i * 37 + seed * 17) & 255;
      image[0] = op; image[1] = 0x34; image[2] = 0x12;
      const c = new CPU8080(image), ref = new context.ReferenceCPU(image, '8080', 3500000, 0.01);
      const names = ['B', 'C', 'D', 'E', 'H', 'L', '', 'A'];
      for (let i = 0; i < 8; i++) if (i !== 6) c.r[i] = ref[names[i]] = (seed * 29 + i * 11) & 255;
      c.sp = ref.SP = (seed * 313 + 0x3000) & 65535;
      c.unpackFlags(seed * 7); ref.setFlags(seed * 7);
      c.step(); ref.step();
      for (let i = 0; i < 8; i++) if (i !== 6) assert.equal(c.r[i], ref[names[i]], `op ${op.toString(16)} reg ${names[i]}`);
      assert.equal(c.packFlags(), ref.flags(), `op ${op.toString(16)} PSW`);
      assert.equal(c.pc, ref.PC); assert.equal(c.sp, ref.SP); assert.equal(c.t, ref.cycles);
      assert.equal(c.memWrites, ref.writes); assert.equal(c.ioWrites, ref.portWrites); assert.equal(c.inte, ref.inte);
      cases++;
    }
  }
  assert.equal(cases, 7776);
});

test('Every memory/port write produces ordered /WR edges, including ignored ROM writes', () => {
  for (const op of [0x02, 0x12, 0x22, 0x32, 0x34, 0x35, 0x36, 0x70, 0x77, 0xc5, 0xd5, 0xe5, 0xf5, 0xcd, 0xc7, 0xff, 0xe3, 0xd3]) {
    const audio = new AudioBus(3500000, 96000, 'wr', 1); audio.trackEvents = true;
    const c = cpu([op, 0x10, 0x20], 'rom', audio); c.setpair(2, 0x3000); c.sp = 0x4000;
    c.step();
    const writes = c.memWrites + c.ioWrites;
    assert.ok(writes > 0); assert.equal(audio.transitions.length, 2 * writes);
    for (let i = 0; i < audio.transitions.length; i += 2) {
      const [begin, low] = audio.transitions[i], [end, high] = audio.transitions[i + 1];
      assert.equal(low, 0); assert.equal(high, 1); assert.equal(end - begin, 1); assert.ok(end <= c.t);
      if (i) assert.ok(begin >= audio.transitions[i - 1][0]);
    }
    assert.equal(c.ignoredWrites, c.memWrites);
  }
});

test('Address wrapping, memory maps, PSW constants, HLT idempotence and DAD flag preservation', () => {
  let c = cpu([0xe5]); c.sp = 1; c.setpair(2, 0x1234); c.step();
  assert.equal(c.sp, 65535); assert.equal(c.read16(65535), 0x1234);
  c.pc = 2; c.mem[2] = 0xe1; c.step(); assert.equal(c.hl(), 0x1234); assert.equal(c.sp, 1);
  c = cpu(new Uint8Array(32768), 'rom'); c.mem[123] = c.mem[32768 + 123] = 0x78;
  c.write(123, 0x99); c.write(32768 + 123, 0x99); assert.equal(c.read(123), 0x78); assert.equal(c.read(32768 + 123), 0x78);
  c = cpu([0], 'ramupper'); c.write(1, 0x22); c.write(32768, 0x33); assert.equal(c.read(1), 255); assert.equal(c.read(32768), 0x33);
  c.unpackFlags(255); assert.equal(c.packFlags(), 0xd7); c.unpackFlags(0); assert.equal(c.packFlags(), 2);
  c = cpu([0x76]); assert.equal(c.step(), 7); assert.equal(c.step(), 0); assert.equal(c.count, 1);
  c = cpu([0x29]); c.setpair(2, 0x9234); c.unpackFlags(0xd6); c.step(); assert.equal(c.hl(), 0x2468); assert.equal(c.packFlags(), 0xd7);
});

test('Area integration preserves INTE duty cycle and /WR pulse area below one sample', () => {
  const audio = new AudioBus(1000000, 10000, 'inte', 1); audio.edge(1, 25); audio.edge(0, 75);
  const data = audio.finish(200); assert.deepEqual([...data], [0.5, 0]);
  const wr = new AudioBus(1000000, 10000, 'wr', 1); wr.edge(0, 13); wr.edge(1, 14);
  assert.ok(Math.abs(wr.finish(100)[0] - 0.99) < 1e-6);
  assert.throws(() => wr.edge(0, 2), /Out-of-order/);
  assert.throws(() => new CPU8080(Uint8Array.of(0), { memoryMode: 'typo' }), /memory/);
  assert.throws(() => new CPU8080(Uint8Array.of(0), { pc: -1 }), /pc/);
  assert.throws(() => new AudioBus(0, 96000, 'inte', 1), /Invalid/);
});
