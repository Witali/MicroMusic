import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseIntelHex } from '../formats.mjs';

test('Example library: preferred tempo, seven intact images, and standalone embeds exactly the same ROMs', () => {
  execFileSync(process.execPath, [fileURLToPath(new URL('../scripts/build-examples.mjs', import.meta.url)), '--check']);
  const catalog = JSON.parse(readFileSync(new URL('../examples.json', import.meta.url)));
  assert.equal(catalog.defaultId, 'voice159'); assert.equal(catalog.entries.length, 7);
  assert.deepEqual(catalog.entries.filter(entry => entry.id.endsWith('-pwm108')).map(entry => entry.id),
    ['uniform26-pwm108', 'balanced27-pwm108']);
  const html = readFileSync(new URL('../Intel_8080_ROM_Player.html', import.meta.url), 'utf8');
  assert.doesNotMatch(html, /fetch\(new URL\(entry\.rom/);
  assert.doesNotMatch(html, /fetch\(new URL\('\.\/examples\.json/);
  for (const entry of catalog.entries) {
    const rom = readFileSync(new URL(entry.rom, new URL('../', import.meta.url)));
    assert.equal(rom.length, entry.bytes); assert.equal(rom.length, 32768);
    assert.equal(createHash('sha256').update(rom).digest('hex'), entry.sha256);
    assert.ok(html.includes(rom.toString('base64')), entry.id + ' embedded bytes');
    if (/\/(Sound|Music)\//.test(entry.rom)) assert.deepEqual(parseIntelHex(readFileSync(new URL(entry.rom.replace(/\.bin$/, '.hex'), new URL('../', import.meta.url)), 'utf8')), new Uint8Array(rom));
    assert.equal(entry.hz, 3500000); assert.equal(entry.output, 'inte'); assert.equal(entry.memory, 'rom');
  }
});
