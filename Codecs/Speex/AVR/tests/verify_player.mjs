// Full player: AVR GCC code + both hardware timers + interrupt delivery.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join, resolve} from 'node:path';
import {CPU, avrInstruction, AVRTimer, timer1Config, timer2Config} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = join(root, 'build/player');
const metadata = JSON.parse(readFileSync(join(build, 'input.json')));
const input = process.argv[2] ? resolve(process.argv[2]) : join(root, 'reference/R4/data', metadata.file);
const raw = readFileSync(input);
assert.equal(createHash('sha256').update(raw).digest('hex'), metadata.sha256);
const oracleFile = join(build, 'reference.pcm');
execFileSync(join(root, 'build/reference', process.platform === 'win32' ? 'decode.exe' : 'decode'), [input, oracleFile]);
const oracle = readFileSync(oracleFile);
const expected = Buffer.from(Array.from({length: oracle.length / 2}, (_,i) => oracle[i*2+1] ^ 128));
const binary = readFileSync(join(build, 'speex-player.bin'));
assert.ok(binary.length <= 32768);
const symbols = new Map(readFileSync(join(build, 'symbols.txt'), 'utf8').split(/\r?\n/)
  .map(line => line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean)
  .map(m => [m[2], parseInt(m[1], 16)]));
function address(name) { assert.ok(symbols.has(name), name); return symbols.get(name) & 0xffff; }
const end = address('__bss_end'), started = address('speex_player_started');
const done = address('speex_player_done'), underruns = address('speex_player_underruns');
const head = address('head'), tail = address('tail');
const program = new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(binary);
const cpu = new CPU(program, 2048);
new AVRTimer(cpu, timer1Config);
new AVRTimer(cpu, timer2Config);
const samples = [], times = [], readyTimes = [];
let minQueued = 127;
const previousHead = cpu.writeHooks[head];
cpu.writeHooks[head] = (value, old, address, mask) => {
  if (cpu.data[started] && value !== old) readyTimes.push(cpu.cycles);
  return previousHead?.(value, old, address, mask) ?? false;
};
const previous = cpu.writeHooks[0x88]; // OCR1AL
cpu.writeHooks[0x88] = (value, old, address, mask) => {
  if (cpu.data[started]) {
    samples.push(value); times.push(cpu.cycles);
    // Exclude the intentional final drain after input is exhausted.
    if (!cpu.data[addressOfFinished]) minQueued = Math.min(minQueued, (cpu.data[head]-cpu.data[tail]) & 127);
  }
  return previous?.(value, old, address, mask) ?? false;
};
let minSP = 0x8ff;
const addressOfFinished = address('input_finished');
const deadline = metadata.frames * 320000 + 2000000;
while (!cpu.data[done]) {
  assert.ok(cpu.cycles < deadline, 'Player did not finish');
  avrInstruction(cpu);
  cpu.tick();
  minSP = Math.min(minSP, cpu.SP);
  assert.ok(cpu.SP >= end, 'Player stack collided with static SRAM');
}
assert.equal(cpu.data[address('speex_player_error')], 0);
assert.equal(cpu.dataView.getUint16(underruns, true), 0, 'PCM ring underrun');
assert.equal(samples.length, expected.length + 1, 'One timer output per sample plus final midpoint');
assert.equal(samples.at(-1), 128);
const output = Buffer.from(samples.slice(0,-1));
if (!output.equals(expected)) {
  const first = output.findIndex((value, i) => value !== expected[i]);
  throw new Error(`PWM differs from upstream at sample ${first}: ${output[first]} != ${expected[first]}`);
}
const gaps = times.slice(1).map((t,i) => t-times[i]);
const readyGaps = readyTimes.slice(1).map((t,i) => t-readyTimes[i]);
assert.ok(Math.min(...gaps) >= 1992 && Math.max(...gaps) <= 2008, 'Timer period / IRQ latency');
const report = {simulator: 'avr8js 0.21.1', input: metadata, frames: metadata.frames,
  samples: expected.length, cpuHz: 16000000, pcmHz: 8000, pwmHz: 62500,
  flashBytes: binary.length, staticSramBytes: end-0x100, peakStackBytes: 0x8ff-minSP,
  freeSramAtPeak: minSP-end+1, underruns: 0, timerIntervalMinCycles: Math.min(...gaps),
  timerIntervalMaxCycles: Math.max(...gaps), elapsedCycles: cpu.cycles,
  minQueuedSamplesBeforeOutput: minQueued,
  maxBlockReadyGapCycles: Math.max(0,...readyGaps),
  pwmSha256: createHash('sha256').update(output).digest('hex'), includesInterrupts: true,
  physicalBoardTested: false};
writeFileSync(join(build, 'player-verification.json'), JSON.stringify(report, null, 2) + '\n');
writeFileSync(join(build, 'player-pwm.u8'), output);
console.log('PASS: complete PWM player', JSON.stringify(report, null, 2));
