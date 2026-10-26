// GNU-linked archived resonator baseline: execute code, not ASM source text.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = resolve(root, '../../build/codec2/frontend');
const directory = join(build, 'r2-baseline');
const legacy = join(root, 'AVR/Codec2_Tiny13_Quality_R2');
const binary = readFileSync(join(directory, 'r2.bin'));
const original = readFileSync(join(legacy, 'build/tiny13_quality_r2_demo.bin'));
const hash = b => createHash('sha256').update(b).digest('hex');
const evidence = JSON.parse(readFileSync(join(build, 'host-and-build.json'), 'utf8'));
assert.equal(hash(binary), evidence.r2_gnu.binary_sha256);
const symbols = new Map(readFileSync(join(directory, 'symbols.txt'), 'utf8').split(/\r?\n/)
  .map(s => s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m => [m[2], parseInt(m[1], 16)]));
function cpuFor(bytes) {
  const program = new Uint16Array(512).fill(0xffff);
  new Uint8Array(program.buffer).set(bytes);
  const cpu = new CPU(program, 64);
  cpu.SP = 0x9f;
  return cpu;
}
function until(cpu, predicate, budget = 100000) {
  const limit = cpu.cycles + budget;
  while (!predicate()) {
    assert.ok(cpu.cycles < limit, `Timeout at byte PC ${(cpu.pc * 2).toString(16)}`);
    avrInstruction(cpu); cpu.tick();
    assert.ok(cpu.SP <= 0x9f && cpu.SP >= 0x82, 'Baseline stack overlaps fixed 35-byte state');
  }
}
const expectedPacket = binary.subarray(symbols.get('demo_packet'), symbols.get('demo_packet') + 8);
const copied = [];
for (const bytes of [binary, original]) {
  const cpu = cpuFor(bytes);
  until(cpu, () => cpu.pc * 2 === symbols.get('codec2tiny_decode_frame'));
  copied.push(Buffer.from(cpu.data.subarray(0x60, 0x68)));
}
assert.deepEqual(copied[0], expectedPacket, 'GNU reset must copy the real packet to SRAM FRAME');
assert.notDeepEqual(copied[1], expectedPacket, 'Documented archived frame-copy defect changed');

function wavSamples(path) {
  const wav = readFileSync(path);
  assert.equal(wav.toString('ascii', 0, 4), 'RIFF');
  assert.equal(wav.toString('ascii', 8, 12), 'WAVE');
  let samples, valid = false;
  for (let at = 12; at + 8 <= wav.length;) {
    const size = wav.readUInt32LE(at + 4), name = wav.toString('ascii', at, at + 4);
    const chunk = wav.subarray(at + 8, at + 8 + size);
    if (name === 'fmt ') {
      assert.equal(chunk.readUInt16LE(0), 1); assert.equal(chunk.readUInt16LE(2), 1);
      assert.equal(chunk.readUInt32LE(4), 8000); assert.equal(chunk.readUInt16LE(14), 16);
      valid = true;
    }
    if (name === 'data') samples = chunk;
    at += 8 + size + (size & 1);
  }
  assert.ok(valid && samples);
  return samples;
}
const streams = [];
for (const name of ['speech.c2zx', 'codec2_3200_8byte_frames.bin']) {
  const packets = readFileSync(join(legacy, 'tests', name));
  const expected = wavSamples(join(legacy, 'audio', name + '.resonator_full.wav'));
  const cpu = cpuFor(binary);
  // A real RCALL at the end of unused test Flash provides hardware return semantics.
  const trampoline = 510, sentinel = 511;
  let worstSample = 0, worstDecode = 0;
  function call(name) {
    cpu.progMem[trampoline] = 0xd000 | (((symbols.get(name) / 2) - trampoline - 1) & 0xfff);
    cpu.pc = trampoline;
    const start = cpu.cycles;
    until(cpu, () => cpu.pc === sentinel);
    return cpu.cycles - start;
  }
  call('codec2tiny_init');
  assert.equal(expected.length, packets.length / 8 * 160 * 2);
  for (let frame = 0; frame < packets.length / 8; ++frame) {
    cpu.data.set(packets.subarray(frame * 8, frame * 8 + 8), 0x60);
    worstDecode = Math.max(worstDecode, call('codec2tiny_decode_frame'));
    for (let n = 0; n < 160; ++n) {
      worstSample = Math.max(worstSample, call('codec2tiny_sample'));
      const actual = (cpu.data[16] - 128) * 256;
      assert.equal(actual, expected.readInt16LE((frame * 160 + n) * 2), `${name}, frame ${frame}, sample ${n}`);
    }
  }
  streams.push({name, frames: packets.length / 8, samples: expected.length / 2,
    packetSha256: hash(packets), pcmSha256: hash(expected), mismatches: 0,
    worstSampleCyclesIncludingRcall: worstSample, worstDecodeCyclesIncludingRcall: worstDecode});
  console.log(JSON.stringify(streams.at(-1)));
}
writeFileSync(join(build, 'r2-machine-code.json'), JSON.stringify({simulator: 'avr8js 0.21.1',
  binarySha256: hash(binary), archivedBinarySha256: hash(original),
  reset: {expectedPacket: expectedPacket.toString('hex'), gnuCopied: copied[0].toString('hex'),
    archivedCopied: copied[1].toString('hex'), archivedDefect: 'LDI r26,0x00 at byte 0x20 instead of LDI r26,0x60'},
  streams, includesInterrupts: false, scope: 'Archived approximate resonator baseline; not full original Codec2 synthesis'}, null, 2) + '\n');
