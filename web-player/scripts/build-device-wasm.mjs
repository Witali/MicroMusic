// Build the connected ATtiny13A runtime without changing the legacy avr.wasm.
import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync} from 'node:fs';
import {dirname, join, parse, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';

const {values} = parseArgs({options: {
  emsdk: {type: 'string'}, clang: {type: 'string'}, 'out-dir': {type: 'string'},
}});
const root = fileURLToPath(new URL('../../', import.meta.url));
const definitionsCheck = spawnSync(process.execPath,
  [join(root, 'web-player/scripts/generate-attiny13a-registers.mjs'), '--check'],
  {cwd: root, encoding: 'utf8'});
if (definitionsCheck.error) throw definitionsCheck.error;
if (definitionsCheck.status !== 0) throw new Error(definitionsCheck.stderr || 'Official register map is stale');
const vendorRoot = 'web-player/vendor/microchip/ATtiny_DFP/3.4.278';
function recursiveFiles(folder) {
  return readdirSync(join(root, folder), {withFileTypes: true}).sort((a,b)=>a.name.localeCompare(b.name))
    .flatMap(entry => entry.isDirectory() ? recursiveFiles(folder + '/' + entry.name) : [folder + '/' + entry.name]);
}
const vendorInputs = recursiveFiles(vendorRoot);
const vendorProvenance = JSON.parse(readFileSync(join(root, vendorRoot, 'provenance.json'), 'utf8'));
let sdk = values.emsdk || process.env.EMSDK;
for (let parent = root; !sdk;) {
  const candidate = join(parent, 'build/toolchains/emscripten-6.0.12');
  if (existsSync(join(candidate, 'upstream/emscripten/cache/sysroot'))) sdk = candidate;
  if (parent === parse(parent).root) break;
  parent = dirname(parent);
}
if (!sdk) throw new Error('Set EMSDK or pass --emsdk <directory> with a prepared read-only SDK.');
sdk = resolve(sdk);
const compiler = values.clang || join(sdk, 'upstream/bin', process.platform === 'win32' ? 'clang.exe' : 'clang');
const sysroot = join(sdk, 'upstream/emscripten/cache/sysroot');
const output = resolve(values['out-dir'] || join(root, 'web-player/wasm'));
const peripheralDir = 'web-player/native/peripherals';
const isTest = name => /(?:^|[.\-_])tests?(?:[.\-_]|$)/i.test(name);
const nativeFiles = readdirSync(join(root, peripheralDir)).sort()
  .filter(name => /\.[ch]$/.test(name) && !isTest(name)).map(name => peripheralDir + '/' + name);
const sources = ['web-player/native/avr.c', ...nativeFiles.filter(name => name.endsWith('.c'))];
const runtimeSource = readFileSync(join(root, sources[0]), 'utf8');
const nativeSupport = readdirSync(join(root, 'web-player/native')).sort()
  .filter(name => /\.(?:h|inc)$/.test(name)).map(name => 'web-player/native/' + name);
const bridgeSource = [runtimeSource, ...nativeSupport.filter(name => name.endsWith('.inc'))
  .map(name => readFileSync(join(root, name), 'utf8'))].join('\n');
if (!runtimeSource.includes('AVR_FULL_DEVICE') || !nativeFiles.includes(peripheralDir + '/device.c')) {
  throw new Error('The connected AVR_FULL_DEVICE hooks and peripherals/device.c are required.');
}

// Keep the original AVR ABI and include every public avr_* bridge definition.
// Discovering definitions (not declarations/calls) prevents stale export lists
// when the full runtime adds board configuration and diagnostic bridges.
const originalExports = ['layout', 'field_name', 'error_message', 'reset', 'decode', 'decode_idle',
  'step', 'next', 'block', 'idle', 'clock', 'interrupt', 'write_io', 'update_timer', 'timer_mode',
  'push', 'pop', 'push_pc', 'pop_pc', 'nzvs', 'arithmetic', 'audio_init', 'audio_channels',
  'audio_controls', 'render', 'filter', 'average'].map(name => 'avr_' + name);
const publicDefinitions = [...bridgeSource.matchAll(
  /^\s*(?!static\b)(?:const\s+)?\w+[\s*]+(avr_\w+)\s*\([^;{}]*\)\s*\{/gm,
)].map(match => match[1]);
const requiredBridges = ['read_io', 'write_io_masked', 'device_configure', 'device_ready',
  'device_time', 'device_time64', 'device_control', 'device_lpm', 'device_wait',
  'device_generation', 'device_bind_generation', 'device_fault', 'device_inject_pins',
  'device_inject_analog', 'device_pin_buffer', 'device_pin_count', 'device_pin_consume',
  'device_divisor', 'device_reset_count', 'device_halted', 'device_audio_config',
  'device_audio_deadline', 'device_audio_sample'].map(name => 'avr_' + name);
for (const name of requiredBridges) {
  if (!publicDefinitions.includes(name)) throw new Error('Missing connected device bridge: ' + name);
}
const exports = [...new Set([...originalExports, ...publicDefinitions])].sort();
const flags = ['--target=wasm32-unknown-unknown', '-O3', '-std=c11', '-ffreestanding', '-nostdlib',
  '-DAVR_FULL_DEVICE', '--sysroot=' + sysroot, '-isystem', join(sysroot, 'include'),
  '-L' + join(sysroot, 'lib/wasm32-emscripten'), '-Wl,--no-entry', '-Wl,--export-memory',
  '-Wl,--initial-memory=131072', '-Wl,--max-memory=131072', '-Wl,-z,stack-size=8192',
  ...exports.map(name => '-Wl,--export=' + name)];
function run(args) {
  const result = spawnSync(compiler, args, {cwd: root, encoding: 'utf8'});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr || result.stdout || 'Compiler failed');
  return result.stdout;
}
mkdirSync(output, {recursive: true});
const pending = join(output, 'attiny13a.pending.wasm');
run([...flags, ...sources, '-lc', '-lclang_rt.builtins', '-o', pending]);
const binary = readFileSync(pending), module = await WebAssembly.compile(binary);
if (WebAssembly.Module.imports(module).length) throw new Error('ATtiny13A runtime must have no host imports');
const instance = new WebAssembly.Instance(module);
if (instance.exports.memory.buffer.byteLength !== 131072) throw new Error('ATtiny13A runtime requires exactly two memory pages');
try {
  instance.exports.memory.grow(1);
  throw new Error('ATtiny13A runtime memory must have a fixed maximum of two pages');
} catch (error) {
  if (!(error instanceof RangeError)) throw error;
}
const hash = value => createHash('sha256').update(value).digest('hex');
const inputs = [sources[0], ...nativeSupport, ...nativeFiles, ...vendorInputs,
  'web-player/scripts/generate-attiny13a-registers.mjs', 'web-player/scripts/build-device-wasm.mjs'];
const normalized = path => path.replaceAll(sdk, '<emsdk>').replaceAll(sdk.replaceAll('\\', '/'), '<emsdk>');
const manifest = {
  schema: 'micromusic-attiny13a-device-wasm-v1',
  compilerVersion: run(['--version']).split(/\r?\n/)[0],
  flags: flags.map(normalized),
  inputs: Object.fromEntries(inputs.map(path => [path,
    hash(readFileSync(join(root, path), 'utf8').replaceAll('\r\n', '\n'))])),
  sources, exports,
  vendorDefinitions: {provenance: vendorRoot + '/provenance.json',
    package: vendorProvenance.package, version: vendorProvenance.version,
    packageSha256: vendorProvenance.packageSha256,
    filesSha256: Object.fromEntries(vendorInputs.map(path => [path, hash(readFileSync(join(root, path)))]))},
  artifacts: {'attiny13a.wasm': hash(binary)},
  bytes: binary.length, memoryPages: 2, maximumMemoryPages: 2, stackBytes: 8192, imports: [],
};
renameSync(pending, join(output, 'attiny13a.wasm'));
writeFileSync(join(output, 'device-build.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Built import-free ATtiny13A device C/WASM: ${binary.length} bytes; ${sources.length} sources; ${exports.length} exports`);
