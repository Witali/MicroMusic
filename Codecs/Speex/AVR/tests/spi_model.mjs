// Host-only facade; all payload reads go through the shared C protocol model.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const statNames = ['transferCalls', 'selectedBytes', 'commandBytes', 'addressBytes',
  'dummyBytes', 'readBytes', 'csAssertions', 'csDeassertions', 'unsupportedCommands', 'resets'];

export async function loadSpiModel(filename, payload, address) {
  assert.ok(Number.isInteger(address) && address >= 0 && address + payload.length <= 16777216);
  const {instance} = await WebAssembly.instantiate(readFileSync(filename));
  const api = instance.exports;
  const start = api.speex_spi_image();
  const image = new Uint8Array(api.memory.buffer, start, 16777216);
  image.fill(255);
  image.set(payload, address);
  assert.equal(api.speex_spi_init(), 1);
  return {
    select: high => api.speex_spi_select(Number(high)),
    transfer: value => api.speex_spi_transfer(value),
    stats: () => Object.fromEntries(statNames.map((name, i) => {
      const value = api.speex_spi_stat(i);
      assert.ok(value <= BigInt(Number.MAX_SAFE_INTEGER));
      return [name, Number(value)];
    })),
  };
}
