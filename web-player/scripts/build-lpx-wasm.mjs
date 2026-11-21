import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { createHash } from 'node:crypto';

const { values } = parseArgs({ options: { emsdk: { type: 'string' }, clang: { type: 'string' } } });
const root = fileURLToPath(new URL('../../', import.meta.url));
const sdk = values.emsdk || process.env.EMSDK;
if (!sdk) throw new Error('Pass --emsdk <SDK directory> or set EMSDK. The SDK is read only.');
const upstream = join(resolve(sdk), 'upstream');
const compiler = values.clang || join(upstream, 'bin', process.platform === 'win32' ? 'clang.exe' : 'clang');
const sysroot = join(upstream, 'emscripten/cache/sysroot');
const sources = ['Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp', 'web-player/lpx/native/decoder.cpp'];
const exports = ['lpx_input', 'lpx_output', 'lpx_samples', 'lpx_rate', 'lpx_decode'];
const flags = ['--target=wasm32-unknown-unknown', '-O3', '-std=c++11', '-ffreestanding', '-nostdlib',
  '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics', '--sysroot=' + sysroot,
  '-isystem', join(sysroot, 'include'), '-ICodecs/LPX/01_ACTIVE_Q0_CODEC/src',
  '-DLPX4_ENABLE_ASM=0', '-DLPX4_FLOAT_SYNTHESIS=0', '-DLPX4_ENABLE_SPEECH=1',
  '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_COMPACT_ONLY=1', '-DLPX4_COMPACT_VERSION=9',
  '-DLPX4_SAMPLE_RATE=0', '-DLPX4_EXTENDED_SAMPLE_RATES=1',
  '-Wl,--no-entry', '-Wl,--export-memory', '-Wl,--initial-memory=262144', '-Wl,--max-memory=262144',
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
const inputs = [...sources, 'web-player/scripts/build-lpx-wasm.mjs',
  ...['Lpx4HybridCore.h', 'Lpx4Math.h', 'Lpx4MemoryProfiles.h', 'Lpx4MultiplyC.h', 'cos_table.inc', 'scale_table.inc']
    .map(name => 'Codecs/LPX/01_ACTIVE_Q0_CODEC/src/' + name)];
const manifest = { schema: 'micromusic-lpx-v9-wasm-v1', compiler: run(['--version']).split(/\r?\n/)[0],
  flags: flags.map(flag => flag.replaceAll(sysroot, '<emsdk>/upstream/emscripten/cache/sysroot')),
  inputs: Object.fromEntries(inputs.map(path => [path, hash(readFileSync(join(root, path), 'utf8').replaceAll('\r\n', '\n'))])),
  bytes: binary.length, sha256: hash(binary), imports: [], memoryBytes: 262144,
  output: 'PCM16', rates: [8000, 12000, 16000], profiles: [4, 6, 15] };
writeFileSync(join(root, 'web-player/lpx/build.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`LPX V9 C → WebAssembly: ${binary.length} bytes, no host imports`);

const encoderSources = ['Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp', 'web-player/lpx/native/encoder.cpp'];
const encoderExports = ['enc_input', 'enc_output', 'enc_begin', 'enc_step', 'enc_finish'];
const encoderFlags = flags.filter(flag => !flag.startsWith('-Wl,--export=') && !flag.startsWith('-Wl,--initial-memory=') && !flag.startsWith('-Wl,--max-memory='));
encoderFlags.push('-Wl,--initial-memory=2097152', '-Wl,--max-memory=2097152', ...encoderExports.map(name => '-Wl,--export=' + name));
const encoderOutput = join(root, 'web-player/lpx/encoder.wasm');
run([...encoderFlags, ...encoderSources, '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-lc', '-lclang_rt.builtins', '-o', encoderOutput]);
const encoderBinary = readFileSync(encoderOutput);
if (WebAssembly.Module.imports(await WebAssembly.compile(encoderBinary)).length) throw new Error('Encoder must have no host imports');
const encoderInputs = [...new Set([...inputs.filter(path => !path.endsWith('native/decoder.cpp')), 'web-player/lpx/native/encoder.cpp',
  ...['speech_v4.py', 'wav_lpc.py', 'q0_model.py', 'speech_v9.py', 'speech_compact.py'].map(name => 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/' + name)])];
writeFileSync(join(root, 'web-player/lpx/encoder-build.json'), JSON.stringify({ ...manifest,
  flags: encoderFlags.map(flag => flag.replaceAll(sysroot, '<emsdk>/upstream/emscripten/cache/sysroot')),
  inputs: Object.fromEntries(encoderInputs.map(path => [path, hash(readFileSync(join(root, path), 'utf8').replaceAll('\r\n', '\n'))])),
  schema: 'micromusic-lpx-v9-encoder-wasm-v1', bytes: encoderBinary.length, sha256: hash(encoderBinary), memoryBytes: 2097152,
  profiles: [4, 6], output: 'LPX V9', algorithm: 'speech_v4 scalar closed-loop search, browser C++ port' }, null, 2) + '\n');
console.log(`LPX V9 encoder C → WebAssembly: ${encoderBinary.length} bytes, no host imports`);
