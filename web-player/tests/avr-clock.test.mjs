import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore} from '../lib/avr-core.js';
import {AVRCore as Reference} from '../lib/avr-reference.js';
import {sameCPU, out} from './helpers/avr-test-state.mjs';

test('public clock(0) still expires control windows and settles an event at the current cycle', () => {
  const c = new AVRCore(Uint8Array.of(0, 0));
  c.writeIO(0x33, 1); c.cyc = 256; c.overflowAt = 256;
  c.io[0x1c] = 4; c.eempeUntil = 256; c.io[0x26] = 128; c.clkprUntil = 256;
  c.clock(0);
  assert.equal(c.cyc, 256); assert.equal(c.io[0x32], 0);
  assert.equal(c.io[0x1c] & 4, 0); assert.equal(c.io[0x26] & 128, 0);
  assert.equal(c.pending, true); assert.equal(c.overflowAt, 512);
  assert.equal(c.lost, 0); assert.equal(c.irqCount, 0);
});

const input = address => 0xb100 | (address & 15) | ((address & 48) << 5);
const commands = [
  ['IN', address => [input(address)], false],
  ['LDS', address => [0x9100, address + 32], false],
  ['LD X+', () => [0x910d], false],
  ['OUT', address => [out(address, 16)], true],
  ['STS', address => [0x9300, address + 32], true],
  ['ST X+', () => [0x930d], true],
  ['SBI EECR,EERE', () => [0x9ae0], true]
];
for (const [name, words, write] of commands)
test(name + ': bus clocks, EEPROM stalls, window expiry and IRQ boundaries match single-step JS', () => {
  const addresses = name.startsWith('SBI') ? [[0x1c, 1]] : write
    ? [[0x1c, 1], [0x26, 0], [0x28, 1], [0x29, 201], [0x32, 255], [0x33, 0], [0x38, 2], [0x39, 2], [0x3f, 255]]
    : [[0x1c, 0], [0x26, 0], [0x32, 0], [0x38, 0]];
  for (const [address, value] of addresses) for (const mode of [0, 3])
  for (const [source, divisor] of [[1, 1], [2, 8], [5, 1024]])
  for (const origin of [0, 2**32 - 2, 2**48 - 2]) for (const until of [1, 2, 4]) for (const delay of [0, 1]) {
    const rom = Uint8Array.from(words(address).flatMap(word => [word & 255, word >> 8]));
    const a = new AVRCore(rom, null, {fastIdle:false}), b = new Reference(rom, null, {fastIdle:false});
    for (const c of [a, b]) {
      c.cyc = origin + divisor - 1; c.prescalerAt = origin;
      c.writeIO(0x2f, mode); c.writeIO(0x33, source); c.writeIO(0x32, (mode === 3 ? 255 : 256) - until);
      c.writeIO(0x39, 2); c.i = 1; c.irqDelay = delay;
      c.io[0x1c] = 4; c.eempeUntil = c.cyc + until; c.io[0x26] = 128; c.clkprUntil = c.cyc + until;
      c.eeprom[0] = 0xa5; c.r[26] = address + 32; c.r[16] = value;
    }
    a.step(); b.step(); sameCPU(a, b, name + ' I/O ' + address.toString(16));
  }
});
