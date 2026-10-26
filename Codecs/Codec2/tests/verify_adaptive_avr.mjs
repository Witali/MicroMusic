// Full mode-3200 with explicit fixed inverse FFT; same physical ATmega64A limits, no IRQ.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = resolve(root, '../../build/codec2/adaptive');
const target = join(build, 'atmega64a');
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
assert.ok(!symbols.has('pow') && !symbols.has('powf'), 'General power routine must not be linked');
for (const name of ['malloc', 'calloc', 'realloc', 'free']) assert.ok(!symbols.has(name), `Unexpected heap dependency ${name}`);
for (const [name, bytes] of [['compact_twiddle', 2048], ['compact_super', 1024], ['compact_window', 640], ['fixed_sine', 258], ['weight_twiddle', 2048], ['weight_super', 1024], ['fifth_value', 5*((1<<meta.root_precision.table_bits)+1)*(meta.root_precision.q<=15?2:3)], ['fifth_curve', 10*(1<<meta.root_precision.table_bits)]]) {
  assert.ok(symbols.has(name));
  assert.ok(symbols.get(name) + bytes <= 65536 && symbols.get(name) < 0x800000, `${name} must reside in near Flash`);
}
const base = memory.RAMSTART, top = address('__stack'), end = address('__bss_end');
assert.equal(top, memory.RAMEND);
const status = address('codec2_decode_status'), command = address('codec2_decode_command');
const result = address('codec2_decode_result'), packet = address('codec2_decode_packet'), pcm = address('codec2_decode_pcm');
const at = process.argv.indexOf('--frames');
const limit = at < 0 ? Infinity : Number(process.argv[at + 1]);
assert.ok(limit > 0);
const results = [];
for (const reference of meta.streams.filter(s => s.name !== 'all-11333')) {
  const name=reference.name;
  const source = readFileSync(reference.packet_path ? join(build, reference.packet_path) : join(root, 'AVR/Codec2_Tiny13_Quality_R2/tests', name));
  const expected = readFileSync(join(build, name + '.upstream.pcm'));
  assert.equal(hash(source), reference.packet_sha256);
  assert.equal(hash(expected), reference.oracle_sha256);
  const program = new Uint16Array((memory.FLASHEND + 1) / 2).fill(0xffff);
  new Uint8Array(program.buffer).set(binary);
  const cpu = new CPU(program, top - base + 1);
  cpu.SP = top;
  let minimumSP = top;
  function until(predicate, budget = 500000000) {
    const deadline = cpu.cycles + budget;
    while (!predicate()) {
      assert.ok(cpu.cycles < deadline, `${name}: timeout at PC ${(cpu.pc * 2).toString(16)}`);
      avrInstruction(cpu); cpu.tick();
      assert.ok(cpu.SP >= end - 1 && cpu.SP <= top, `SRAM stack collision at PC ${(cpu.pc * 2).toString(16)}`);
      minimumSP = Math.min(minimumSP, cpu.SP);
    }
  }
  const started = Date.now();
  until(() => cpu.data[status] !== 0);
  assert.equal(cpu.data[status], 1);
  const initializationCycles = cpu.cycles;
  const stateBytes = cpu.dataView.getUint16(address('codec2_decode_state_bytes'), true);
  const frames = Math.min(limit, source.length / 8), output = Buffer.alloc(frames * 320);
  const cycles = [];
  for (let frame = 0; frame < frames; ++frame) {
    cpu.data.set(source.subarray(frame * 8, frame * 8 + 8), packet);
    cpu.data[status] = 1; cpu.data[command] = 1;
    const before = cpu.cycles;
    until(() => cpu.data[status] !== 1);
    assert.equal(cpu.data[status], 2, `${name}: decode failed at frame ${frame}, result=${cpu.data[result]}`);
    assert.equal(cpu.data[result], 0);
    cycles.push(cpu.cycles - before);
    output.set(cpu.data.subarray(pcm, pcm + 320), frame * 320);
    if ((frame + 1) % 25 === 0) console.log(`${name}: ${frame + 1}/${frames} adaptive-analysis frames`);
  }
  const oracle = expected.subarray(0, output.length);
  let signal = 0, noise = 0, maximum = 0, different = 0;
  for (let offset = 0; offset < output.length; offset += 2) {
    const value = output.readInt16LE(offset), original = oracle.readInt16LE(offset), error = value - original;
    signal += original * original; noise += error * error;
    maximum = Math.max(maximum, Math.abs(error)); different += error !== 0;
  }
  const snrDb = noise ? 10 * Math.log10(Math.max(1, signal) / noise) : null;
  const record = {name, frames, samples: frames * 160, completeStream: frames === source.length / 8,
    binarySha256: hash(binary), packetSha256: hash(source), outputSha256: hash(output), expectedSha256: hash(oracle),
    differentSamples: different, maxAbsoluteError: maximum, rmse: Math.sqrt(noise / (frames * 160)), snrDb,
    numericalGate: {minimumSnrDb: 50, maximumAbsoluteError: 256, absoluteQuantizationAllowance: 1},
    flashBytes: binary.length, staticSramBytes: end - base, stateBytes,
    stackBytes: top - minimumSP, freeSramAtPeak: minimumSP - end + 1,
    initializationCycles, maximumCycles: Math.max(...cycles), meanCycles: cycles.reduce((a, b) => a + b, 0) / frames,
    perFrameCycles: cycles, includesInterrupts: false, realtimeAt16MHz: Math.max(...cycles) <= 320000,
    hostRuntimeSeconds: (Date.now() - started) / 1000};
  console.log(JSON.stringify({...record, perFrameCycles: undefined}));
  writeFileSync(join(build, name + '.avr.pcm'), output);
  results.push(record);
  const passed=(snrDb === null || snrDb >= 50 || maximum <= 1) && maximum <= 256;
  if(!passed&&process.argv.includes('--record-failure')){
    const studyBytes=readFileSync(join(root,'reports/adaptive-precision.json'));
    assert.equal(hash(studyBytes),meta.precision_study_sha256);
    const study=JSON.parse(studyBytes),names=['tools/verify_adaptive.py','tests/verify_adaptive_avr.mjs','tests/compact_analysis_helpers.c','tests/upstream_decode.c','tools/verify_decoder.py','vendor/codec2-1.2.0/UPSTREAM.json'];
    const sources={...study.sources,...Object.fromEntries(names.map(n=>[n,hash(readFileSync(join(root,n)))]))};
    writeFileSync(join(root,'reports/adaptive-cold-failure.json'),JSON.stringify({...meta,sources,avr_execution:{simulator:'avr8js 0.21.1',mcu:'ATmega64A',hardwareMemory:memory,results,complete:false,numericalPassed:false},verified_at_utc:new Date().toISOString(),scope:'Native PCM passes; two-frame AVR prefix fails the independent conditioning sequence. Negative baseline, no complete AVR or real-time admission.'},null,2)+'\n');
  }
  assert.ok(passed, 'Fixed spectrum AVR numerical gate failed');
}
writeFileSync(join(build, 'avr-execution.json'), JSON.stringify({simulator: 'avr8js 0.21.1', mcu: 'ATmega64A',
  hardwareMemory: memory, results, complete: results.every(r => r.completeStream),
  scope: 'Hybrid full decode, integer main and weighted spectra, inverse FFT and postfilter power on 4-KB SRAM; no active-IRQ, hardware or real-time admission'}, null, 2) + '\n');
