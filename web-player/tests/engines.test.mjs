import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {Worker, MessageChannel} from 'node:worker_threads';
import {createRenderer, DEFAULT_ENGINE} from '../lib/engines.js';
import {ReferenceRenderer} from './helpers/reference-audio.mjs';
import {sameCPU, snapshot} from './helpers/avr-test-state.mjs';
const catalog = JSON.parse(readFileSync(new URL('../firmware.json', import.meta.url)));
function sameSamples(actual, expected) {
  assert.equal(actual.length, expected.length);
  let max = 0;
  for (let n = 0; n < actual.length; n++) max = Math.max(max, Math.abs(actual[n] - expected[n]));
  assert.ok(max < 2e-7, 'PCM error ' + max);
}

test('WASM is the default; explicit JS runs without WebAssembly and unknown engines fail', async () => {
  assert.equal(DEFAULT_ENGINE, 'wasm');
  const defaultRenderer = await createRenderer(catalog.entries[0], 48000);
  assert.equal(defaultRenderer.engine, 'wasm'); assert.ok(defaultRenderer.core._exports);
  const script = `globalThis.WebAssembly=undefined;
    const {readFileSync}=await import('node:fs');
    const {createRenderer}=await import(${JSON.stringify(new URL('../lib/engines.js', import.meta.url).href)});
    const entry=JSON.parse(readFileSync(new URL(${JSON.stringify(new URL('../firmware.json', import.meta.url).href)}))).entries[0];
    const renderer=await createRenderer(entry,48000,{},'js');
    if(renderer.engine!=='js'||renderer.core._exports||!renderer.render(4096).some(x=>x!==0))throw Error('JS engine unavailable');`;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', script], {encoding:'utf8'});
  assert.equal(result.status, 0, result.stderr);
  await assert.rejects(createRenderer(catalog.entries[0], 48000, {}, 'typo'), /Unknown AVR engine/);
});

for (const entry of catalog.entries) for (const rate of [22050, 44100, 48000, 96000])
test(entry.id + ' / ' + rate + ': selectable JS and WASM preserve PCM, counters and independent DSP expectations', async () => {
  const controls = {cutoff:9000, volume:.65};
  const js = await createRenderer(entry, rate, controls, 'js'), wasm = await createRenderer(entry, rate, controls, 'wasm');
  const reference = new ReferenceRenderer(entry, rate, controls);
  assert.equal(js.engine, 'js'); assert.equal(wasm.engine, 'wasm');
  for (const count of [1, 127, 4096, 17, 8193]) {
    const output = js.render(count), native = wasm.render(count), expected = reference.render(count);
    sameSamples(output, native); sameSamples(output, expected);
    assert.deepEqual(js.core.rawSamples, wasm.core.rawSamples);
    assert.deepEqual(js.core.rawSamples, reference.rawSamples);
    assert.ok(Math.abs(js.core.averagePWM - wasm.core.averagePWM) < 1e-12);
    sameCPU(js.core, wasm.core); sameCPU(js.core, reference.core);
    assert.equal(js.frames, wasm.frames); assert.equal(js.core.lost, 0); assert.equal(js.core.workLost, 0);
  }
});

test('JS controls smooth like WASM, remain block independent and do not advance paused clocks', async () => {
  const entry = catalog.entries[0];
  const a = await createRenderer(entry, 48000, {}, 'js'), b = await createRenderer(entry, 48000, {}, 'js'), native = await createRenderer(entry, 48000, {}, 'wasm');
  for (const renderer of [a, b, native]) renderer.render(4096);
  for (const controls of [{cutoff:12000, volume:.2}, {cutoff:4000, volume:0}]) {
    for (const renderer of [a, b, native]) {
      const paused = snapshot(renderer.core); renderer.setAudioControls(controls);
      assert.deepEqual(snapshot(renderer.core), paused);
    }
    const expected = a.render(16384), actual = new Float32Array(16384); let offset = 0;
    for (const count of [1, 127, 4096, 17, 12143]) { actual.set(b.render(count), offset); offset += count; }
    assert.deepEqual(actual, expected); sameSamples(actual, native.render(16384)); sameCPU(a.core, native.core);
    assert.ok(actual.every(Number.isFinite));
    if (!controls.volume) assert.ok(actual.slice(-1024).every(x => Math.abs(x) < 1e-8));
  }
  const restarted = await createRenderer(entry, 48000, {cutoff:4000, volume:0}, 'wasm');
  assert.equal(restarted.frames, 0); assert.equal(restarted.core.cyc, 0); assert.equal(restarted.core.irqCount, 0);
  assert.ok(restarted.render(4096).every(x => x === 0), 'Current controls survive a fresh engine');
});

test('JS rejects invalid audio requests before advancing CPU', async () => {
  const entry = catalog.entries[0];
  for (const rate of [0, NaN, 7999, 192001]) await assert.rejects(createRenderer(entry, rate, {}, 'js'), /sample rate/);
  for (const controls of [{volume:-1}, {volume:2}, {volume:NaN}, {cutoff:0}, {cutoff:Infinity}])
    await assert.rejects(createRenderer(entry, 48000, controls, 'js'), /audio configuration/);
  const renderer = await createRenderer(entry, 48000, {}, 'js'), before = snapshot(renderer.core);
  for (const count of [0, -1, .5, 16385, NaN]) assert.throws(() => renderer.render(count), /block size/);
  assert.deepEqual(snapshot(renderer.core), before);
});

function message(target, type) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { target.off('message', receive); reject(new Error(type + ' timed out')); }, 10000);
    function receive(data) {
      if (data.type !== type && data.type !== 'error') return;
      clearTimeout(timer); target.off('message', receive);
      if (data.type === 'error') reject(new Error(data.message)); else resolve(data);
    }
    target.on('message', receive);
  });
}
for (const engine of [undefined, 'js', 'wasm', 'transpiled','device'])
test('real Worker ' + (engine ?? 'default') + ': immediate init, queued controls and audio port use the chosen engine', async t => {
  const worker = new Worker(new URL('./helpers/browser-worker-node.mjs', import.meta.url));
  t.after(() => worker.terminate());
  const ready = message(worker, 'ready'), ports = new MessageChannel();
  t.after(() => ports.port1.close());
  const entry = catalog.entries[0], controls = {cutoff:6000, volume:0};
  worker.postMessage({type:'init', entry, engine, sampleRate:48000});
  worker.postMessage({type:'controls', controls});
  worker.postMessage({type:'audio-port', port:ports.port2, sampleRate:48000}, [ports.port2]);
  assert.equal((await ready).engine, engine ?? DEFAULT_ENGINE);
  const expected = await createRenderer(entry, 48000, controls, engine);
  for (let n = 0; n < 3; n++) {
    const state = message(worker, 'state'), samples = message(ports.port1, 'samples');
    ports.port1.postMessage({type:'need', frames:4096});
    const [actualState, actual] = await Promise.all([state, samples]);
    sameSamples(actual.samples, expected.render(4096));
    assert.ok(actual.samples.every(x => x === 0), 'Queued mute must precede audio initialization');
    assert.deepEqual(actualState.state, expected.core.state());
  }
});
