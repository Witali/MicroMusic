import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {Worker, MessageChannel} from 'node:worker_threads';
import {createRenderer} from '../lib/engines.js';
import {AVRMusicTargetCore} from '../lib/avr-attiny88.js';
import {AVRCore as JSCore} from '../lib/avr-reference.js?v=20261025-um88';
import {AVRMusicTargetCore as AuditCore} from '../../tools/avr-music-target-core.mjs';
import {parseHex} from '../lib/hex.js';

const variants = ['rhythmic', 'lumiere-stereo', 'alicia', 'children', 'turkish-march',
  'greensleeves', 'cancion-del-mariachi', 'cancion-del-mariachi-polyphonic', 'cancion-del-mariachi-sparse'];
function entryFor(id) {
  const folder = new URL('../../ATtiny88/Music/variants/' + id + '/', import.meta.url);
  const report = JSON.parse(readFileSync(new URL('build-report.json', folder)));
  return {id, device:'attiny88', cpuHz:report.cpuHz, pwmHz:report.pwmHz, audioChannels:report.audioChannels,
    flashHex:readFileSync(new URL('synth.hex', folder), 'utf8'),
    eepromHex:readFileSync(new URL('eeprom.hex', folder), 'utf8')};
}

test('ATtiny88 playback and firmware audits use the configurable AVR core in both engines', async () => {
  assert.equal(AuditCore, AVRMusicTargetCore);
  const entry = entryFor('rhythmic');
  assert.equal((await createRenderer(entry, 48000)).engine, 'wasm');
  await assert.rejects(createRenderer(entry, 48000, {}, 'unknown'), /Unknown AVR engine/);
  const renderer = await createRenderer(entry, 48000, {}, 'js');
  assert.equal(renderer.engine, 'js');
  assert.ok(renderer.core instanceof JSCore);
  assert.equal(renderer.core.profile.flashBytes, 8192);
  assert.equal(renderer.core.sram.length, 512);
  assert.equal(renderer.core.cpuHz, 8000000);
  assert.equal(renderer.ratio, 31250 / 48000);
});

for (const engine of ['js','wasm']) for (const id of variants) test(engine + ' / ' + id + ': browser renderer runs actual ATtiny88 HEX at 8 MHz / Timer1, without lost interrupts', async () => {
  const entry = entryFor(id), renderer = await createRenderer(entry, 48000, {}, engine);
  const binary = readFileSync(new URL('../../ATtiny88/Music/variants/' + id + '/synth.bin', import.meta.url));
  assert.deepEqual(Buffer.from(parseHex(entry.flashHex, 8192)), binary);
  assert.ok(binary.length > 1024 || id === 'greensleeves');
  if (binary.length > 1024) assert.throws(() => parseHex(entry.flashHex), /device memory/);
  let energy = 0, difference = 0;
  for (let block = 0; block < 4; block++) {
    const pcm = renderer.render(8192);
    assert.equal(pcm.length, 8192 * entry.audioChannels);
    assert.ok(pcm.every(Number.isFinite));
    for (const sample of pcm) energy += sample * sample;
    if (entry.audioChannels === 2) for (let n = 0; n < pcm.length; n += 2) difference += Math.abs(pcm[n] - pcm[n + 1]);
  }
  assert.ok(energy > 1, 'Firmware produces audible signal');
  if (entry.audioChannels === 2) {
    assert.ok(difference > 1, 'OC1A/OC1B remain distinct stereo channels');
    assert.equal(renderer.core.leftWrites, renderer.core.writes);
  }
  assert.equal(renderer.frames, 32768);
  assert.equal(renderer.core.state().lost, 0);
  assert.ok(Math.abs(renderer.core.irqCount - 32768 / 48000 * 31250) < 10, 'Timer1 overflow rate is 31.25 kHz');
  assert.ok(Math.abs(renderer.core.cyc - 32768 / 48000 * 8000000) < 10000, 'CPU runs at 8 MHz');
});

for (const engine of ['js','wasm']) test(engine + ': ATtiny88 stereo resampling and control smoothing are independent of audio block boundaries', async () => {
  const entry = entryFor('lumiere-stereo');
  const whole = await createRenderer(entry, 44100, {}, engine), split = await createRenderer(entry, 44100, {}, engine);
  for (const controls of [{volume:.3, cutoff:7500}, {volume:0, cutoff:2000}]) {
    for (const renderer of [whole, split]) renderer.setAudioControls(controls);
    const expected = whole.render(16384), actual = new Float32Array(32768);
    let offset = 0;
    for (const count of [1, 127, 4096, 17, 12143]) { actual.set(split.render(count), offset); offset += count * 2; }
    assert.deepEqual(actual, expected);
    assert.deepEqual(split.core.state(), whole.core.state());
    assert.deepEqual(split.core.data, whole.core.data);
  }
});

function message(target, type) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { target.off('message', receive); reject(new Error(type + ' timed out')); }, 10000);
    function receive(data) {
      if (data.type !== type && data.type !== 'error') return;
      clearTimeout(timeout); target.off('message', receive);
      if (data.type === 'error') reject(new Error(data.message)); else resolve(data);
    }
    target.on('message', receive);
  });
}

for (const engine of ['js','wasm']) for (const id of ['lumiere-stereo', 'cancion-del-mariachi-sparse']) test(engine + ' / ' + id + ': actual browser Worker preserves ATtiny88 selection and PCM channels', async t => {
  const worker = new Worker(new URL('./helpers/browser-worker-node.mjs', import.meta.url));
  t.after(() => worker.terminate());
  const ports = new MessageChannel(); t.after(() => ports.port1.close());
  const entry = entryFor(id), controls = {volume:.5, cutoff:6000};
  const ready = message(worker, 'ready');
  worker.postMessage({type:'init', entry, engine, sampleRate:48000, controls});
  worker.postMessage({type:'audio-port', port:ports.port2, sampleRate:48000}, [ports.port2]);
  assert.equal((await ready).engine, engine);
  const expected = await createRenderer(entry, 48000, controls, engine);
  for (let n = 0; n < 3; n++) {
    const state = message(worker, 'state'), samples = message(ports.port1, 'samples');
    ports.port1.postMessage({type:'need', frames:4096});
    const [actualState, actual] = await Promise.all([state, samples]);
    assert.deepEqual(actual.samples, expected.render(4096));
    assert.deepEqual(actualState.state, expected.core.state());
    assert.equal(actualState.scopes.length, entry.audioChannels);
    assert.equal(actualState.averages.length, entry.audioChannels);
  }
});
