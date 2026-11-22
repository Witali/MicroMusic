// Reproduce bounded SIMD/compact-prefix experiments without changing assets.
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const { values } = parseArgs({ options: { emsdk: { type: 'string' }, 'source-ref': { type: 'string' } } });
if (!values.emsdk) throw new Error('Pass --emsdk <read-only SDK>.');
const root = fileURLToPath(new URL('../../', import.meta.url));
const git = (...args) => execFileSync('git', args, { cwd: root });
const revision = git('rev-parse', '--verify', `${values['source-ref'] || 'HEAD'}^{commit}`).toString().trim();
const recorded = path => git('show', `${revision}:${path}`);
const sourcePath = 'web-player/lpx/native/encoder.cpp';
const source = recorded(sourcePath).toString().replaceAll('\r\n', '\n');
const manifest = JSON.parse(recorded('web-player/lpx/encoder-build.json'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
for (const [path, digest] of Object.entries(manifest.inputs)) {
  assert.equal(hash(readFileSync(join(root, path), 'utf8').replaceAll('\r\n', '\n')), digest, `Use a checkout matching ${revision}: ${path}`);
}
const sdk = resolve(values.emsdk), sysroot = join(sdk, 'upstream/emscripten/cache/sysroot');
const compiler = join(sdk, 'upstream/bin', process.platform === 'win32' ? 'clang.exe' : 'clang');
const flags = manifest.flags.map(flag => flag.replaceAll('<emsdk>/upstream/emscripten/cache/sysroot', sysroot));
const directory = 'build/lpx-backend-probes';
mkdirSync(join(root, directory), { recursive: true });
const replaceOnce = (text, before, after) => {
  assert.equal(text.split(before).length, 2, `Expected one source seam: ${before}`);
  return text.replace(before, after);
};
function compactPrefix(text) {
  text = replaceOnce(text, 'static State prefixState[20];',
    'struct PrefixState { int h[10], dd; };\nstatic PrefixState prefixState[20];\nstatic int prefixExcitation[20];');
  text = replaceOnce(text, '    out = reusePrefix ? prefixState[pos] : initial;', `    out = initial;
    if (reusePrefix) {
        memcpy(out.h, prefixState[pos].h, sizeof(out.h)); out.dd = prefixState[pos].dd;
        for (int j = 0; j < first; ++j) out.ring[(cursor + j) & 255] = prefixExcitation[j];
    }`);
  text = replaceOnce(text, 'if (recordPrefix) { prefixState[j] = out; prefixLoss[j] = loss; }',
    'if (recordPrefix) { memcpy(prefixState[j].h, out.h, sizeof(out.h)); prefixState[j].dd = out.dd; prefixLoss[j] = loss; }');
  text = replaceOnce(text, 'q = clip(q + (j == pos ? amp : 0), -32, 31); out.ring[at & 255] = q;',
    'q = clip(q + (j == pos ? amp : 0), -32, 31); out.ring[at & 255] = q;\n#if LPX_ENCODER_REUSE_PREFIX\n        if (recordPrefix) prefixExcitation[j] = q;\n#endif');
  return text;
}
function compile(extra, files, output) {
  const result = spawnSync(compiler, [...flags, ...extra, '-Iweb-player/lpx/native',
    'Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp', ...files,
    '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins', '-o', output],
    { cwd: root, encoding: 'utf8' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr);
}
for (const [name, text, extra] of [['control', source, []], ['simd', source, ['-msimd128']],
  ['compact-prefix', compactPrefix(source), []]]) {
  const cpp = `${directory}/${name}.cpp`, wasm = `${directory}/${name}.wasm`;
  writeFileSync(join(root, cpp), text);
  compile(extra, [cpp], wasm);
  const binary = readFileSync(join(root, wasm));
  assert.deepEqual(WebAssembly.Module.imports(await WebAssembly.compile(binary)), []);
  if (name === 'control') assert.equal(hash(binary), manifest.sha256, 'Control must reproduce the shipped scalar binary');
  writeFileSync(join(root, `${directory}/${name}-build.json`), JSON.stringify({ ...manifest,
    sha256: hash(binary), bytes: binary.length,
    flags: [...manifest.flags, ...extra, '-Iweb-player/lpx/native'],
    inputs: { ...manifest.inputs, [cpp]: hash(text), 'web-player/scripts/probe-lpx-backends.mjs': hash(readFileSync(fileURLToPath(import.meta.url), 'utf8').replaceAll('\r\n', '\n')) },
    experiment: { name, sourceRevision: revision, staticPrefixCacheBytes: name === 'compact-prefix' ? 1120 : 21520 }
  }, null, 2) + '\n');
  let harness = recorded('web-player/tests/helpers/lpx-prefix-selftest.cpp').toString();
  harness = replaceOnce(harness, '#include "../../lpx/native/encoder.cpp"', `#include "${name}.cpp"`);
  harness += '\n' + recorded('web-player/tests/helpers/lpx-analysis-selftest.cpp').toString().replace('#include "../../lpx/native/encoder.cpp"', '');
  const harnessCpp = `${directory}/${name}-selftest.cpp`, harnessWasm = `${directory}/${name}-selftest.wasm`;
  writeFileSync(join(root, harnessCpp), harness);
  compile([...extra, ...['lpx_prefix_selftest', 'lpx_silence_selftest', 'lpx_analysis_selftest'].map(name => '-Wl,--export=' + name)], [harnessCpp], harnessWasm);
  const { instance } = await WebAssembly.instantiate(readFileSync(join(root, harnessWasm)));
  assert.equal(instance.exports.lpx_prefix_selftest(), 918000, `${name} prefix state/bounds`);
  assert.equal(instance.exports.lpx_silence_selftest(), 48, `${name} silence state`);
  assert.equal(instance.exports.lpx_analysis_selftest(), 20768, `${name} analysis bits`);
  console.log(`${name}: ${binary.length} bytes, exact direct self-tests passed; ${wasm}`);
}
