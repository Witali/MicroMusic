import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, join, parse} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../../', import.meta.url));
export function compileAnalog(name, sources, fixture, {fixedMemoryPages}={}) {
  // device.c owns the supply observer even when the selected fixture leaves it
  // disabled. Keep its linked dependency common to all standalone board tests.
  if(sources.includes('web-player/native/peripherals/device.c')&&!sources.includes('web-player/native/peripherals/power_reset.c'))
    sources=[...sources,'web-player/native/peripherals/power_reset.c'];
  if((sources.includes('web-player/native/peripherals/device.c')||fixture.includes('#include "device.c"'))&&
    !sources.includes('web-player/native/devices/attiny13a/reset_input.c'))
    sources=[...sources,'web-player/native/devices/attiny13a/reset_input.c'];
  let sdk = process.env.EMSDK;
  for (let p = root; !sdk;) {
    const candidate = join(p, 'build/toolchains/emscripten-6.0.12');
    if (existsSync(candidate)) sdk = candidate;
    if (p === parse(p).root) break;
    p = dirname(p);
  }
  assert.ok(sdk, 'Set EMSDK to a read-only Emscripten installation');
  const clang = join(sdk, 'upstream/bin', process.platform === 'win32' ? 'clang.exe' : 'clang');
  const sysroot = join(sdk, 'upstream/emscripten/cache/sysroot');
  const out = join(root, 'build/analog-tests');
  mkdirSync(out, {recursive: true});
  const dir = mkdtempSync(join(out, name + '-'));
  const c = join(dir, 'fixture.c'), wasm = join(dir, 'fixture.wasm');
  writeFileSync(c, fixture);
  assert.ok(fixedMemoryPages===undefined || (Number.isInteger(fixedMemoryPages)&&fixedMemoryPages>=1&&fixedMemoryPages<=256),
    'fixedMemoryPages must be1..256 when specified');
  const memoryFlags=fixedMemoryPages===undefined?[]:[
    '-Wl,--initial-memory='+fixedMemoryPages*65536,'-Wl,--max-memory='+fixedMemoryPages*65536,
    '-Wl,-z,stack-size=8192',
  ];
  const run = spawnSync(clang, ['--target=wasm32-unknown-unknown', '-O2', '-std=c11',
    '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-nostdlib', '--sysroot=' + sysroot,
    '-isystem', join(sysroot, 'include'), '-L' + join(sysroot, 'lib/wasm32-emscripten'),
    '-I', join(root, 'web-player/native/peripherals'), '-Wl,--no-entry',
    '-Wl,--export-all', '-Wl,--export-memory', ...memoryFlags, ...sources.map(s => join(root, s)), c,
    '-lc', '-lclang_rt.builtins', '-o', wasm], {encoding: 'utf8'});
  assert.equal(run.status, 0, run.stderr || String(run.error));
  const module = new WebAssembly.Module(readFileSync(wasm));
  assert.deepEqual(WebAssembly.Module.imports(module), [], 'Peripheral must not import the host');
  const instantiate=() => new WebAssembly.Instance(module).exports;
  Object.defineProperty(instantiate,'module',{value:module});
  return instantiate;
}
