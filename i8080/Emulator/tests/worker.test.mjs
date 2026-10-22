import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { CPU8080, AudioBus } from '../core8080.mjs';

// Execute the actual worker handler, including asynchronous chunks, without browser globals.
const source = readFileSync(new URL('../worker.mjs', import.meta.url), 'utf8').replace(/^import .*\n/, '');
function run(rom, overrides = {}) {
  return new Promise(resolve => {
    const messages = [], self = { postMessage: message => { messages.push(message); if (message.kind === 'done' || message.kind === 'error') resolve({ result: message, messages }); } };
    vm.runInNewContext(source, { self, CPU8080, AudioBus, Uint8Array, setTimeout });
    self.onmessage({ data: { rom: rom.buffer, hz: 3500000, rate: 96000, output: 'inte', seconds: 0.1, memoryMode: 'rom', inputByte: 255, ...overrides } });
  });
}
test('Worker returns final registers, INTE, T-states and transferable audio', async () => {
  const { result } = await run(Uint8Array.of(0xfb, 0x00, 0xf3, 0x76));
  assert.equal(result.kind, 'done'); assert.equal(result.t, 19); assert.equal(result.steps, 4);
  assert.equal(result.stopReason, 'HLT'); assert.equal(result.inte, 0); assert.equal(result.edges, 2);
  assert.equal(result.pc, 4); assert.equal(result.rate, 96000); assert.ok(result.audio.byteLength > 0);
});
test('Worker chunks long loops and returns an explicit time limit', async () => {
  const { result, messages } = await run(Uint8Array.of(0xc3, 0, 0), { seconds: 0.5 });
  assert.ok(messages.some(m => m.kind === 'progress')); assert.equal(result.stopReason, 'time_limit');
  assert.equal(result.halted, false); assert.equal(result.t, 1750000); assert.equal(result.steps, 175000);
});
test('Worker rejects invalid settings and reports opcode faults', async () => {
  assert.equal((await run(Uint8Array.of(0x08))).result.kind, 'error');
  assert.equal((await run(Uint8Array.of(0), { hz: NaN })).result.kind, 'error');
});
test('Live worker streams ordered audio chunks before final WAV data', async () => {
  const { result, messages } = await run(Uint8Array.of(0xfb, 0, 0xf3, 0x76), { realtime: true });
  const streamed = messages.filter(m => m.kind === 'audio').flatMap(m => [...new Float32Array(m.audio)]);
  assert.deepEqual(streamed, [...new Float32Array(result.audio)]);
  assert.equal(messages[0].kind, 'audio'); assert.equal(result.t, 19);
});
