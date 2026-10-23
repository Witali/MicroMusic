import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join, resolve} from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
let sdk = process.env.EMSDK;
if (!sdk) {
  for (let folder = root; ; folder = dirname(folder)) {
    const candidate = join(folder, 'build/toolchains/emscripten-6.0.12');
    if (existsSync(candidate)) { sdk = candidate; break; }
    if (folder === dirname(folder)) break;
  }
}
if (!sdk) throw new Error('Set EMSDK to the read-only Emscripten SDK to compile Timer0 tests.');
const compiler = join(resolve(sdk), 'upstream/bin', process.platform === 'win32' ? 'clang.exe' : 'clang');
const sysroot = join(resolve(sdk), 'upstream/emscripten/cache/sysroot');
const output = join(root, 'build/tests/timer0');
mkdirSync(output, {recursive: true});
const wasm = join(output, 'timer0-test.wasm');
const build = spawnSync(compiler, [
  '--target=wasm32-unknown-unknown', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
  '-ffreestanding', '-nostdlib', '--sysroot=' + sysroot,
  '-isystem', join(sysroot, 'include'), '-L' + join(sysroot, 'lib/wasm32-emscripten'),
  '-Wl,--no-entry', '-Wl,--export=timer0_test_case', '-Wl,--export-memory',
  '-Wl,-z,stack-size=8192', 'web-player/native/peripherals/timer0.c',
  'web-player/native/peripherals/timer0-test.c', '-lc', '-lclang_rt.builtins', '-o', wasm,
], {cwd: root, encoding: 'utf8'});
if (build.error) throw build.error;
assert.equal(build.status, 0, build.stderr || build.stdout);
const module = await WebAssembly.compile(readFileSync(wasm));
assert.deepEqual(WebAssembly.Module.imports(module), [], 'Timer0 must have no host/JavaScript imports');
const {exports} = await WebAssembly.instantiate(module);
const cases = [
  'ATtiny13A register addresses and reserved-bit masks',
  'normal count, delayed compare, overflow, IRQ and TCNT write blocking',
  'CTC TOP, compare timing, missed lowered TOP and blocked clear',
  'free-running prescaler, all clock taps, PSR10/TSM, PRR and clkI/O gates',
  'fast PWM channels, inversion, exact TOP buffering and extreme duties',
  'OCR0A variable TOP, toggle output, buffered period change and TOP=0',
  'phase-correct PWM fixed/variable TOP, direction, extremes and buffering',
  'forced compare, output mux, preserved latches and FOC strobes',
  'synchronized external T0 edges, selected polarity and clock gates',
  'bounded batch output capture, same-cycle coalescing and explicit overflow',
  'event jumps match one-clock stepping through 9000 random scenarios',
  'event deadlines, >2^32 timestamps, UINT64 boundary and reserved modes',
];
cases.forEach((name, index) => test(name, () => {
  assert.equal(exports.timer0_test_case(index), 0, `timer0-test.c fixture failed (return value is its line number)`);
}));
