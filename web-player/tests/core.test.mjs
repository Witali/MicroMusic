import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { AVRCore } from '../lib/avr-core.js';
import { parseHex } from '../lib/hex.js';
const require = createRequire(import.meta.url);
const { AVRCore: Reference } = require('../../ATtiny13A/Music/final/attiny13a_synth_release/avr_core.js');
const catalog = JSON.parse(readFileSync(new URL('../firmware.json', import.meta.url)));

for (const entry of catalog.entries) {
  test(`${entry.id}: 14 seconds match archived interpreter, PWM and exact CPU state`, () => {
    const flash = parseHex(entry.flashHex), ep = entry.eepromHex ? parseHex(entry.eepromHex, 64) : null;
    const ReferenceCore = entry.referenceCore ? require(fileURLToPath(new URL(entry.referenceCore,new URL('../',import.meta.url)))).AVRCore : Reference;
    const fast = new AVRCore(flash, ep), ref = new ReferenceCore(flash, ep);
    let changes = 0, last = -1;
    for (let i = 0; i < 14 * 37500; i++) {
      const sample = fast.nextDuty();
      assert.equal(sample, ref.nextDuty(), `PWM ${i}`);
      assert.equal(fast.cyc, ref.cyc, `Cycle ${i}`);
      if (sample !== last) changes++;
      last = sample;
    }
    for (const key of ['pc','cyc','z','c','i','overflowAt','pending','inIRQ','irqCount','lost','maxIRQ','writes'])
      assert.equal(fast[key], ref[key], key);
    assert.deepEqual(fast.r, ref.r); assert.deepEqual(fast.io, ref.io);
    assert.deepEqual(Array.from(fast.stack.subarray(0, fast.sp)), ref.stack);
    assert.ok(changes > 1000, 'No useful sound');
    assert.equal(fast.lost, 0);
    assert.equal(fast.workLost, 0);
    if (entry.referenceCore) assert.equal(fast.t, ref.t);
  });
}

test('single stepping and fast idle disabled preserve instruction boundaries', () => {
  const entry = catalog.entries.find(x => x.id === 'final');
  const flash = parseHex(entry.flashHex), ep = parseHex(entry.eepromHex, 64);
  const fast = new AVRCore(flash, ep, {fastIdle:false}), ref = new Reference(flash, ep);
  for (let i = 0; i < 20000; i++) {
    fast.step(); ref.step();
    assert.equal(fast.pc, ref.pc); assert.equal(fast.cyc, ref.cyc);
    assert.deepEqual(fast.r, ref.r); assert.deepEqual(fast.io, ref.io);
  }
});

test('HEX rejects corruption, overlaps, malformed and out-of-range records', () => {
  assert.throws(() => parseHex(':0100000000FE\n:00000001FF'));
  assert.throws(() => parseHex(':0100000000FF\n:0100000000FF\n:00000001FF'));
  assert.throws(() => parseHex(':0104000000FB\n:00000001FF'));
  assert.throws(() => parseHex(':00000001FF'));
  assert.throws(() => parseHex(':0100000000FF'));
  assert.throws(() => parseHex(':GG\n:00000001FF'));
  assert.equal(parseHex(':0100000000FF\n:00000001FF').length, 1);
});
