import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url)), repo = resolve(here, '../../..');
export async function cReference({ defines = [], suffix = '' } = {}) {
  const common = execFileSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], { cwd: repo, encoding: 'utf8' }).trim();
  const roots = [repo, dirname(common)];
  const compiler = [process.env.MICROMUSIC_CLANG,
    ...roots.map(root => join(root, 'build/toolchains/emscripten-6.0.12/upstream/bin/clang.exe')),
    'clang'].filter(Boolean).find(path => path === 'clang' || existsSync(path));
  const output = join(repo, 'build/i8080-voice32');
  mkdirSync(output, { recursive: true });
  const wasm = join(output, `reference${suffix}.wasm`);
  const args = ['--target=wasm32-unknown-unknown', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
    '-nostdlib', '-Wl,--no-entry', '-Wl,--export-all', ...defines.map(value => '-D' + value),
    join(here, 'voice.c'), join(here, 'reference-driver.c'), '-o', wasm];
  execFileSync(compiler, args, { stdio: 'pipe' });
  const { instance } = await WebAssembly.instantiate(readFileSync(wasm));
  return { api: instance.exports, compiler, options: args.slice(0, 8) };
}
