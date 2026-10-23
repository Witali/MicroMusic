// Execute the linked AVR GCC machine code on an independent AVR8js CPU.
// No timers/ISR in this harness: frame cycles measure the decoder and mailbox.
import assert from 'node:assert/strict';
import {readFileSync, readdirSync, writeFileSync, mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = join(root, 'build/profile');
function option(name, fallback) {
  const i = process.argv.indexOf(name);
  return i < 0 ? fallback : resolve(process.argv[i+1]);
}
const streamsDirectory = option('--streams', join(root, 'reference/R4/data'));
const oracleDirectory = option('--oracle', join(root, 'build/reference'));
const outputDirectory = option('--out', build);
const capture = process.argv.includes('--capture');
mkdirSync(outputDirectory, {recursive: true});
const symbols = new Map(readFileSync(join(build, 'symbols.txt'), 'utf8').split(/\r?\n/)
  .map(line => line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean)
  .map(m => [m[2], parseInt(m[1], 16)]));
function address(name) {
  assert.ok(symbols.has(name), 'Missing symbol ' + name);
  return symbols.get(name) & 0xffff;
}
const status = address('speex_test_status'), command = address('speex_test_command');
const packet = address('speex_test_packet'), pcm = address('speex_test_pcm');
const result = address('speex_test_result'), end = address('__bss_end');
const binary = readFileSync(join(build, 'speex-test.bin'));
assert.equal(address('scratch') & 3, 0, '220-byte scratch requires a four-byte-aligned base');
for (const table of ['cdbk_nb', 'cdbk_nb_low1', 'cdbk_nb_high1', 'gain_cdbk_lbr', 'exc_10_32_table', 'nb3_gain_table']) {
  assert.ok(symbols.has(table) && symbols.get(table) < 32768, table + ' must reside in Flash');
}
for (const name of ['malloc', 'calloc', 'realloc', 'free']) assert.ok(!symbols.has(name), 'Unexpected heap: ' + name);
const profile = process.argv.includes('--profile');
const lspEntry=[...symbols].find(([name,value])=>/^lsp_to_lpc(?:\.|$)/.test(name)&&value<32768)?.[1];
assert.ok(lspEntry!==undefined,'Count the actual out-of-line LSP conversion entries');
const hits = new Map();
const functions = [...symbols].filter(([name, value]) => value < 0x800000 && name !== '__stack')
  .sort((a,b) => a[1]-b[1]);
assert.ok(binary.length <= 32768);
const limitIndex = process.argv.indexOf('--frames');
const limit = limitIndex < 0 ? Infinity : Number(process.argv[limitIndex + 1]);
const report = {simulator: 'avr8js 0.21.1', compiler: 'AVR GCC', mcu: 'ATmega328P',
  flashBytes: binary.length, staticSramBytes: end - 0x100,
  includesInterrupts: false, frames: 0, maxCycles: 0, minStackPointer: 0x8ff, streams: []};

for (const file of readdirSync(streamsDirectory).filter(s => s.endsWith('.spxraw')).sort()) {
  const program = new Uint16Array(16384).fill(0xffff);
  new Uint8Array(program.buffer).set(binary);
  const cpu = new CPU(program, 2048);
  let minSP = 0x8ff;
  let lspConversions = 0;
  function until(predicate, budget = 2000000) {
    const deadline = cpu.cycles + budget;
    while (!predicate()) {
      assert.ok(cpu.cycles < deadline, 'Firmware timeout at PC ' + (cpu.pc * 2).toString(16));
      const pc = cpu.pc * 2, before = cpu.cycles;
      if (pc===lspEntry) lspConversions++;
      avrInstruction(cpu);
      cpu.tick();
      if (profile) hits.set(pc, (hits.get(pc) || 0) + cpu.cycles - before);
      if (cpu.SP < minSP) minSP = cpu.SP;
      assert.ok(cpu.SP >= end, 'C stack collided with static SRAM');
    }
  }
  until(() => cpu.data[status] === 1);
  const raw = readFileSync(join(streamsDirectory, file));
  const expected = readFileSync(join(oracleDirectory, file.replace('.spxraw', '.pcm')));
  const frames = Math.min(raw.length / 20, limit), cycles = [];
  const captured = [];
  for (let frame = 0; frame < frames; frame++) {
    cpu.data.set(raw.subarray(frame * 20, frame * 20 + 20), packet);
    cpu.data[status] = 1;
    cpu.data[command] = 1;
    const start = cpu.cycles;
    until(() => cpu.data[status] === 2);
    assert.equal(cpu.data[result], 0, file + ': decode result');
    const actual = Buffer.from(cpu.data.subarray(pcm, pcm + 320));
    const oracle = expected.subarray(frame * 320, frame * 320 + 320);
    if (!actual.equals(oracle)) {
      const first = [...actual].findIndex((value, i) => value !== oracle[i]);
      throw new Error(`${file} frame ${frame}: PCM differs at sample ${first >> 1}: ` +
        `${actual.readInt16LE(first & ~1)} != ${oracle.readInt16LE(first & ~1)}`);
    }
    cycles.push(cpu.cycles - start);
    if (capture) captured.push(actual);
  }
  let resetVerified=false;
  if (process.argv.includes('--verify-reset')) {
    const before=lspConversions;
    cpu.data[status]=0;cpu.data[command]=2;
    until(()=>cpu.data[status]===1);
    cpu.data.set(raw.subarray(0,20),packet);cpu.data[command]=1;
    until(()=>cpu.data[status]===2);
    assert.equal(cpu.data[result],0,'Decode after reset');
    assert.ok(Buffer.from(cpu.data.subarray(pcm,pcm+320)).equals(expected.subarray(0,320)),
      'Reset must reproduce a fresh first frame despite previously cached LPC');
    assert.equal(lspConversions-before,1,'Reset computes the first LPC before reusing it');
    lspConversions=before;resetVerified=true;
  }
  const row = {stream: file, frames, minCycles: Math.min(...cycles),
    maxCycles: Math.max(...cycles), meanCycles: Math.round(cycles.reduce((a,b) => a+b, 0) / frames),
    stackBytes: 0x8ff - minSP, freeSramAtPeak: minSP - end + 1,
    lspConversions, lspCacheHits: frames*4-lspConversions, resetVerified};
  report.frames += frames;
  report.maxCycles = Math.max(report.maxCycles, row.maxCycles);
  report.minStackPointer = Math.min(report.minStackPointer, minSP);
  report.streams.push(row);
  if (capture) writeFileSync(join(outputDirectory, file.replace('.spxraw', '.pcm')), Buffer.concat(captured));
  console.log(file, JSON.stringify(row));
}
report.freeSramAtPeak = report.minStackPointer - end + 1;
report.fitsDecoderBudget = report.maxCycles <= 320000;
writeFileSync(resolve(outputDirectory, limit === Infinity ? 'avr-verification.json' : 'avr-smoke.json'), JSON.stringify(report, null, 2) + '\n');
console.log('PASS: AVR PCM exact;', report.frames, 'frames; max', report.maxCycles,
  'cycles;', report.freeSramAtPeak, 'bytes spare SRAM. ISR excluded.');
if (profile) {
  const totals = new Map();
  for (const [pc, cycles] of hits) {
    const fn = functions.findLast(([,address]) => address <= pc)?.[0];
    totals.set(fn, (totals.get(fn) || 0) + cycles);
  }
  console.log('Cycle profile:', [...totals].sort((a,b) => b[1]-a[1]).slice(0,15));
}
