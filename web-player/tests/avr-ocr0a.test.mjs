import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as WASM} from '../lib/avr-core.js';

// Microchip DS40002307A, register descriptions p.81 / summary p.164:
// OCR0A is I/O 0x36 (data 0x56); I/O 0x2A is reserved, OCR0B is I/O 0x29.
const rom = words => Uint8Array.from(words.flatMap(w => [w & 255, w >> 8]));
const out = (address, register) => [0xb800 | (register << 4) | (address & 15) | ((address & 48) << 5)];
const sts = (address, register) => [0x9200 | (register << 4), address + 32];

for (const [engine, Core] of [['JS', JS], ['WASM', WASM]]) for (const [bus, instruction, clocks] of [['OUT', out, 1], ['STS', sts, 2]]) {
  test(engine + '/' + bus + ': reserved 0x2A produces no audio; actual OCR0A 0x36 and OCR0B 0x29 form one stereo frame', () => {
    const core = new Core(rom([
      ...instruction(0x2a, 16), ...instruction(0x36, 17), ...instruction(0x29, 18),
    ]), null, {fastIdle:false});
    core.writeIO(0x2f, 0xa3); core.writeIO(0x33, 1);
    core.r[16] = 203; core.r[17] = 51; core.r[18] = 31;
    core.sreg = 0x73;
    core.step();
    assert.equal(core.leftWrites, 0); assert.equal(core.writes, 0);
    assert.equal(core.dutyLeft, 128); assert.equal(core.duty, 128);
    assert.equal(core.cyc, clocks);
    assert.equal(core.nextStereoDuty(), 51 | (31 << 8));
    assert.equal(core.leftWrites, 1); assert.equal(core.writes, 1);
    assert.equal(core.io[0x36], 51); assert.equal(core.io[0x29], 31);
    assert.equal(core.data[0x56], 51); assert.equal(core.data[0x49], 31);
    assert.equal(core.sreg, 0x73); assert.equal(core.cyc, 3 * clocks);
  });
}
