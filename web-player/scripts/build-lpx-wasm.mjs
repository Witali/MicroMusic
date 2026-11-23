import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { createHash } from 'node:crypto';

const { values } = parseArgs({ options: { emsdk: { type: 'string' }, clang: { type: 'string' },
  'reference-encoder': { type: 'boolean', default: false },
  'prefix-selftest': { type: 'boolean', default: false },
  'analysis-selftest': { type: 'boolean', default: false },
  'simd-selftest': { type: 'boolean', default: false } } });
const root = fileURLToPath(new URL('../../', import.meta.url));
const sdk = values.emsdk || process.env.EMSDK;
if (!sdk) throw new Error('Pass --emsdk <SDK directory> or set EMSDK. The SDK is read only.');
const upstream = join(resolve(sdk), 'upstream');
const compiler = values.clang || join(upstream, 'bin', process.platform === 'win32' ? 'clang.exe' : 'clang');
const sysroot = join(upstream, 'emscripten/cache/sysroot');
const sources = ['Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp', 'web-player/lpx/native/decoder.cpp'];
const exports = ['lpx_reserve', 'lpx_input', 'lpx_output', 'lpx_samples', 'lpx_rate', 'lpx_decode'];
const flags = ['--target=wasm32-unknown-unknown', '-O3', '-std=c++11', '-ffreestanding', '-nostdlib',
  '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics', '--sysroot=' + sysroot,
  '-isystem', join(sysroot, 'include'), '-ICodecs/LPX/01_ACTIVE_Q0_CODEC/src',
  '-ICodecs/LPX/01_ACTIVE_Q0_CODEC/host', '-ffp-contract=off',
  '-DLPX4_ENABLE_ASM=0', '-DLPX4_FLOAT_SYNTHESIS=0', '-DLPX4_ENABLE_SPEECH=1',
  '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_COMPACT_ONLY=1', '-DLPX4_COMPACT_VERSION=9',
  '-DLPX4_SAMPLE_RATE=0', '-DLPX4_EXTENDED_SAMPLE_RATES=1', '-DLPX4_ENABLE_WIDE_V9=1',
  '-Wl,--no-entry', '-Wl,--export-memory', '-Wl,--initial-memory=262144', '-Wl,--max-memory=268435456',
  '-Wl,-z,stack-size=32768', '-Wl,--strip-all', ...exports.map(name => '-Wl,--export=' + name)];
function run(args) {
  const result = spawnSync(compiler, args, { cwd: root, encoding: 'utf8' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  return result.stdout;
}
const output = join(root, 'web-player/lpx/decoder.wasm');
run([...flags, ...sources, '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins', '-o', output]);
const binary = readFileSync(output);
const module = await WebAssembly.compile(binary);
if (WebAssembly.Module.imports(module).length) throw new Error('Decoder must have no host imports');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const inputs = [...sources, 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxHostWorkspace.h', 'web-player/scripts/build-lpx-wasm.mjs',
  ...['Lpx4HybridCore.h', 'Lpx4Math.h', 'Lpx4MemoryProfiles.h', 'Lpx4MultiplyC.h', 'cos_table.inc', 'scale_table.inc']
    .map(name => 'Codecs/LPX/01_ACTIVE_Q0_CODEC/src/' + name)];
const manifest = { schema: 'micromusic-lpx-v9-wasm-v1', compiler: run(['--version']).split(/\r?\n/)[0],
  flags: flags.map(flag => flag.replaceAll(sysroot, '<emsdk>/upstream/emscripten/cache/sysroot')),
  inputs: Object.fromEntries(inputs.map(path => [path, hash(readFileSync(join(root, path), 'utf8').replaceAll('\r\n', '\n'))])),
  bytes: binary.length, sha256: hash(binary), imports: [], initialMemoryBytes: 262144, maxMemoryBytes: 268435456,
  maxSamples: 32000000, wideV9: true,
  output: 'PCM16', rates: [8000, 12000, 16000], profiles: [4, 6, 15] };
writeFileSync(join(root, 'web-player/lpx/build.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`LPX V9 C → WebAssembly: ${binary.length} bytes, no host imports`);

const encoderSources = ['Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp', 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxEncoder.cpp'];
const encoderExports = ['enc_reserve', 'enc_input', 'enc_output', 'enc_begin', 'enc_step', 'enc_finish'];
const encoderFlags = flags.filter(flag => !flag.startsWith('-Wl,--export=') && !flag.startsWith('-Wl,--initial-memory=') && !flag.startsWith('-Wl,--max-memory='));
encoderFlags.push('-Wl,--initial-memory=262144', '-Wl,--max-memory=1073741824', ...encoderExports.map(name => '-Wl,--export=' + name));
const encoderOutput = join(root, 'web-player/lpx/encoder.wasm');
run([...encoderFlags, ...encoderSources, '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins', '-o', encoderOutput]);
const encoderBinary = readFileSync(encoderOutput);
if (WebAssembly.Module.imports(await WebAssembly.compile(encoderBinary)).length) throw new Error('Encoder must have no host imports');
const encoderInputs = [...new Set([...inputs.filter(path => !path.endsWith('native/decoder.cpp')), ...encoderSources,
  'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxEncoder.h', 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxEncoderSimd.h',
  'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxSeed.h',
  ...['speech_v4.py', 'wav_lpc.py', 'q0_model.py', 'speech_v9.py', 'speech_compact.py'].map(name => 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/' + name)])];
writeFileSync(join(root, 'web-player/lpx/encoder-build.json'), JSON.stringify({ ...manifest,
  flags: encoderFlags.map(flag => flag.replaceAll(sysroot, '<emsdk>/upstream/emscripten/cache/sysroot')),
  inputs: Object.fromEntries(encoderInputs.map(path => [path, hash(readFileSync(join(root, path), 'utf8').replaceAll('\r\n', '\n'))])),
  schema: 'micromusic-lpx-v9-encoder-wasm-v1', bytes: encoderBinary.length, sha256: hash(encoderBinary), maxMemoryBytes: 1073741824,
  profiles: [4, 6], output: 'LPX V9', algorithm: 'speech_v4 closed-loop search, shared native/WASM C++ core',
  searchOptimizations: { nonnegativeLossPruning: true, duplicateCandidates: true, commonPrefixes: true, exactSilentBlocks: true },
  analysisOptimizations: { exactGridCache: true, cacheBytes: 112816 } }, null, 2) + '\n');
console.log(`LPX V9 encoder C → WebAssembly: ${encoderBinary.length} bytes, no host imports`);

if (values['reference-encoder']) {
  mkdirSync(join(root, 'build'), { recursive: true });
  const referenceOutput = join(root, 'build/lpx-encoder-exhaustive.wasm');
  run([...encoderFlags, '-DLPX_ENCODER_ENABLE_PRUNING=0', '-DLPX_ENCODER_DEDUP_CANDIDATES=0', '-DLPX_ENCODER_REUSE_PREFIX=0', '-DLPX_ENCODER_FAST_SILENCE=0', '-DLPX_ENCODER_CACHE_ANALYSIS=0',
    ...encoderSources, '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins', '-o', referenceOutput]);
  console.log('Exhaustive C encoder oracle: build/lpx-encoder-exhaustive.wasm');
}

if (values['prefix-selftest']) {
  mkdirSync(join(root, 'build'), { recursive: true });
  run([...encoderFlags, '-Wl,--export=lpx_prefix_selftest', encoderSources[0],
    'web-player/tests/helpers/lpx-prefix-selftest.cpp',
    '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins',
    '-o', join(root, 'build/lpx-prefix-selftest.wasm')]);
  console.log('Pulse prefix state/loss/bound self-test: build/lpx-prefix-selftest.wasm');
}

if (values['analysis-selftest']) {
  mkdirSync(join(root, 'build'), { recursive: true });
  run([...encoderFlags, '-Wl,--export=lpx_silence_selftest', '-Wl,--export=lpx_analysis_selftest', encoderSources[0],
    'web-player/tests/helpers/lpx-analysis-selftest.cpp',
    '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins',
    '-o', join(root, 'build/lpx-analysis-selftest.wasm')]);
  console.log('Analysis/silent-block self-test: build/lpx-analysis-selftest.wasm');
}

const simdFlags = [...encoderFlags, '-msimd128', '-DLPX_ENCODER_SIMD_SEARCH=1'];
{
  const simdOutput = join(root, 'web-player/lpx/encoder-simd.wasm');
  run([...simdFlags, ...encoderSources, '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins', '-o', simdOutput]);
  const simdBinary = readFileSync(simdOutput);
  if (WebAssembly.Module.imports(await WebAssembly.compile(simdBinary)).length) throw new Error('SIMD encoder must have no host imports');
  const scalarManifest = JSON.parse(readFileSync(join(root, 'web-player/lpx/encoder-build.json')));
  writeFileSync(join(root, 'web-player/lpx/encoder-simd-build.json'), JSON.stringify({ ...scalarManifest,
    flags: simdFlags.map(flag => flag.replaceAll(sysroot, '<emsdk>/upstream/emscripten/cache/sysroot')),
    bytes: simdBinary.length, sha256: hash(simdBinary), backend: 'wasm-simd128-pulse4' }, null, 2) + '\n');
  console.log(`LPX V9 four-candidate SIMD encoder: ${simdBinary.length} bytes, no host imports`);
}
if (values['simd-selftest']) {
  mkdirSync(join(root, 'build'), { recursive: true });
  run([...simdFlags, '-Wl,--export=lpx_simd_selftest', encoderSources[0], 'web-player/tests/helpers/lpx-simd-selftest.cpp',
    '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins', '-o', join(root, 'build/lpx-simd-selftest.wasm')]);
  console.log('Four-candidate SIMD self-test: build/lpx-simd-selftest.wasm');
}

// Same adaptive C++ translation units as the offline native executable.
// Python source files below are provenance/test oracles, not runtime imports.
const adaptiveNames = ['LpxAdaptiveDsp.cpp', 'LpxQuality.cpp', 'LpxStoi.cpp',
  'LpxRefinement.cpp', 'LpxAdaptiveController.cpp', 'LpxAdaptiveApi.cpp', 'LpxWasmMemory.cpp'];
const adaptiveSources = adaptiveNames.map(name => 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/' + name);
const adaptiveExports = ['enc_adaptive', 'enc_adaptive_output', 'enc_adaptive_candidates', 'enc_adaptive_stages', 'enc_adaptive_gain'];
const adaptiveFlags = ['-isystem', join(sysroot, 'include/c++/v1'),
  ...encoderFlags.filter(flag => !flag.startsWith('-Wl,-z,stack-size=') && !flag.startsWith('-Wl,--initial-memory='))];
adaptiveFlags.push('-Wl,--initial-memory=524288', '-Wl,-z,stack-size=262144', '-DLPX_ADAPTIVE_ENCODER=1',
  ...adaptiveExports.map(name => '-Wl,--export=' + name));
const adaptiveInputs = [...new Set([...encoderInputs, ...adaptiveSources,
  ...['LpxAdaptive.h', 'LpxQuality.h', 'LpxRefinement.h', 'LpxAdaptiveController.h',
    'stoi-resample.inc', 'LICENSE-pystoi.txt'].map(name => 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/' + name),
  ...['adaptive_speech_voice.py', 'encode_speech_voice.py', 'refine_speech_compact.py', 'enhance_speech_compact.py',
    'refine_speech_lpc.py', 'refine_speech_extras.py', 'speech_rate_allocation.py', 'speech_voice_objective.py',
    'speech_noise_objective.py', 'voice_character.py', 'standard_metrics.py', 'voice_input.py']
    .map(name => 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/' + name)])];
for (const simd of [false, true]) {
  const name = simd ? 'encoder-adaptive-simd' : 'encoder-adaptive';
  const buildFlags = [...adaptiveFlags, ...(simd ? ['-msimd128', '-DLPX_ENCODER_SIMD_SEARCH=1'] : [])];
  run([...buildFlags, ...encoderSources, ...adaptiveSources,
    '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc++-noexcept', '-lc++abi-noexcept', '-lc', '-lclang_rt.builtins',
    '-o', join(root, `web-player/lpx/${name}.wasm`)]);
  const bytes = readFileSync(join(root, `web-player/lpx/${name}.wasm`));
  if (WebAssembly.Module.imports(await WebAssembly.compile(bytes)).length) throw new Error('Adaptive encoder must have no host imports');
  const parent = JSON.parse(readFileSync(join(root, 'web-player/lpx/encoder-build.json')));
  writeFileSync(join(root, `web-player/lpx/${name}-build.json`), JSON.stringify({ ...parent,
    schema: 'micromusic-lpx-v9-adaptive-wasm-v1',
    flags: buildFlags.map(flag => flag.replaceAll(sysroot, '<emsdk>/upstream/emscripten/cache/sysroot')),
    inputs: Object.fromEntries(adaptiveInputs.map(path => [path, hash(readFileSync(join(root, path), 'utf8').replaceAll('\r\n', '\n'))])),
    bytes: bytes.length, sha256: hash(bytes), initialMemoryBytes: 524288, stackBytes: 262144, backend: simd ? 'wasm-simd128-pulse4' : 'scalar',
    algorithm: 'shared C++ adaptive voice controller; Python-free runtime',
    quality: { seedPre: [0, 8192, 13926], refinementCalls: 4, lpcPreset: 'expanded',
      headerTrials: 256, headerFinalists: 16, extraHorizon: 320, extraFinalists: 6,
      extraFullEvaluations: 128, ranking: 'mean of PCM16/PWM voice + noise',
      budget: 'actual complete v5 control bytes, before lossless V9 repacking', levelPolicy: 'preserve' }
  }, null, 2) + '\n');
  console.log(`LPX V9 adaptive ${simd ? 'SIMD' : 'C++'}: ${bytes.length} bytes, no Python or host imports`);
}
