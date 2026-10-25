import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';

const player = new URL('../', import.meta.url);
const load = path => JSON.parse(readFileSync(new URL(path, player)));
const hash = data => createHash('sha256').update(data).digest('hex');
const catalog = load('firmware-attiny88-legacy.json');
const original = load('firmware.json');

test('ATtiny88 offers the same nine arrangements in the same order', () => {
  assert.equal(catalog.device, 'attiny88');
  assert.equal(catalog.entries.length, 9);
  assert.deepEqual(catalog.entries.map(e => [e.id, e.order, e.title]),
    original.entries.map(e => [e.id, e.order, e.title]));
  assert.equal(catalog.defaultId, original.defaultId);
  assert.deepEqual(catalog.sourceOnly, []);
  assert.equal(catalog.hardwareProfile.name, 'ATtiny88');
  assert.equal(catalog.hardwareProfile.flashCapacity, 8192);
  assert.equal(catalog.hardwareProfile.sramCapacity, 512);
  assert.deepEqual(catalog.hardwareProfile.requiredFuses, {low:'0xEE',high:'0xDF',extended:'0xFF'});
});

for (const entry of catalog.entries) {
  test(`${entry.id}: target downloads, clocks, pins and music metadata match verified port`, () => {
    const prior = original.entries.find(e => e.id === entry.id);
    const report = load(entry.buildReport);
    const verification = load(entry.verificationSource);
    assert.equal(entry.device, 'attiny88');
    assert.match(entry.source, /^\.\.\/ATtiny88\/Music\/variants\/[^/]+\/synth\.hex$/);
    assert.match(entry.eepromSource, /^\.\.\/ATtiny88\/Music\/variants\/[^/]+\/eeprom\.hex$/);
    assert.equal(entry.originalPlayer, undefined);
    assert.equal(entry.preview, undefined);
    assert.equal(entry.referenceCore, undefined);
    for (const key of ['voices', 'instruments', 'releaseTailSlots', 'audioChannels', 'panorama'])
      assert.deepEqual(entry[key], prior[key], `${key} retained`);
    for (const key of ['source', 'eepromSource', 'sourceAssembly', 'buildReport', 'verificationSource'])
      assert.ok(existsSync(new URL(entry[key], player)), `Missing ${key}`);
    assert.equal(entry.flashHex, readFileSync(new URL(entry.source, player), 'utf8').replace(/\r\n/g, '\n'));
    assert.equal(entry.eepromHex, readFileSync(new URL(entry.eepromSource, player), 'utf8').replace(/\r\n/g, '\n'));
    assert.equal(hash(readFileSync(new URL(entry.source.replace(/\.hex$/, '.bin'), player))), entry.flashSha256);
    assert.equal(hash(readFileSync(new URL(entry.eepromSource.replace(/\.hex$/, '.bin'), player))), entry.eepromSha256);
    assert.equal(entry.flashSha256, report.flashSha256);
    assert.equal(entry.eepromSha256, report.eepromSha256);
    assert.equal(entry.flashBytes, report.flashBytes);
    assert.ok(entry.flashBytes <= entry.flashCapacity && entry.flashCapacity === 8192);
    assert.equal(entry.eepromBytes, 64);
    assert.equal(entry.eepromCapacity, 64);
    assert.equal(entry.cpuHz, 8000000);
    assert.equal(entry.pwmHz, 31250);
    assert.equal(entry.sampleHz, 31250);
    assert.equal(entry.synthesisHz, 15625);
    assert.equal(verification.allMusicalStatesMatch, true);
    assert.equal(verification.allMusicalCommandsMatch, true);
    assert.equal(verification.port.flashSha256, entry.flashSha256);
    assert.equal(verification.port.eepromSha256, entry.eepromSha256);
    assert.equal(verification.port.fifoUnderruns, 0);
    const right = entry.outputs.find(o => o.channel === (entry.audioChannels === 2 ? 'R' : 'mono'));
    assert.deepEqual(right, {channel:entry.audioChannels === 2 ? 'R' : 'mono',pin:'PB2',compare:'OC1B',register:'OCR1B',packagePin:16});
    if (entry.audioChannels === 2)
      assert.deepEqual(entry.outputs[0], {channel:'L',pin:'PB1',compare:'OC1A',register:'OCR1A',packagePin:15});
  });
}
