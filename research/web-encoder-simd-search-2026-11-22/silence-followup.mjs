// Bounded repeat of the noisy silent cases; run from any cwd after building.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';
import { createEncoder } from '../../web-player/lpx/encoder.js';
const root = fileURLToPath(new URL('../../', import.meta.url));
const scalar = execFileSync('git', ['show', '19bc7455:web-player/lpx/encoder.wasm'], { cwd: root });
const simd = readFileSync(new URL('../../web-player/lpx/encoder-simd.wasm', import.meta.url));
const binaries = { scalar, simd }, pcm = new Int16Array(16000), rows = [];
const median = values => [...values].sort((a, b) => a - b)[values.length >> 1];
for (const profile of [4, 6]) {
  const encoders = { scalar: await createEncoder(scalar), simd: await createEncoder(simd) };
  const expected = encoders.scalar(pcm, 8000, profile), warm = { scalar: [], simd: [] }, cold = { scalar: [], simd: [] };
  for (let round = -2; round < 15; round++) for (const name of (round & 1 ? ['simd', 'scalar'] : ['scalar', 'simd'])) {
    const start = performance.now(), bytes = encoders[name](pcm, 8000, profile), elapsed = performance.now() - start;
    assert.deepEqual(bytes, expected); if (round >= 0) warm[name].push(elapsed);
  }
  for (let round = 0; round < 7; round++) for (const name of (round & 1 ? ['simd', 'scalar'] : ['scalar', 'simd'])) {
    const encode = await createEncoder(binaries[name]);
    const start = performance.now(), bytes = encode(pcm, 8000, profile), elapsed = performance.now() - start;
    assert.deepEqual(bytes, expected); cold[name].push(elapsed);
  }
  const row = { profile, samples: pcm.length, rate: 8000, warm_runs_ms: warm, first_encode_runs_ms: cold,
    warm_median_ms: { scalar: median(warm.scalar), simd: median(warm.simd) },
    first_encode_median_ms: { scalar: median(cold.scalar), simd: median(cold.simd) } };
  rows.push(row); console.log(JSON.stringify(row));
}
writeFileSync(new URL('silence-followup.json', import.meta.url), JSON.stringify({ measuredAt: new Date().toISOString(), node: process.version,
  method: '2 warmups + 15 alternating warm pairs, then 7 alternating fresh-instance first-encode pairs; instantiation outside timing, shared C validation and copy inside; exact bytes asserted every call.',
  binary_sha256: Object.fromEntries(Object.entries(binaries).map(([name, bytes]) => [name, createHash('sha256').update(bytes).digest('hex')])), rows }, null, 2) + '\n');
