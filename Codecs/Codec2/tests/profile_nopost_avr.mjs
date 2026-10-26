// Source/inline instruction attribution on the byte-identical verified image.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import {CPU, avrInstruction} from 'avr8js';

const root = fileURLToPath(new URL('../', import.meta.url));
const build = resolve(root, '../../build/codec2/nopost-profile');
const hash = b => createHash('sha256').update(b).digest('hex');
const attribution = JSON.parse(readFileSync(join(build, 'attribution.json')));
const binary = readFileSync(join(build, 'decoder.bin'));
const symbolBytes = readFileSync(join(build, 'symbols.txt'));
assert.equal(hash(binary), attribution.binary_sha256);
assert.equal(hash(symbolBytes), attribution.symbols_sha256);
const baselineBytes = readFileSync(join(root, 'reports/nopost-decoder.json'));
const baseline = JSON.parse(baselineBytes);
const humanBytes = readFileSync(join(root, 'reports/existing-speech.json'));
const human = JSON.parse(humanBytes);
assert.equal(hash(binary), baseline.avr_build.binary_sha256);
const fixtureBytes = readFileSync(join(root, 'fixtures/existing-speech.json'));
assert.equal(hash(fixtureBytes), human.fixture_sha256);
const fixture = JSON.parse(fixtureBytes);
const at = process.argv.indexOf('--frames');
const windowFrames = at < 0 ? 20 : Number(process.argv[at + 1]);
assert.ok(Number.isInteger(windowFrames) && windowFrames > 0);
const entries = symbolBytes.toString().split(/\r?\n/).map(s => s.match(/^([0-9a-f]+)\s+(\w)\s+(.+)$/)).filter(Boolean)
  .map(m => ({name: m[3], at: parseInt(m[1], 16), type: m[2]}));
const symbols = new Map(entries.map(e => [e.name, e.at]));
const counts = new Map();
for (const e of entries.filter(e => /[tT]/.test(e.type))) counts.set(e.name, (counts.get(e.name) ?? 0) + 1);
const code = entries.filter(e => /[tT]/.test(e.type)).map(e => ({...e, name: counts.get(e.name) > 1 ? e.name + '@' + e.at.toString(16) : e.name})).sort((a, b) => a.at - b.at);
const functionByPC = new Uint16Array((baseline.avr_build.manufacturer_header_memory.FLASHEND + 1) / 2);
let which = 0;
for (let pc = 0; pc < functionByPC.length; ++pc) {
  while (which + 1 < code.length && code[which + 1].at <= pc * 2) ++which;
  functionByPC[pc] = which;
}
const address = name => {assert.ok(symbols.has(name), name); return symbols.get(name) & 0xffff;};
const cases = [];
for (const clip of fixture.clips) {
  const wav = readFileSync(join(root, clip.source_8k_wav));
  assert.equal(hash(wav), clip.source_8k_wav_sha256);
  let pcm;
  for (let p = 12; p + 8 <= wav.length;) {
    const length = wav.readUInt32LE(p + 4);
    if (wav.toString('ascii', p, p + 4) === 'data') pcm = wav.subarray(p + 8, p + 8 + length);
    p += 8 + length + (length & 1);
  }
  assert.equal(hash(pcm), clip.input_pcm_sha256);
  const energies = Array.from({length: clip.frames}, (_, frame) => {
    let sum = 0; for (let i = frame * 160; i < (frame + 1) * 160; ++i) sum += pcm.readInt16LE(i * 2) ** 2; return sum;
  });
  const frames = Math.min(windowFrames, clip.frames);
  let sum = energies.slice(0, frames).reduce((a, b) => a + b, 0), maximum = sum, start = 0;
  for (let i = 1; i <= energies.length - frames; ++i) {
    sum += energies[i + frames - 1] - energies[i - 1];
    if (sum > maximum) {maximum = sum; start = i;}
  }
  const record = human.avr_execution.results.find(r => r.profile === 'nopost' && r.name === clip.id);
  assert.ok(record.completeStream);
  cases.push({name: clip.id, start, frames, record,
    packetPath: resolve(root, '../../build/codec2/existing-speech', clip.id + '.packets'),
    expectedPath: resolve(root, '../../build/codec2/existing-speech/nopost', clip.id + '.avr.pcm'),
    selection: 'Maximum-energy contiguous source-PCM window; prior frames replayed with profiling disabled.'});
}
const cold = baseline.avr_execution.results.find(r => r.name === 'conditioning-stress');
const coldInput = baseline.streams.find(r => r.name === cold.name);
cases.push({name: cold.name, start: 0, frames: cold.frames, record: cold,
  packetPath: resolve(root, '../../build/codec2/nopost', coldInput.packet_path),
  expectedPath: resolve(root, '../../build/codec2/nopost', cold.name + '.avr.pcm'), selection: 'Entire existing extreme/transition regression.'});
const memory = baseline.avr_build.manufacturer_header_memory, top = address('__stack'), end = address('__bss_end');
assert.equal(top, memory.RAMEND);
const stageMap = attribution.stage_by_word_pc, results = [];
for (const test of cases) {
  const source = readFileSync(test.packetPath), expected = readFileSync(test.expectedPath);
  assert.equal(hash(source), test.record.packetSha256); assert.equal(hash(expected), test.record.outputSha256);
  const program = new Uint16Array((memory.FLASHEND + 1) / 2).fill(0xffff); new Uint8Array(program.buffer).set(binary);
  const cpu = new CPU(program, top - memory.RAMSTART + 1); cpu.SP = top;
  const stageCycles = new Float64Array(attribution.stages.length), exclusive = new Float64Array(code.length), inclusive = new Float64Array(code.length);
  const depth = new Uint16Array(code.length), opened = new Float64Array(code.length), calls = [];
  let inheritedStage = 0, measuring = false, total = 0;
  const status = address('codec2_decode_status'), command = address('codec2_decode_command'), packet = address('codec2_decode_packet'), out = address('codec2_decode_pcm');
  function until(predicate) {
    const deadline = cpu.cycles + 500000000;
    while (!predicate()) {
      assert.ok(cpu.cycles < deadline); const pc = cpu.pc, opcode = program[pc], before = cpu.cycles;
      const explicitStage = stageMap[pc], stage = explicitStage >= 0 ? explicitStage : inheritedStage;
      avrInstruction(cpu); cpu.tick(); assert.ok(cpu.SP >= end - 1 && cpu.SP <= top);
      if (measuring) {const cost = cpu.cycles - before; total += cost; stageCycles[stage] += cost; exclusive[functionByPC[pc]] += cost;}
      const absolute = (opcode & 0xfe0e) === 0x940e;
      if (absolute || opcode === 0x9509 || opcode === 0x9519 || ((opcode & 0xf000) === 0xd000 && cpu.pc !== pc + 1)) {
        const id = functionByPC[cpu.pc]; calls.push({id, returnPC: pc + (absolute ? 2 : 1), callerStage: stage});
        if (depth[id]++ === 0) opened[id] = total; inheritedStage = stage;
      }
      if (opcode === 0x9508 || opcode === 0x9518) {
        const call = calls.pop(); assert.equal(call?.returnPC, cpu.pc, 'Balanced physical call stack');
        if (--depth[call.id] === 0) inclusive[call.id] += total - opened[call.id]; inheritedStage = call.callerStage;
      }
    }
  }
  until(() => cpu.data[status] !== 0); assert.equal(cpu.data[status], 1);
  const sampledPCM = Buffer.alloc(test.frames * 320), elapsed = [];
  const started = Date.now();
  for (let frame = 0; frame < test.start + test.frames; ++frame) {
    measuring = frame >= test.start;
    cpu.data.set(source.subarray(frame * 8, frame * 8 + 8), packet); cpu.data[status] = 1; cpu.data[command] = 1;
    const before = cpu.cycles; until(() => cpu.data[status] !== 1);
    assert.equal(cpu.data[status], 2); assert.equal(cpu.cycles - before, test.record.perFrameCycles[frame]);
    assert.deepEqual(Buffer.from(cpu.data.subarray(out, out + 320)), expected.subarray(frame * 320, frame * 320 + 320));
    if (measuring) {elapsed.push(cpu.cycles - before); sampledPCM.set(cpu.data.subarray(out, out + 320), (frame - test.start) * 320);}
  }
  for (let id = 0; id < depth.length; ++id) if (depth[id]) inclusive[id] += total - opened[id];
  assert.equal(total, elapsed.reduce((a, b) => a + b, 0));
  assert.equal([...stageCycles].reduce((a, b) => a + b, 0), total);
  const ranked = values => [...values].map((cycles, id) => ({name: code[id].name, cycles, percent: 100 * cycles / total})).filter(r => r.cycles).sort((a, b) => b.cycles - a.cycles).slice(0, 30);
  const result = {name: test.name, firstFrame: test.start, frames: test.frames, selection: test.selection,
    totalCycles: total, meanCycles: total / test.frames,
    stages: attribution.stages.map((name, id) => ({name, cycles: stageCycles[id], percent: stageCycles[id] * 100 / total})),
    inclusive: ranked(inclusive), exclusive: ranked(exclusive), binarySha256: hash(binary),
    packetSha256: hash(source), sampledPcmSha256: hash(sampledPCM), pcmAndCyclesEqualFullVerification: true,
    hostRuntimeSeconds: (Date.now() - started) / 1000};
  results.push(result); console.log(JSON.stringify({name: test.name, firstFrame: test.start, frames: test.frames, stages: result.stages}));
}
const humanResults = results.filter(r => r.name !== 'conditioning-stress');
const humanCycles = humanResults.reduce((a, b) => a + b.totalCycles, 0);
const report = {simulator: 'avr8js 0.21.1', mcu: 'ATmega64A', results,
  pooledHuman: {frames: humanResults.reduce((a, b) => a + b.frames, 0), totalCycles: humanCycles,
    stages: attribution.stages.map((name, id) => {const cycles = humanResults.reduce((a, b) => a + b.stages[id].cycles, 0); return {name, cycles, percent: 100 * cycles / humanCycles};})},
  baselineReportSha256: hash(baselineBytes), humanVerificationSha256: hash(humanBytes),
  attributionSha256: hash(readFileSync(join(build, 'attribution.json'))),
  generatorSha256: hash(readFileSync(join(root, 'tools/prepare_nopost_profile.py'))),
  profilerSha256: hash(readFileSync(fileURLToPath(import.meta.url))),
  scope: 'Source/inline instruction attribution on byte-identical release image. Highest-energy 20-frame windows from four human clips plus entire 24-frame extreme regression. PCM and every replayed frame cycle count equal full verification. Stage costs partition total; inclusive function costs overlap and tail-called helpers remain charged to entering calls. No active IRQ or board.'};
writeFileSync(join(build, 'profile.json'), JSON.stringify(report, null, 2) + '\n');
if (process.argv.includes('--record')) writeFileSync(join(root, 'reports/nopost-profile.json'), JSON.stringify(report, null, 2) + '\n');
