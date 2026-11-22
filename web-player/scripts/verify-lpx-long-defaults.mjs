// Prove the disabled host extension leaves default AVR machine-code objects exact.
import { execFileSync, spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { parseArgs } from 'node:util';
const { values } = parseArgs({ options: { 'avr-root': { type: 'string' } } });
if (!values['avr-root']) throw new Error('Pass --avr-root <AVR toolchain directory>.');
const root = fileURLToPath(new URL('../../', import.meta.url));
const baseline = '8a2d2c7d399c409a3eda8d69869d56f41f17a946';
const source = 'Codecs/LPX/01_ACTIVE_Q0_CODEC/src';
const output = join(root, 'build/lpx-long-defaults'), before = join(output, 'before'), after = join(root, source);
mkdirSync(before, { recursive: true });
for (const name of readdirSync(after).filter(name => /\.(cpp|h|inc)$/.test(name))) {
  writeFileSync(join(before, name), execFileSync('git', ['show', `${baseline}:${source}/${name}`], { cwd: root, maxBuffer: 1024 * 1024 }));
}
const compiler = join(resolve(values['avr-root']), 'bin', process.platform === 'win32' ? 'avr-g++.exe' : 'avr-g++');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const flags = ['-Os', '-std=c++11', '-ffunction-sections', '-fdata-sections', '-DLPX4_ENABLE_SPEECH=1',
  '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_COMPACT_ONLY=1', '-DLPX4_COMPACT_VERSION=9'];
const cases = [];
for (const cpu of ['attiny88', 'atmega328p']) for (const memory of ['standard', 'sram512']) for (const asm of [0, 1]) for (const rate of [8000, 12000, 16000]) {
  const id = `${cpu}-${memory}-asm${asm}-${rate}`, digests = [];
  for (const [index, directory] of [before, after].entries()) {
    const object = join(output, `${id}-${index}.o`);
    const args = [...flags, '-mmcu=' + cpu, '-DLPX4_ENABLE_ASM=' + asm, '-DLPX4_SAMPLE_RATE=' + rate,
      ...(memory === 'sram512' ? ['-include', join(root, 'Codecs/LPX/01_ACTIVE_Q0_CODEC/profiles/Lpx4Sram512.h')] : []),
      '-I' + directory, '-c', join(directory, 'Lpx4HybridCore.cpp'), '-o', object];
    const result = spawnSync(compiler, args, { encoding: 'utf8' });
    if (result.error) throw result.error;
    if (result.status !== 0) throw new Error(result.stderr || 'AVR compilation failed');
    digests.push(hash(readFileSync(object)));
  }
  if (digests[0] !== digests[1]) throw new Error('Default object changed: ' + id);
  cases.push({ cpu, memory, asm, rate, before_sha256: digests[0], after_sha256: digests[1] });
}
const sources = {};
for (const name of ['Lpx4HybridCore.cpp', 'Lpx4HybridCore.h']) {
  const entry = bytes => ({ raw_sha256: hash(bytes), text_lf_sha256: hash(bytes.toString('utf8').replaceAll('\r\n', '\n')) });
  sources[`${source}/${name}`] = { baseline: entry(readFileSync(join(before, name))), current: entry(readFileSync(join(after, name))) };
}
const report = { schema: 'lpx-v9-long-host-transition-v1', baseline_revision: baseline,
  compiler: execFileSync(compiler, ['--version'], { encoding: 'utf8' }).split(/\r?\n/)[0], flags,
  scope: 'LPX4_ENABLE_WIDE_V9 defaults to zero; no new AVR IRQ or timing admission',
  complete: true, all_default_objects_exact: true, cases, sources };
const directory = join(root, 'Codecs/LPX/research/v9-long-host-2026-11-21'); mkdirSync(directory, { recursive: true });
writeFileSync(join(directory, 'source-transition.json'), JSON.stringify(report, null, 2) + '\n');
console.log(`${cases.length} default AVR C/ASM objects are byte-exact at all rates and both memory profiles.`);
