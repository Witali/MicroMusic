import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { AVRCore } from '../lib/avr-core.js';
import { parseHex } from '../lib/hex.js';
const require = createRequire(import.meta.url);
const { AVRCore: Reference } = require('../../ATtiny13A/Music/final/attiny13a_synth_release/avr_core.js');
const catalog = JSON.parse(readFileSync(new URL('../firmware.json', import.meta.url)));

for (const entry of catalog.entries) {
  test(`${entry.id}: 14 seconds preserve archived PWM and register state`, () => {
    const flash = parseHex(entry.flashHex), ep = entry.eepromHex ? parseHex(entry.eepromHex, 64) : null;
    const fast = new AVRCore(flash, ep), ref = new Reference(flash, ep);
    let changes = 0, last = -1;
    for (let i = 0; i < 14 * 37500; i++) {
      const sample = fast.nextDuty();
      assert.equal(sample, ref.nextDuty(), `PWM ${i}`);
      assert.ok(Math.abs(fast.cyc-ref.cyc)<=2, `RETI foreground latency at PWM ${i}`);
      if (sample !== last) changes++;
      last = sample;
    }
    // Archive compatibility is a musical regression, not a hardware oracle.
    // Its SREG and SRAM stack are known to be incomplete (see avr-audit.txt).
    for (const key of ['pc','cyc','c','i','overflowAt','pending','inIRQ','irqCount','lost','maxIRQ','writes'])
      assert.equal(fast[key], ref[key], key);
    assert.deepEqual(fast.r, ref.r);
    assert.ok(changes > 1000, 'No useful sound');
    assert.equal(fast.lost, 0);
  });
}

test('fast idle matches single stepping at every output boundary', () => {
  const entry = catalog.entries.find(x => x.id === 'final');
  const flash = parseHex(entry.flashHex), ep = parseHex(entry.eepromHex, 64);
  const fast = new AVRCore(flash, ep), ref = new AVRCore(flash, ep, {fastIdle:false});
  for (let i = 0; i < 20000; i++) {
    assert.equal(fast.nextDuty(), ref.nextDuty());
    assert.equal(fast.pc, ref.pc); assert.equal(fast.cyc, ref.cyc);
    assert.deepEqual(fast.data, ref.data);
    assert.equal(fast.sp, ref.sp); assert.equal(fast.pending, ref.pending);
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
