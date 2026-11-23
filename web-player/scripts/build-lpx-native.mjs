// Build the shared PC encoder without modifying or downloading any toolchain.
import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync, lstatSync } from 'node:fs';
import { join, resolve, relative, dirname, basename, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { createHash } from 'node:crypto';

const { values } = parseArgs({ options: {
  cuda: { type: 'boolean', default: false }, compiler: { type: 'string' },
  nvcc: { type: 'string' }, msvc: { type: 'string' }, arch: { type: 'string', default: 'sm_120' },
  output: { type: 'string' }
} });
const root = fileURLToPath(new URL('../../', import.meta.url));
const directory = resolve(root, values.output || 'build/lpx-native');
const build = resolve(root, 'build');
const outputRelative = relative(build, directory);
if (!outputRelative || isAbsolute(outputRelative) || outputRelative === '..' || outputRelative.startsWith('..\\') || outputRelative.startsWith('../')) throw new Error('Native output must be a subdirectory of this checkout’s build directory.');
for (let path = directory; path !== dirname(build); path = dirname(path)) {
  if (lstatSync(path, { throwIfNoEntry: false })?.isSymbolicLink()) throw new Error('Do not build through symbolic links.');
}
mkdirSync(directory, { recursive: true });
const src = 'Codecs/LPX/01_ACTIVE_Q0_CODEC';
const sources = [`${src}/src/Lpx4HybridCore.cpp`, ...['LpxEncoder.cpp', 'LpxAdaptiveDsp.cpp',
  'LpxQuality.cpp', 'LpxStoi.cpp', 'LpxRefinement.cpp', 'LpxAdaptiveController.cpp', 'encode_lpx.cpp']
  .map(name => `${src}/host/${name}`)];
const defines = ['LPX4_ENABLE_ASM=0', 'LPX4_FLOAT_SYNTHESIS=0', 'LPX4_ENABLE_SPEECH=1',
  'LPX4_ENABLE_SPEECH_COMPACT=1', 'LPX4_COMPACT_ONLY=1', 'LPX4_COMPACT_VERSION=9',
  'LPX4_SAMPLE_RATE=0', 'LPX4_EXTENDED_SAMPLE_RATES=1', 'LPX4_ENABLE_WIDE_V9=1'];
const includes = [`${src}/src`, `${src}/host`];
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const inputPaths = [...sources, ...['LpxEncoder.h', 'LpxSeed.h', 'LpxEncoderSimd.h', 'LpxAdaptive.h',
  'LpxQuality.h', 'LpxAdaptiveController.h', 'LpxRefinement.h', 'LpxHostWorkspace.h', 'stoi-resample.inc']
  .map(name => `${src}/host/${name}`), ...['Lpx4HybridCore.h', 'Lpx4Math.h', 'Lpx4MemoryProfiles.h',
  'Lpx4MultiplyC.h', 'cos_table.inc', 'scale_table.inc'].map(name => `${src}/src/${name}`),
  ...(values.cuda ? [`${src}/host/LpxCuda.h`, `${src}/host/cuda/LpxCuda.cu`] : []),
  'web-player/scripts/build-lpx-native.mjs'];
const inputHashes = Object.fromEntries(inputPaths.map(path => [path, hash(join(root, path))]));
function run(command, args, env = process.env, windowsVerbatimArguments = false) {
  const result = spawnSync(command, args, { cwd: root, env, encoding: 'utf8', windowsVerbatimArguments, maxBuffer: 8 * 1024 * 1024 });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error((result.stderr || result.stdout || 'Compiler failed').slice(0, 12000));
  return result.stdout + result.stderr;
}
function developerEnvironment() {
  let install = values.msvc || process.env.VSINSTALLDIR;
  if (!install) {
    const where = join(process.env['ProgramFiles(x86)'] || 'C:/Program Files (x86)', 'Microsoft Visual Studio/Installer/vswhere.exe');
    install = run(where, ['-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath']).trim();
  }
  if (!install) throw new Error('MSVC is not installed. Pass --msvc <Visual Studio directory> or use a C++ compiler in a developer prompt.');
  const setup = join(install, 'VC/Auxiliary/Build/vcvars64.bat');
  if (/["%!^&|<>\r\n]/.test(setup)) throw new Error('Invalid developer environment path.');
  // Read the environment in memory only; it may contain private inherited
  // variables and must never be printed or written into a build manifest.
  const output = run(process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', `call "${setup}" >nul && set`], process.env, true);
  const env = { ...process.env };
  for (const line of output.split(/\r?\n/)) {
    const at = line.indexOf('=');
    if (at > 0) env[line.slice(0, at)] = line.slice(at + 1);
  }
  return env;
}
const compiler = values.compiler || process.env.CXX || (process.platform === 'win32' ? 'clang++' : 'c++');
if (/^(?:cl|cl\.exe)$/i.test(basename(compiler))) throw new Error('Use Clang/clang-cl for the shared GNU-compatible host sources; MSVC supplies the ABI, CRT and linker.');
const msvc = /^(?:clang-cl|clang-cl\.exe)$/i.test(basename(compiler));
const env = process.platform === 'win32' ? developerEnvironment() : process.env;
const toolchains = { host: { compiler: basename(compiler), version: run(compiler, ['--version'], env).trim().split(/\r?\n/)[0] }, vendorHeaders: {} };
if (process.platform === 'win32') {
  toolchains.host.abi = 'Microsoft x64';
  toolchains.host.msvcToolset = env.VCToolsVersion?.trim() || null;
  toolchains.host.windowsSdk = env.WindowsSDKVersion?.replaceAll('\\', '').trim() || null;
  if (env.VCToolsInstallDir) for (const name of ['yvals_core.h', 'vcruntime.h']) {
    const path = join(env.VCToolsInstallDir, 'include', name);
    if (lstatSync(path, { throwIfNoEntry: false })?.isFile()) toolchains.vendorHeaders[`<msvc>/include/${name}`] = hash(path);
  }
}
const artifacts = [];
const cpuOutput = join(directory, process.platform === 'win32' ? 'lpx-encode.exe' : 'lpx-encode');
const cpuFlags = msvc
  ? ['/nologo', '/O2', '/EHsc', '/std:c++17', '/fp:strict', '/DNDEBUG', ...defines.map(x => '/D' + x), ...includes.map(x => '/I' + x)]
  : ['-O3', process.platform === 'win32' ? '-std=c++17' : '-std=c++11', '-ffp-contract=off', '-DNDEBUG', ...defines.map(x => '-D' + x), ...includes.map(x => '-I' + x)];
if (msvc) {
  const objects = join(directory, 'obj-cpu'); mkdirSync(objects, { recursive: true });
  run(compiler, [...cpuFlags, ...sources, '/Fo' + objects + '/', '/Fe' + cpuOutput], env);
} else run(compiler, [...cpuFlags, ...sources, '-o', cpuOutput], env);
artifacts.push({ backend: 'cpu', path: relative(root, cpuOutput), flags: cpuFlags });
if (values.cuda) {
  if (!/^sm_[0-9]+[a-z]?$/.test(values.arch)) throw new Error('CUDA architecture must use sm_### syntax.');
  const nvcc = values.nvcc || process.env.CUDACXX || 'nvcc';
  const nvccVersion = run(nvcc, ['--version'], env).trim().split(/\r?\n/);
  toolchains.cuda = { compiler: basename(nvcc), banner: nvccVersion[0], version: nvccVersion.find(line => line.includes('release ')) || null,
    documentation: 'https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/' };
  let nvccPath = nvcc;
  if (!isAbsolute(nvccPath)) {
    const located = run(process.platform === 'win32' ? 'where.exe' : 'which', [nvcc], env).trim().split(/\r?\n/)[0];
    if (located) nvccPath = located;
  }
  if (isAbsolute(nvccPath)) for (const name of ['cuda_runtime.h', 'cuda_runtime_api.h', 'driver_types.h']) {
    const path = join(dirname(dirname(nvccPath)), 'include', name);
    if (lstatSync(path, { throwIfNoEntry: false })?.isFile()) toolchains.vendorHeaders[`<cuda>/include/${name}`] = hash(path);
  }
  const output = join(directory, process.platform === 'win32' ? 'lpx-encode-cuda.exe' : 'lpx-encode-cuda');
  const flags = ['-O3', '-std=c++17', '--fmad=false', '-arch=' + values.arch,
    '-DLPX_ENCODER_ENABLE_CUDA=1', '-DNDEBUG', ...defines.map(x => '-D' + x), ...includes.map(x => '-I' + x),
    '-Xcompiler', process.platform === 'win32' ? '/fp:strict,/EHsc' : '-ffp-contract=off'];
  const objects = join(directory, 'obj-cuda'); mkdirSync(objects, { recursive: true });
  const objectPaths = [];
  for (const source of sources) {
    const object = join(objects, basename(source, '.cpp') + (process.platform === 'win32' ? '.obj' : '.o'));
    const args = msvc
      ? [...cpuFlags, '/DLPX_ENCODER_ENABLE_CUDA=1', '/c', source, '/Fo' + object]
      : [...cpuFlags, '-DLPX_ENCODER_ENABLE_CUDA=1', '-c', source, '-o', object];
    run(compiler, args, env); objectPaths.push(object);
  }
  // Clang emits shared host objects with the platform ABI. nvcc compiles only
  // the CUDA translation unit and links it with those same host sources.
  run(nvcc, [...flags, `${src}/host/cuda/LpxCuda.cu`, ...objectPaths, '-o', output], env);
  artifacts.push({ backend: 'cuda-and-explicit-cpu', path: relative(root, output), flags,
    hostFlags: [...cpuFlags, (msvc ? '/D' : '-D') + 'LPX_ENCODER_ENABLE_CUDA=1'] });
}
for (const [path, digest] of Object.entries(inputHashes)) if (hash(join(root, path)) !== digest) throw new Error('An input changed during the native build; rebuild before using its provenance.');
writeFileSync(join(directory, 'build.json'), JSON.stringify({ schema: 'lpx-native-build-v1',
  toolchains, inputs: inputHashes,
  artifacts: artifacts.map(artifact => ({ ...artifact, path: artifact.path.replaceAll('\\', '/'), sha256: hash(join(root, artifact.path)) }))
}, null, 2) + '\n');
for (const artifact of artifacts) console.log(`Built ${artifact.backend}: ${artifact.path}`);
