// Complete scalar float Codec2 decoder, linked for a real ATmega1284P memory map.
// No timer/peripheral playback. Report timing independently from correctness.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = resolve(root, '../../build/codec2/decoder');
const target = join(build, 'atmega1284p');
const meta = JSON.parse(readFileSync(join(build, 'host-verification.json'), 'utf8'));
const binary = readFileSync(join(target, 'decoder.bin'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
assert.equal(hash(binary), meta.avr_build.binary_sha256);
const memory = meta.avr_build.manufacturer_header_memory;
assert.ok(binary.length <= memory.FLASHEND + 1);
const symbols = new Map(readFileSync(join(target, 'symbols.txt'), 'utf8').split(/\r?\n/)
  .map(s => s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m => [m[2], parseInt(m[1], 16)]));
function address(name) {
  assert.ok(symbols.has(name), `Missing symbol ${name}`);
  return symbols.get(name) & 0xffff;
}
const base = memory.RAMSTART, top = address('__stack'), end = address('__bss_end');
assert.equal(top, memory.RAMEND);
const status = address('codec2_decode_status'), command = address('codec2_decode_command');
const result = address('codec2_decode_result'), packet = address('codec2_decode_packet');
const pcm = address('codec2_decode_pcm');
const dynamic = new Set(['malloc', 'calloc', 'realloc', 'free'].filter(n => symbols.has(n)).map(n => symbols.get(n)));
const framesAt = process.argv.indexOf('--frames');
const frameLimit = framesAt < 0 ? Infinity : Number(process.argv[framesAt + 1]);
assert.ok(frameLimit > 0);
const results = [];
for (const name of ['speech.c2zx', 'codec2_3200_8byte_frames.bin']) {
  const source = readFileSync(join(root, 'AVR/Codec2_Tiny13_Quality_R2/tests', name));
  const oracle = readFileSync(join(build, name + '.upstream.pcm'));
  const original = meta.streams.find(s => s.name === name);
  assert.equal(hash(source), original.packet_sha256);
  assert.equal(hash(oracle), original.oracle_sha256);
  const program = new Uint16Array((memory.FLASHEND + 1) / 2).fill(0xffff);
  new Uint8Array(program.buffer).set(binary);
  const cpu = new CPU(program, top - base + 1);
  cpu.SP = top;
  let minimumSP = top;
  function until(predicate, budget = 100000000) {
    const deadline = cpu.cycles + budget;
    while (!predicate()) {
      assert.ok(cpu.cycles < deadline, `${name}: timeout at byte PC ${(cpu.pc * 2).toString(16)}`);
      assert.ok(!dynamic.has(cpu.pc * 2), 'Unexpected heap function');
      avrInstruction(cpu); cpu.tick();
      assert.ok(cpu.SP >= end - 1 && cpu.SP <= top, 'Stack collision or invalid SP');
      minimumSP = Math.min(minimumSP, cpu.SP);
    }
  }
  const start = Date.now();
  until(() => cpu.data[status] !== 0);
  assert.equal(cpu.data[status], 1, 'Initialization failed');
  const initializationCycles = cpu.cycles;
  const stateBytes = cpu.dataView.getUint16(address('codec2_decode_state_bytes'), true);
  const fftBytes = cpu.dataView.getUint16(address('codec2_decode_fft_bytes'), true);
  const frames = Math.min(frameLimit, source.length / 8);
  const output = Buffer.alloc(frames * 320);
  const trace = symbols.has('codec2_decoder_trace') ? Buffer.alloc(frames * 512) : null;
  const nativeTrace = trace ? readFileSync(join(build, name + '.native-trace.bin')) : null;
  let maximumCycles = 0, totalCycles = 0;
  const perFrameCycles = [];
  for (let frame = 0; frame < frames; ++frame) {
    cpu.data.set(source.subarray(frame * 8, frame * 8 + 8), packet);
    cpu.data[status] = 1; cpu.data[command] = 1;
    const before = cpu.cycles;
    until(() => cpu.data[status] !== 1);
    assert.equal(cpu.data[status], 2, `Decode failed at ${frame}, result=${cpu.data[result]}`);
    assert.equal(cpu.data[result], 0);
    const cycles = cpu.cycles - before;
    maximumCycles = Math.max(maximumCycles, cycles); totalCycles += cycles;
    perFrameCycles.push(cycles);
    output.set(cpu.data.subarray(pcm, pcm + 320), frame * 320);
    if (trace) {
      trace.set(cpu.data.subarray(address('codec2_decoder_trace'), address('codec2_decoder_trace') + 512), frame * 512);
      writeFileSync(join(build, name + '.avr-trace.bin'), trace);
      for (let half = 0; half < 2; ++half) {
        const offset = frame * 512 + half * 256 + 240;
        assert.equal(trace.readUInt32LE(offset), nativeTrace.readUInt32LE(offset), `RNG divergence at frame ${frame}, half ${half}`);
      }
    }
    if ((frame + 1) % 25 === 0) console.log(`${name}: ${frame + 1}/${frames} frames`);
  }
  const expected = oracle.subarray(0, output.length);
  let signal = 0, noise = 0, maxError = 0, differentSamples = 0;
  for (let offset = 0; offset < output.length; offset += 2) {
    const value = output.readInt16LE(offset), reference = expected.readInt16LE(offset);
    const error = value - reference;
    signal += reference * reference; noise += error * error;
    maxError = Math.max(maxError, Math.abs(error)); differentSamples += error !== 0;
  }
  const snrDb = noise ? 10 * Math.log10(Math.max(1, signal) / noise) : null;
  const record = {name, frames, completeStream: frames === source.length / 8,
    samples: frames * 160, binarySha256: hash(binary), packetSha256: hash(source),
    outputSha256: hash(output), expectedSha256: hash(expected),
    differentSamples, maxAbsoluteError: maxError, rmse: Math.sqrt(noise / (frames * 160)), snrDb,
    numericalGate: {minimumSnrDb: 50, maximumAbsoluteError: 256, absoluteQuantizationAllowance: 1},
    flashBytes: binary.length, staticSramBytes: end - base, stateBytes, fftBytes,
    stackBytes: top - minimumSP, freeSramAtPeak: minimumSP - end + 1,
    initializationCycles, maximumCycles, meanCycles: totalCycles / frames,
    perFrameCycles, includesInterrupts: false, realtimeAt16MHz: maximumCycles <= 320000,
    hostRuntimeSeconds: (Date.now() - start) / 1000};
  console.log(JSON.stringify({...record, perFrameCycles: undefined}));
  writeFileSync(join(build, name + '.avr.pcm'), output);
  results.push(record);
  // Cross-compiler float/libm differences are qualified separately from the
  // native byte-identical oracle test. These bounds are fixed before tuning.
  assert.ok((snrDb === null || snrDb >= 50 || maxError <= 1) && maxError <= 256, 'AVR numeric qualification failed');
}
writeFileSync(join(build, 'avr-execution.json'), JSON.stringify({simulator: 'avr8js 0.21.1', mcu: 'ATmega1284P',
  hardwareMemory: memory, results, complete: results.every(r => r.completeStream),
  scope: 'Full waveform decode without timers or ISR; no hardware or real-time admission'}, null, 2) + '\n');
