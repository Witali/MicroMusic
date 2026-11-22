// Compare the shipped exhaustive WASM with the current production module.
// Audio stays local. Only timing, provenance and hashes are retained.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { cpus } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
import { parseArgs } from 'node:util';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder } from '../lpx/codec.js';

const { values } = parseArgs({ options: { output: { type: 'string' } } });
const root = fileURLToPath(new URL('../../', import.meta.url));
const revision = '688fc4f618f9ed6176501e0f5d6e55bcb8fc80cf';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const baseline = execFileSync('git', ['show', `${revision}:web-player/lpx/encoder.wasm`], { cwd: root });
assert.equal(hash(baseline), 'f59002ca5e46f6bee2616f28edf3fe61ff91972df93ded823b6af21c64355a49');
const candidate = readFileSync(resolve(root, 'web-player/lpx/encoder.wasm'));
const manifest = JSON.parse(readFileSync(resolve(root, 'web-player/lpx/encoder-build.json')));
assert.equal(hash(candidate), manifest.sha256);
const encoders = { baseline: await createEncoder(baseline), optimized: await createEncoder(candidate) };
const decode = await createDecoder(readFileSync(resolve(root, 'web-player/lpx/decoder.wasm')));

function speech(name, rate) {
  const path = `web-player/audio/originals/${name}.wav`;
  const args = ['-v', 'error', '-i', path, '-ac', '1', '-ar', String(rate), '-f', 's16le', 'pipe:1'];
  const bytes = execFileSync('ffmpeg', args, { cwd: root, maxBuffer: 4 * 1024 * 1024 });
  const pcm = new Int16Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length));
  return { name: `speech-${name}`, rate, pcm, source: { path, sha256: hash(readFileSync(resolve(root, path))), ffmpegArgs: args } };
}
const tone = length => Int16Array.from({ length }, (_, i) => Math.round(6000 * Math.sin(i * .14) + 1000 * Math.sin(i * .31)));
const workloads = [speech('chego', 8000), speech('vinni', 8000), speech('chego', 12000), speech('chego', 16000),
  { name: 'tone-1s', rate: 8000, pcm: tone(8000), source: { generator: 'round(6000*sin(i*.14)+1000*sin(i*.31))' } },
  { name: 'silence-2s', rate: 8000, pcm: new Int16Array(16000), source: { generator: 'zeros' } },
  { name: 'tone-long', rate: 8000, pcm: tone(65537), source: { generator: 'round(6000*sin(i*.14)+1000*sin(i*.31))' } }];
const warmups = 2, rounds = 5, rows = [];
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
for (const work of workloads) for (const profile of [4, 6]) {
  const expected = encoders.baseline(work.pcm, work.rate, profile);
  const actual = encoders.optimized(work.pcm, work.rate, profile);
  assert.deepEqual(actual, expected);
  const expectedPcm = decode(expected).pcm;
  assert.deepEqual(decode(actual).pcm, expectedPcm);
  const runs = { baseline: [], optimized: [] };
  for (let round = -warmups; round < rounds; round++) {
    for (const name of (round & 1 ? ['optimized', 'baseline'] : ['baseline', 'optimized'])) {
      const start = performance.now();
      const bytes = encoders[name](work.pcm, work.rate, profile);
      const elapsed = performance.now() - start;
      assert.deepEqual(bytes, expected, `${work.name} P${profile} ${name} round ${round}`);
      if (round >= 0) runs[name].push(elapsed);
    }
  }
  const times = Object.fromEntries(Object.entries(runs).map(([name, values]) => [name, median(values)]));
  const row = { workload: work.name, profile, rate: work.rate, samples: work.pcm.length,
    duration_s: work.pcm.length / work.rate, source: work.source,
    input_pcm_sha256: hash(Buffer.from(work.pcm.buffer)), lpx_sha256: hash(expected),
    decoded_pcm_sha256: hash(Buffer.from(expectedPcm.buffer)), median_ms: times, runs_ms: runs,
    speedup: times.baseline / times.optimized };
  rows.push(row);
  console.log(`${work.name} P${profile}/${work.rate}: ${times.baseline.toFixed(2)} → ${times.optimized.toFixed(2)} ms (${row.speedup.toFixed(2)}x), exact LPX/PCM`);
}
const result = { schema: 'micromusic-lpx-encoder-benchmark-v1',
  method: 'Whole synchronous createEncoder call, including reserve/input copy, analysis, search, packing, complete shared-C decode/model validation and output copy. Byte assertions and external decode are outside timing. Two warmups then five alternating-order paired runs; medians and all raw runs. Sequential local Node/V8 execution, not an in-browser/device/IRQ timing claim.',
  measuredAt: new Date().toISOString(), node: process.version, v8: process.versions.v8, platform: process.platform,
  arch: process.arch, cpu: cpus()[0].model, warmups, rounds,
  ffmpeg: execFileSync('ffmpeg', ['-version'], { encoding: 'utf8' }).split(/\r?\n/)[0],
  baseline: { revision, sha256: hash(baseline), bytes: baseline.length },
  optimized: { sha256: hash(candidate), bytes: candidate.length, compiler: manifest.compiler,
    flags: manifest.flags, inputs: manifest.inputs }, rows };
const output = resolve(root, values.output || 'build/lpx-encoder-benchmark.json');
mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, JSON.stringify(result, null, 2) + '\n');
console.log(`Wrote ${rows.length} byte-exact benchmark cases to ${output}`);
