// Existing public human speech, reset per clip; exact previously qualified images.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = resolve(root, '../../build/codec2/existing-speech');
const meta = JSON.parse(readFileSync(join(build, 'host-verification.json'), 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
assert.equal(hash(readFileSync(join(root, 'fixtures/existing-speech.json'))), meta.fixture_sha256);
assert.deepEqual(meta.profiles.map(p => p.name), ['matrix', 'nopost']);
const results = [];
for (const profile of meta.profiles) {
  assert.deepEqual(profile.streams.map(s => s.name), ['balloon', 'owl', 'chego', 'otvechaesh']);
  const folder = join(build, profile.name), memory = profile.avr_image.manufacturer_header_memory;
  const binary = readFileSync(join(folder, 'decoder.bin'));
  const symbolsText = readFileSync(join(folder, 'symbols.txt'));
  assert.equal(hash(binary), profile.avr_image.binary_sha256);
  assert.equal(hash(symbolsText), profile.avr_image.symbols_sha256);
  assert.ok(binary.length <= memory.FLASHEND + 1);
  const symbols = new Map(symbolsText.toString().split(/\r?\n/)
    .map(s => s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m => [m[2], parseInt(m[1], 16)]));
  const address = name => {assert.ok(symbols.has(name), name); return symbols.get(name) & 0xffff;};
  for (const name of ['malloc', 'calloc', 'realloc', 'free']) assert.ok(!symbols.has(name));
  const base = memory.RAMSTART, top = address('__stack'), end = address('__bss_end');
  assert.equal(top, memory.RAMEND);
  const status = address('codec2_decode_status'), command = address('codec2_decode_command');
  const result = address('codec2_decode_result'), packet = address('codec2_decode_packet'), pcm = address('codec2_decode_pcm');
  for (const stream of profile.streams) {
    const name = stream.name, source = readFileSync(join(build, name + '.packets'));
    const expected = readFileSync(join(folder, name + '.upstream.pcm'));
    assert.equal(hash(source), stream.packet_sha256);
    assert.equal(hash(expected), stream.oracle_sha256);
    assert.equal(source.length, stream.frames * 8);
    assert.equal(expected.length, stream.frames * 320);
    const program = new Uint16Array((memory.FLASHEND + 1) / 2).fill(0xffff);
    new Uint8Array(program.buffer).set(binary);
    const cpu = new CPU(program, top - base + 1); cpu.SP = top;
    let minimumSP = top;
    function until(predicate) {
      const deadline = cpu.cycles + 500000000;
      while (!predicate()) {
        assert.ok(cpu.cycles < deadline, `${profile.name}/${name}: execution timeout`);
        avrInstruction(cpu); cpu.tick();
        assert.ok(cpu.SP >= end - 1 && cpu.SP <= top, 'SRAM collision');
        minimumSP = Math.min(minimumSP, cpu.SP);
      }
    }
    const started = Date.now(); until(() => cpu.data[status] !== 0);
    assert.equal(cpu.data[status], 1);
    const output = Buffer.alloc(expected.length), cycles = [];
    for (let frame = 0; frame < stream.frames; ++frame) {
      cpu.data.set(source.subarray(frame * 8, frame * 8 + 8), packet);
      cpu.data[status] = 1; cpu.data[command] = 1;
      const before = cpu.cycles; until(() => cpu.data[status] !== 1);
      assert.equal(cpu.data[status], 2); assert.equal(cpu.data[result], 0);
      cycles.push(cpu.cycles - before); output.set(cpu.data.subarray(pcm, pcm + 320), frame * 320);
      if ((frame + 1) % 50 === 0) console.log(`${profile.name}/${name}: ${frame + 1}/${stream.frames}`);
    }
    let signal = 0, noise = 0, maximum = 0, different = 0;
    for (let i = 0; i < output.length; i += 2) {
      const original = expected.readInt16LE(i), error = output.readInt16LE(i) - original;
      signal += original * original; noise += error * error;
      maximum = Math.max(maximum, Math.abs(error)); different += error !== 0;
    }
    const snrDb = noise ? 10 * Math.log10(Math.max(1, signal) / noise) : null;
    const record = {profile: profile.name, name, frames: stream.frames, completeStream: true,
      binarySha256: hash(binary), packetSha256: hash(source), outputSha256: hash(output), expectedSha256: hash(expected),
      snrDb, maxAbsoluteError: maximum, differentSamples: different, rmse: Math.sqrt(noise / (output.length / 2)),
      numericalGate: {minimumSnrDb: 50, maximumAbsoluteError: 256, absoluteQuantizationAllowance: 1},
      flashBytes: binary.length, staticSramBytes: end - base, stackBytes: top - minimumSP,
      freeSramAtPeak: minimumSP - end + 1, meanCycles: cycles.reduce((a, b) => a + b, 0) / cycles.length,
      maximumCycles: Math.max(...cycles), perFrameCycles: cycles, includesInterrupts: false,
      realtimeAt16MHz: Math.max(...cycles) <= 320000, hostRuntimeSeconds: (Date.now() - started) / 1000};
    writeFileSync(join(folder, name + '.avr.pcm'), output);
    results.push(record); console.log(JSON.stringify({...record, perFrameCycles: undefined}));
    assert.ok((snrDb === null || snrDb >= 50 || maximum <= 1) && maximum <= 256, 'Same-option upstream numerical gate');
  }
}
assert.equal(results.length, 8);
writeFileSync(join(build, 'avr-execution.json'), JSON.stringify({simulator: 'avr8js 0.21.1', mcu: 'ATmega64A',
  results, complete: results.every(r => r.completeStream),
  scope: 'Four complete existing human-speech clips, two previously verified images. No IRQ, hardware or real-time admission.'}, null, 2) + '\n');
