import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder, parseHeader } from '../lpx/codec.js';

const root = new URL('../', import.meta.url);
const decode = await createDecoder(readFileSync(new URL('lpx/decoder.wasm', root)));
const tone = n => Int16Array.from({ length: n }, (_, i) => Math.round(5000 * Math.sin(i * .14) + 700 * Math.sin(i * .31)));

test('3/8 kbit presets emit the same V9 format within complete-file caps on scalar and SIMD', async () => {
  const encoders = await Promise.all(['encoder-adaptive', 'encoder-adaptive-simd'].map(name =>
    createEncoder(readFileSync(new URL(`lpx/${name}.wasm`, root)))));
  for (const [kbps, n, wireProfile] of [[3, 8193, 4], [8, 4097, 6]]) {
    const pcm = tone(n), progress = [];
    const bytes = encoders[0](pcm, 8000, kbps, value => progress.push(value));
    assert.deepEqual(encoders[1](pcm, 8000, kbps), bytes, `${kbps}k scalar/SIMD`);
    assert.deepEqual(progress, [0, 1]);
    assert.deepEqual(Array.from(bytes.subarray(0, 2)), [76, 57], 'one L9 wire signature');
    assert.ok(bytes.length <= Math.floor(n * kbps * 1000 / 64000), 'includes header and final packets');
    const header = parseHeader(bytes), decoded = decode(bytes);
    assert.equal(header.profile, wireProfile);
    assert.equal(header.samples, n);
    assert.equal(header.sampleRate, 8000);
    assert.equal(decoded.pcm.length, n, 'partial final sample count is retained');
  }
});

test('explicit bitrate presets reject wrong rates, allowances and infeasible short inputs', async () => {
  const encode = await createEncoder(readFileSync(new URL('lpx/encoder-adaptive.wasm', root)));
  for (const kbps of [3, 8]) {
    assert.throws(() => encode(tone(8193), 12000, kbps), /8 кГц/);
    assert.throws(() => encode(tone(8193), 8000, kbps, () => {}, { sizeAllowancePercent: 10 }), /без допуска/);
    assert.throws(() => encode(new Int16Array(1), 8000, kbps), /полный поток/);
  }
  const oldModule = await createEncoder(readFileSync(new URL('lpx/encoder.wasm', root)));
  assert.throws(() => oldModule(tone(8193), 8000, 3), /Обновите страницу/);
  assert.ok(oldModule(tone(321), 8000, 4).length >= 13, 'old P4 remains supported');
});

test('3 kbit short gain-zero fallback and continuous silent Long streams retain all samples', async () => {
  const encoders = await Promise.all(['encoder-adaptive', 'encoder-adaptive-simd'].map(name =>
    createEncoder(readFileSync(new URL(`lpx/${name}.wasm`, root)))));
  for (const pcm of [tone(3201), new Int16Array(8193), new Int16Array(65537)]) {
    const bytes = encoders[0](pcm, 8000, 3);
    assert.deepEqual(encoders[1](pcm, 8000, 3), bytes);
    assert.ok(bytes.length <= Math.floor(pcm.length * 3 / 64));
    const result = decode(bytes);
    assert.equal(result.samples, pcm.length);
    assert.equal(result.profile, 4);
    assert.equal(result.long, pcm.length > 64000);
    if (pcm.every(value => value === 0)) assert.deepEqual(result.pcm, pcm);
  }
});

function converterPage(sampleCount = 8193) {
  const html = readFileSync(new URL('lpx/index.html', root), 'utf8');
  const elements = new Map(), workers = [], rates = [];
  class Element {
    constructor(value = '') { this.value = value; this.disabled = false; this.hidden = false; this.files = []; }
    classList = { toggle() {}, add() {}, remove() {} };
    addEventListener() {}
    querySelector() { return new Element(); }
    replaceChildren() {}
    removeAttribute() {}
  }
  for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) elements.set(match[1], new Element());
  for (const match of html.matchAll(/<select[^>]+id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
    const options = [...match[2].matchAll(/<option value="([^"]+)"/g)].map(option => option[1]);
    elements.get(match[1]).value = options[0]; elements.get(match[1]).options = options;
  }
  for (const match of html.matchAll(/<input[^>]+id="([^"]+)"[^>]*value="([^"]+)"[^>]*>/g)) elements.get(match[1]).value = match[2];
  const context = {
    MAX_SAMPLES: 32000000, MAX_STREAM_SAMPLES:64000000, supportsSimd: () => true, URL, Int16Array, Number, Math,
    recoverTemporaryInputs:async()=>{},removeTemporaryInput:async()=>{},crypto,
    document: { getElementById: id => {
      assert.ok(elements.has(id), `page has #${id}`); return elements.get(id);
    } },
    OfflineAudioContext: class {
      constructor(channels, length, rate) { this.rate = rate; rates.push(rate); }
      async decodeAudioData() { return { length: sampleCount, sampleRate: this.rate, duration: sampleCount / this.rate,
        numberOfChannels: 1, getChannelData: () => new Float32Array(sampleCount) }; }
    },
    Worker: class {
      constructor() { workers.push(this); }
      postMessage(message) { this.message = message; }
      terminate() { this.terminated = true; }
    }
  };
  const source = readFileSync(new URL('lpx/converter.js', root), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replaceAll('import.meta.url', JSON.stringify(new URL('lpx/converter.js', root).href));
  runInNewContext(source, context);
  return { elements, workers, rates };
}

test('converter uses accuracy levels at every rate without a complete-file bitrate cap', async () => {
  const { elements, workers, rates } = converterPage();
  const element = id => elements.get(id);
  assert.ok(element('encode-profile').options.includes('3'));
  assert.ok(element('encode-profile').options.includes('8'));
  element('encode-rate').value = '16000'; element('encode-allowance').value = '25';
  for (const kbps of ['3', '8']) {
    element('encode-profile').value = kbps; element('encode-profile').onchange();
    assert.equal(element('encode-rate').value, '16000');
    assert.equal(element('encode-allowance').value, '0');
    assert.equal(element('encode-rate').disabled, false);
    assert.equal(element('encode-allowance').disabled, true);
    assert.equal(element('bitrate-note').hidden, false);
  }
  element('source-file').files = [{ name: 'synthetic.ogg', size: 10, arrayBuffer: async () => new ArrayBuffer(0) }];
  element('encode-level').checked = true;
  assert.equal(element('encode-quality-target').value,'pwm');
  element('encode-quality-target').value='pcm';
  element('source-file').onchange();
  await element('convert').onclick();
  assert.deepEqual(rates, [16000]);
  assert.equal(workers[0].message.profile, 8);
  assert.equal(workers[0].message.sampleRate, 16000);
  assert.equal(workers[0].message.accuracy,true);
  assert.equal(workers[0].message.sizeAllowancePercent, 0);
  assert.equal(workers[0].message.normalization, 'loudness');
  assert.equal(workers[0].message.qualityTarget,'pcm');
  assert.equal(element('encode-quality-target').disabled,true);
  assert.equal(workers[0].message.targetLufs, -18);
  assert.equal(workers[0].message.maxGainDb, 12);
  assert.equal(element('encode-level').disabled, true);
  element('cancel-convert').onclick();
  assert.equal(workers[0].terminated, true);
  assert.equal(element('encode-profile').disabled, false);
  assert.equal(element('encode-level').disabled, false);
  assert.equal(element('encode-quality-target').disabled,false);
  assert.equal(element('encode-rate').disabled, false);
  assert.equal(element('encode-allowance').disabled, true);
  element('encode-profile').value = '6'; element('encode-profile').onchange();
  assert.equal(element('encode-rate').value, '16000');
  assert.equal(element('encode-allowance').value, '0');
  assert.equal(element('encode-rate').disabled, false);
  assert.equal(element('encode-allowance').disabled, true);
  assert.equal(element('bitrate-note').hidden, false);
});

test('converter auto streams long input without a whole PCM transfer and keeps explicit search choices',async()=>{
  const {elements,workers}=converterPage(131073),element=id=>elements.get(id);
  element('source-file').files=[{name:'synthetic.ogg',size:100,arrayBuffer:async()=>new ArrayBuffer(0)}];
  element('source-file').onchange();await element('convert').onclick();
  assert.equal(workers[0].message.processing,'stream');assert.equal(workers[0].message.samples,131073);
  assert.equal(workers[0].message.calls,0);assert.equal(workers[0].message.pcm,undefined);
  assert.equal(element('encode-processing').disabled,true);
  workers[0].onmessage({data:{read:{id:7,offset:20460,samples:20528}}});
  assert.equal(workers[0].message.readReply,7);assert.equal(workers[0].message.pcm.byteLength,41056);
  workers[0].onmessage({data:{phase:'encode',progress:.123}});
  assert.equal(element('convert-progress').value,12);assert.match(element('convert-status').textContent,/12,3%/);
  element('cancel-convert').onclick();assert.equal(workers[0].terminated,true);
  element('encode-processing').value='stream-refine';await element('convert').onclick();
  assert.equal(workers[1].message.calls,4);element('cancel-convert').onclick();
  element('encode-processing').value='full';await element('convert').onclick();
  assert.equal(workers[2].message.processing,undefined);assert.equal(workers[2].message.pcm.byteLength,131073*2);
  element('cancel-convert').onclick();assert.equal(element('encode-processing').disabled,false);
});

test('MP3/AAC/M4A/WAV are sent as File objects without whole-input decoding',async()=>{
  for(const extension of['mp3','aac','m4a','wav']){
    const{elements,workers,rates}=converterPage(),element=id=>elements.get(id);
    const file={name:'synthetic.'+extension,size:100,arrayBuffer(){throw Error('Whole input decoding forbidden');}};
    element('source-file').files=[file];element('source-file').onchange();await element('convert').onclick();
    assert.deepEqual(rates,[]);assert.equal(workers[0].message.source,file);assert.equal(workers[0].message.pcm,undefined);
    assert.match(workers[0].message.temporaryName,/^pcm-/);assert.equal(workers[0].message.accuracy,true);element('cancel-convert').onclick();
  }
});
