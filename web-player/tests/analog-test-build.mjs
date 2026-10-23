import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, join, parse} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../../', import.meta.url));
export function compileAnalog(name, sources, fixture) {
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
  const run = spawnSync(clang, ['--target=wasm32-unknown-unknown', '-O2', '-std=c11',
    '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-nostdlib', '--sysroot=' + sysroot,
    '-isystem', join(sysroot, 'include'), '-L' + join(sysroot, 'lib/wasm32-emscripten'),
    '-I', join(root, 'web-player/native/peripherals'), '-Wl,--no-entry',
    '-Wl,--export-all', '-Wl,--export-memory', ...sources.map(s => join(root, s)), c,
    '-lc', '-lclang_rt.builtins', '-o', wasm], {encoding: 'utf8'});
  assert.equal(run.status, 0, run.stderr || String(run.error));
  const module = new WebAssembly.Module(readFileSync(wasm));
  assert.deepEqual(WebAssembly.Module.imports(module), [], 'Peripheral must not import the host');
  return () => new WebAssembly.Instance(module).exports;
}
