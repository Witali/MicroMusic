// Validate the WASM ABI and sequential >64-KiB model access independently of AVR.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {resolve, dirname, join} from 'node:path';
import {loadSpiModel} from './spi_model.mjs';

const payload = Buffer.from(Array.from({length: 70003}, (_, i) => (i * 73 + (i >> 8)) & 255));
const address = 0xff80;
const filename = resolve(process.argv[2]);
const model = await loadSpiModel(filename, payload, address);
assert.equal(model.transfer(255), 255, 'Deselected bus pulled up');
model.select(false);
for (const value of [11, address >> 16, (address >> 8) & 255, address & 255, 255])
  assert.equal(model.transfer(value), 0);
for (const value of payload) assert.equal(model.transfer(255), value);
model.select(true);
const stats = model.stats();
assert.equal(stats.commandBytes, 1);
assert.equal(stats.addressBytes, 3);
assert.equal(stats.dummyBytes, 1);
assert.equal(stats.readBytes, payload.length);
assert.equal(stats.selectedBytes, payload.length + 5);
assert.equal(stats.transferCalls, payload.length + 6);
assert.equal(stats.csAssertions, 1);
assert.equal(stats.csDeassertions, 1);
assert.equal(stats.unsupportedCommands, 0);
assert.equal(stats.resets, 0);
writeFileSync(join(dirname(filename), 'verification.json'), JSON.stringify({passed: true,
  scope: 'Host-only shared C model / WASM ABI; no AVR timing claim',
  wasmSha256: createHash('sha256').update(readFileSync(filename)).digest('hex'),
  payloadBytes: payload.length, startAddress: address, modelStats: stats}, null, 2) + '\n');
console.log('PASS shared C model via WASM:', JSON.stringify(stats));
