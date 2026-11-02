// Actual AVR instructions, SPI controller completion times, shared C flash
// model, GPIO chip-select and production timer/IRQ/PWM queue. No RAM packet feed.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join, resolve} from 'node:path';
import {CPU, avrInstruction, AVRTimer, timer1Config, timer2Config,
  AVRSPI, spiConfig, AVRIOPort, portBConfig} from 'avr8js';
import {tickAvr} from './avr_tick.mjs';
import {loadSpiModel} from './spi_model.mjs';

const dir = resolve(process.argv[2]), stream = resolve(process.argv[3]);
const oraclePath = resolve(process.argv[4]), modelPath = resolve(process.argv[5]);
const metadata = JSON.parse(readFileSync(join(dir, 'input.json')));
const pwmPin=metadata.pwmPin??9;assert.ok([3,9].includes(pwmPin));
const pwmAddress=pwmPin===3?timer2Config.OCRB:timer1Config.OCRA;
assert.equal(metadata.backend, 'asm');
const binary = readFileSync(join(dir, 'player.bin'));
const raw = readFileSync(stream), expected = readFileSync(oraclePath);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
assert.equal(hash(binary), metadata.binarySha256);
assert.equal(hash(raw), metadata.inputSha256);
assert.ok(binary.length <= 32768);
assert.equal(raw.length, metadata.streamBytes);
const frameSamples = metadata.wideband ? 320 : 160;
const period = metadata.wideband ? 1000 : 2000;
assert.equal(expected.length, metadata.frames * frameSamples * 2);
const symbols = new Map(readFileSync(join(dir, 'symbols.txt'), 'utf8').split(/\r?\n/)
  .map(line => line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean)
  .map(match => [match[2], parseInt(match[1], 16) & 65535]));
const address = name => { assert.ok(symbols.has(name), name); return symbols.get(name); };
const [started, done, error, underruns, head, tail, finished, frames, end] = [
  'speex_player_started', 'speex_player_done', 'speex_player_error', 'speex_player_underruns',
  'head', 'tail', 'input_finished', 'speex_spi_frames', '__bss_end'].map(address);
for (const name of ['sample_data', 'speex_embedded_player_unused_main', 'malloc', 'calloc', 'realloc', 'free'])
  assert.ok(!symbols.has(name), 'No embedded input, unused demo main or heap: ' + name);
const program = new Uint16Array(16384).fill(65535);
new Uint8Array(program.buffer).set(binary);
const cpu = new CPU(program, 2048);
const port = new AVRIOPort(cpu, portBConfig);
new AVRTimer(cpu, timer1Config);
new AVRTimer(cpu, timer2Config);
const spi = new AVRSPI(cpu, spiConfig, metadata.cpuHz);
const flash = await loadSpiModel(modelPath, raw, metadata.flashAddress);
let csHigh = true, bytesStarted = 0, bytesCompleted = 0, enabledTransfers = 0;
let wireCycles = 0, minCompletion = Infinity, maxCompletion = 0;
port.addListener(value => {
  if (!(cpu.data[portBConfig.DDR] & (1 << metadata.csBit))) return;
  const nextHigh = Boolean(value & (1 << metadata.csBit));
  if (csHigh === nextHigh) return;
  assert.equal(spi.transmissionActive, false, 'CS changes only between complete bytes');
  csHigh = nextHigh;
  flash.select(csHigh);
});
spi.onByte = value => {
  assert.equal(csHigh, false, 'Flash selected for every transfer');
  assert.ok(spi.isMaster);
  assert.equal(spi.spiMode, 0);
  assert.equal(spi.dataOrder, 'msbFirst');
  assert.equal(spi.spiFrequency, metadata.spiHz);
  assert.equal(spi.transferCycles, 16);
  assert.equal(cpu.data[portBConfig.DDR] & 0x3c, 0x2c, 'CS/MOSI/SCK output; MISO input');
  const begin = cpu.cycles, duration = spi.transferCycles;
  ++bytesStarted;
  if (cpu.interruptsEnabled) ++enabledTransfers;
  wireCycles += duration;
  cpu.addClockEvent(() => {
    assert.equal(csHigh, false);
    const elapsed = cpu.cycles - begin;
    assert.ok(elapsed >= duration && elapsed <= duration + 10, 'SPI completion scheduling');
    minCompletion = Math.min(minCompletion, elapsed);
    maxCompletion = Math.max(maxCompletion, elapsed);
    spi.completeTransfer(flash.transfer(value));
    ++bytesCompleted;
  }, duration);
};

const pwm = Buffer.alloc(expected.length / 2 + 1);
let outputs = 0, lastTime = 0, minInterval = Infinity, maxInterval = 0, minQueue = 127;
const previous = cpu.writeHooks[pwmAddress];
cpu.writeHooks[pwmAddress] = (value, old, at, mask) => {
  if (cpu.data[started]) {
    assert.ok(outputs < pwm.length, 'PWM output count');
    pwm[outputs++] = value;
    if (lastTime) {
      const gap = cpu.cycles - lastTime;
      minInterval = Math.min(minInterval, gap);
      maxInterval = Math.max(maxInterval, gap);
    }
    lastTime = cpu.cycles;
    if (!cpu.data[finished]) minQueue = Math.min(minQueue, (cpu.data[head] - cpu.data[tail]) & 127);
  }
  return previous?.(value, old, at, mask) ?? false;
};
const chunks = metadata.capturePcm ? address('speex_spi_chunks') : -1;
const count = metadata.capturePcm ? address('speex_spi_samples') : -1;
const pcm = metadata.capturePcm ? address('speex_spi_pcm') : -1;
let oldChunks = 0, pcmBytes = 0, minSP = 2303;
const deadline = metadata.frames * 320000 + 2000000;
try {
  while (!cpu.data[done]) {
    assert.ok(cpu.cycles < deadline, 'Continuous player deadline');
    const enabled = cpu.interruptsEnabled;
    avrInstruction(cpu);
    tickAvr(cpu, enabled);
    minSP = Math.min(minSP, cpu.SP);
    assert.ok(cpu.SP >= end, 'Static SRAM/stack collision');
    assert.equal(cpu.data[error], 0, 'Player error');
    assert.equal(cpu.dataView.getUint16(underruns, true), 0, 'PWM queue underrun');
    if (chunks >= 0 && cpu.data[chunks] !== oldChunks) {
      oldChunks = cpu.data[chunks];
      const samples = cpu.data[count];
      assert.equal(samples, metadata.wideband ? 80 : 160);
      const pointer = cpu.dataView.getUint16(pcm, true);
      const block = Buffer.from(cpu.data.subarray(pointer, pointer + 2 * samples));
      assert.ok(block.equals(expected.subarray(pcmBytes, pcmBytes + block.length)), 'Exact s16 at byte ' + pcmBytes);
      pcmBytes += block.length;
      if (pcmBytes % (frameSamples * 2 * 256) === 0) console.log('Decoded', pcmBytes / (frameSamples * 2), 'frames');
    }
  }
  assert.equal(cpu.dataView.getUint32(frames, true), metadata.frames);
  assert.equal(csHigh, true, 'Input closed before final drain');
  assert.equal(bytesStarted, bytesCompleted);
  assert.equal(bytesCompleted, raw.length + 5);
  assert.ok(enabledTransfers >= raw.length - metadata.packetBytes, 'SPI runs with interrupts enabled after prefill');
  if (metadata.capturePcm) assert.equal(pcmBytes, expected.length);
  assert.equal(outputs, pwm.length);
  assert.equal(pwm.at(-1), 128);
  const expectedPwm = Buffer.from(Array.from({length: expected.length / 2}, (_, i) => expected[2 * i + 1] ^ 128));
  assert.ok(pwm.subarray(0, -1).equals(expectedPwm), 'Entire PWM stream equals oracle');
  assert.ok(minInterval >= period - 10 && maxInterval <= period + 10, 'PCM timer/IRQ intervals');
  const stats = flash.stats();
  assert.equal(stats.transferCalls, raw.length + 5);
  assert.equal(stats.selectedBytes, raw.length + 5);
  assert.equal(stats.readBytes, raw.length);
  assert.equal(stats.commandBytes, 1);
  assert.equal(stats.addressBytes, 3);
  assert.equal(stats.dummyBytes, 1);
  assert.equal(stats.csAssertions, 1);
  assert.equal(stats.csDeassertions, 1);
  assert.equal(stats.unsupportedCommands, 0);
  assert.equal(stats.resets, 0);
  const result = {passed: true, simulator: 'avr8js 0.21.1 + tests/avr_tick.mjs + shared C W25Q128 model via WASM',
    physicalBoardTested: false, includesInterrupts: true, input: metadata,
    modelWasmSha256: hash(readFileSync(modelPath)), pcmSha256: hash(expected), pwmSha256: hash(pwm.subarray(0, -1)),
    fullHistoryWithoutReset: true, frames: metadata.frames, samples: expected.length / 2,
    s16Exact: metadata.capturePcm, pwmExact: true, underruns: 0, minQueuedSamplesBeforeOutput: minQueue,
    timerIntervalMinCycles: minInterval, timerIntervalMaxCycles: maxInterval,
    flashBytes: binary.length, staticSramBytes: end - 256, peakStackBytes: 2303 - minSP,
    freeSramAtPeak: minSP - end + 1, elapsedCycles: cpu.cycles, spiWireCycles: wireCycles,
    spiBytesWithInterruptsEnabled: enabledTransfers, spiCompletionMinCycles: minCompletion,
    spiCompletionMaxCycles: maxCompletion, modelStats: stats};
  writeFileSync(join(dir, 'verification.json'), JSON.stringify(result, null, 2) + '\n');
  console.log('PASS SPI player:', JSON.stringify(result));
} catch (errorThrown) {
  writeFileSync(join(dir, 'failure.json'), JSON.stringify({passed: false, reason: errorThrown.message,
    elapsedCycles: cpu.cycles, pwmOutputs: outputs, pcmBytes, bytesStarted, bytesCompleted,
    underruns: cpu.dataView.getUint16(underruns, true), freeSramAtPeak: minSP - end + 1,
    modelStats: flash.stats()}, null, 2) + '\n');
  throw errorThrown;
}
