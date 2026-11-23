// Local-only corpus driver. Media, fingerprints and per-case rows stay ignored.
import { readFileSync, writeFileSync, mkdirSync, lstatSync } from 'node:fs';
import { spawnSync, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { resolve, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import assert from 'node:assert/strict';
import { createDecoder } from '../lpx/codec.js';

const { values } = parseArgs({ options: {
  encoder: { type: 'string' }, manifest: { type: 'string' }, output: { type: 'string' },
  quality: { type: 'string', default: 'fast' }, limit: { type: 'string' },
  repeat: { type: 'string', default: '3' }, profile: { type: 'string' }, cases: { type: 'string' }
} });
if (!values.encoder || !values.manifest) throw new Error('Pass --encoder <CUDA executable> --manifest <local private corpus manifest>.');
if (!['fast', 'adaptive'].includes(values.quality)) throw new Error('Quality must be fast or adaptive.');
const repeats = Number(values.repeat), limit = values.limit ? Number(values.limit) : Infinity;
if (!Number.isInteger(repeats) || repeats < 1 || repeats > 20 || !(limit > 0)) throw new Error('Invalid repeat/limit.');
const profiles = values.profile ? [Number(values.profile)] : [4, 6];
if (profiles.some(x => x !== 4 && x !== 6)) throw new Error('Profile must be 4 or 6.');
const root = fileURLToPath(new URL('../../', import.meta.url));
const output = resolve(root, values.output || `build/lpx-cuda-${values.quality}.private.json`);
const build = resolve(root, 'build');
if (!output.startsWith(build + sep)) throw new Error('Private benchmark output must stay in this checkout’s ignored build directory.');
function checkPrivateOutput() {
  // Includes the output file itself: an existing file symlink must not redirect
  // media fingerprints into a tracked folder or outside this checkout.
  for (let path = output; path !== dirname(build); path = dirname(path)) {
    if (lstatSync(path, { throwIfNoEntry: false })?.isSymbolicLink()) throw new Error('Do not write private corpus reports through symbolic links or junctions.');
  }
}
checkPrivateOutput();
mkdirSync(dirname(output), { recursive: true });
const executable = resolve(values.encoder), manifestPath = resolve(values.manifest), folder = dirname(manifestPath);
const manifest = JSON.parse(readFileSync(manifestPath));
if (manifest.schema !== 'lpx-private-encoding-corpus-v1') throw new Error('Expected prepared private corpus.');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const decode = await createDecoder(readFileSync(new URL('../lpx/decoder.wasm', import.meta.url)));
const selected = values.cases ? values.cases.split(',').map(Number) : null;
if (selected?.some(x => !Number.isInteger(x) || x < 0 || x >= manifest.cases.length)) throw new Error('Invalid anonymous case indices.');
const cases = manifest.cases.map((input, ordinal) => ({ input, ordinal }))
  .filter(x => !selected || selected.includes(x.ordinal)).slice(0, limit), rows = [];
const gpu = execFileSync('nvidia-smi', ['--query-gpu=name,compute_cap,driver_version,memory.total', '--format=csv,noheader'], { encoding: 'utf8' }).trim();
const saved = { schema: 'lpx-cuda-private-benchmark-v1', quality: values.quality,
  executableSha256: hash(readFileSync(executable)), gpu, rows };
const median = a => [...a].sort((x, y) => x-y)[Math.floor(a.length/2)];
for (let index = 0; index < cases.length; ++index) {
  const { input, ordinal } = cases[index], path = resolve(folder, input.pcm.path);
  if (!path.startsWith(folder + sep) || input.pcm.format !== 's16le' || input.pcm.sampleRate !== 8000) throw new Error('Invalid prepared PCM path/format.');
  const pcm = readFileSync(path);
  assert.equal(pcm.length, input.pcm.samples*2); assert.equal(hash(pcm), input.pcm.sha256);
  for (const profile of profiles) {
    const runs = {}, bytes = {}, wall = {};
    const repeat = input.pcm.samples <= 64000 ? repeats : 1;
    // Alternate process order by case; CLI keeps the CUDA context between its
    // repeats and verifies all repeated output bytes before writing stdout.
    for (const backend of (index & 1 ? ['cuda', 'cpu'] : ['cpu', 'cuda'])) {
      const started = performance.now();
      const result = spawnSync(executable, ['--backend', backend, '--profile', String(profile),
        '--rate', '8000', '--quality', values.quality, '--repeat', String(repeat),
        ...(values.quality === 'adaptive' && input.kind !== 'speech' ? ['--non-speech'] : [])],
      { input: pcm, maxBuffer: 120*1024*1024, windowsHide: true });
      wall[backend] = performance.now()-started;
      if (result.error) throw result.error;
      if (result.status !== 0) throw new Error(`${backend} failed at anonymous case ${index}: ${result.stderr?.toString().slice(0, 1000)}`);
      const lines = result.stderr.toString().trim().split(/\r?\n/);
      runs[backend] = JSON.parse(lines.at(-1)); bytes[backend] = result.stdout;
    }
    assert.deepEqual(bytes.cuda, bytes.cpu, `CPU/CUDA stream mismatch at anonymous case ${index} P${profile}`);
    const decoded = decode(bytes.cpu);
    assert.equal(decoded.samples, input.pcm.samples);
    const row = { ordinal, profile, samples: input.pcm.samples, cohort: input.cohort,
      language: input.language, kind: input.kind, repeat, bytes: bytes.cpu.length,
      streamSha256: hash(bytes.cpu), pcmSha256: hash(pcm), exact: true, wallMs: wall, runs };
    rows.push(row); checkPrivateOutput(); writeFileSync(output, JSON.stringify(saved, null, 2)+'\n');
    console.log(JSON.stringify({ case: index+1, total: cases.length, profile, samples: input.pcm.samples,
      exact: true, bytes: bytes.cpu.length, cpuWallMs: Math.round(wall.cpu), cudaWallMs: Math.round(wall.cuda) }));
  }
}
console.log(JSON.stringify({ completed: rows.length, allExact: rows.every(x => x.exact),
  medianColdWallRatio: median(rows.map(x => x.wallMs.cpu/x.wallMs.cuda)),
  scope: 'Cold process wall ratio includes CUDA initialization; inspect CLI times separately. Private per-case report remains local.' }));
