import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {cpus, platform, arch} from 'node:os';
import {parseArgs} from 'node:util';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {join, resolve} from 'node:path';
import assert from 'node:assert/strict';
import {Renderer} from '../lib/renderer.js';
import {sameCPU} from '../tests/helpers/avr-test-state.mjs';

const {values} = parseArgs({options:{'baseline-ref':{type:'string'}, report:{type:'string'}, seconds:{type:'string'}, trials:{type:'string'}, warmup:{type:'string'}}});
if (!values['baseline-ref']) throw new Error('Pass --baseline-ref <commit> containing the previous native build');
const seconds = Number(values.seconds ?? 12), trials = Number(values.trials ?? 9), warmup = Number(values.warmup ?? 30);
if (!Number.isInteger(seconds) || seconds < 1 || seconds > 300 || !Number.isInteger(trials) || trials < 3 || trials > 31 || !Number.isInteger(warmup) || warmup < 1 || warmup > 300)
  throw new Error('Use seconds/warmup 1..300 and trials 3..31');
const root = fileURLToPath(new URL('../../', import.meta.url));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const textHash = file => hash(readFileSync(file, 'utf8').replaceAll('\r\n', '\n'));
function git(args) {
  const result = spawnSync('git', args, {cwd:root, maxBuffer:16*1024*1024});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr.toString());
  return result.stdout;
}
const baselineCommit = git(['rev-parse', '--verify', values['baseline-ref'] + '^{commit}']).toString().trim();
const directory = join(root, 'build/avr-native-benchmark', baselineCommit);
for (const part of ['lib', 'wasm']) mkdirSync(join(directory, part), {recursive:true});
for (const file of ['lib/avr-core.js', 'lib/avr-wasm.js', 'lib/renderer.js', 'lib/hex.js', 'wasm/avr.wasm', 'wasm/build.json'])
  writeFileSync(join(directory, file), git(['show', baselineCommit + ':web-player/' + file]));
writeFileSync(join(directory, 'package.json'), '{"type":"module"}\n');
const {Renderer:Baseline} = await import(pathToFileURL(join(directory, 'lib/renderer.js')).href);
const baselineBuild = JSON.parse(readFileSync(join(directory, 'wasm/build.json')));
const build = JSON.parse(readFileSync(join(root, 'web-player/wasm/build.json')));
const baselineWasm = readFileSync(join(directory, 'wasm/avr.wasm'));
const wasm = readFileSync(join(root, 'web-player/wasm/avr.wasm'));
assert.equal(hash(baselineWasm), baselineBuild.artifacts['avr.wasm']);
assert.equal(hash(wasm), build.artifacts['avr.wasm']);
for (const [file, expected] of Object.entries(baselineBuild.inputs))
  assert.equal(hash(git(['show', baselineCommit + ':' + file]).toString().replaceAll('\r\n', '\n')), expected, 'Baseline ' + file);
for (const [file, expected] of Object.entries(build.inputs)) assert.equal(textHash(join(root, file)), expected, file);
const catalog = JSON.parse(readFileSync(new URL('../firmware.json', import.meta.url)));
const rate = 48000, controls = {cutoff:9000, volume:.65}, blockSize = 4096;
const median = samples => [...samples].sort((a,b) => a-b)[samples.length >> 1];
function render(Type, entry, duration) {
  const renderer = new Type(entry, rate, controls), cpuStart = process.cpuUsage(), start = performance.now(); let checksum = 0;
  for (let offset = 0; offset < rate * duration; offset += blockSize) {
    const pcm = renderer.render(Math.min(blockSize, rate * duration - offset)); checksum += pcm.at(-1);
  }
  const elapsed = performance.now() - start, usage = process.cpuUsage(cpuStart);
  return {msPerAudioSecond:elapsed / duration, cpuMsPerAudioSecond:(usage.user+usage.system)/1000/duration, checksum};
}
const rows = [];
for (const entry of catalog.entries) {
  // Validation is outside the timed runs: every sample and each block boundary.
  const current = new Renderer(entry, rate, controls), previous = new Baseline(entry, rate, controls);
  const pcmHash = createHash('sha256'), rawHash = createHash('sha256');
  for (let offset = 0; offset < rate * seconds; offset += blockSize) {
    const count = Math.min(blockSize, rate * seconds - offset), actual = current.render(count), expected = previous.render(count);
    assert.deepEqual(actual, expected, 'Filtered PCM ' + entry.id + ' frame ' + offset);
    assert.deepEqual(current.core.rawSamples, previous.core.rawSamples);
    sameCPU(current.core, previous.core); assert.deepEqual(current.core.state(), previous.core.state());
    pcmHash.update(new Uint8Array(actual.buffer)); rawHash.update(new Uint8Array(current.core.rawSamples.buffer));
  }
  render(Baseline, entry, warmup); render(Renderer, entry, warmup);
  const baselineTimes = [], currentTimes = [], baselineCpuTimes = [], currentCpuTimes = [];
  for (let trial = 0; trial < trials; trial++) {
    const order = trial % 2 ? [Renderer, Baseline] : [Baseline, Renderer]; let checksum;
    for (const Type of order) {
      const result = render(Type, entry, seconds);
      if (checksum !== undefined) assert.equal(result.checksum, checksum); checksum = result.checksum;
      (Type === Baseline ? baselineTimes : currentTimes).push(result.msPerAudioSecond);
      (Type === Baseline ? baselineCpuTimes : currentCpuTimes).push(result.cpuMsPerAudioSecond);
    }
  }
  const baselineMs = median(baselineTimes), currentMs = median(currentTimes), speedup = baselineMs / currentMs;
  const row = {id:entry.id, flashSha256:entry.flashSha256, eepromSha256:entry.eepromSha256,
    baselineMs, currentMs, speedup, throughputGainPercent:(speedup-1)*100, realtimeHeadroom:1000/currentMs,
    baselineTimes, currentTimes, baselineCpuTimes, currentCpuTimes,
    cpuSpeedup:median(baselineCpuTimes)/median(currentCpuTimes),
    wallTimeSpread:Math.max(...baselineTimes,...currentTimes)/Math.min(...baselineTimes,...currentTimes),
    validation:{frames:rate*seconds, pcmSha256:pcmHash.digest('hex'), rawSha256:rawHash.digest('hex'),
      bitExact:true, cycles:current.core.cyc, irqs:current.core.irqCount, lost:current.core.lost, workLost:current.core.workLost}};
  rows.push(row); console.log(entry.id + ': ' + baselineMs.toFixed(2) + ' → ' + currentMs.toFixed(2) + ' ms/audio second; ' + speedup.toFixed(3) + 'x');
}
const report = {schema:'micromusic-native-speed-v1', runtime:process.version, platform:platform(), arch:arch(), cpu:cpus()[0].model,
  baselineCommit, sampleRate:rate, seconds, trials, warmupSeconds:warmup, blockSize, controls,
  method:'Median of warmed alternating runs; construction and compilation excluded. Full bit-exact PCM/raw and CPU/timer/IRQ comparison at every block of a separate validation run. Both versions render the current catalog. All wall and process CPU times are retained; CPU time excludes descheduling but includes this process background work. Large wall-time spread indicates a noisy host. Results describe this host/runtime.',
  scriptSha256:textHash(fileURLToPath(import.meta.url)),
  inputs:Object.fromEntries(['web-player/lib/renderer.js', 'web-player/lib/avr-wasm.js', 'web-player/lib/hex.js',
    'web-player/tests/helpers/avr-test-state.mjs', 'web-player/firmware.json'].map(file => [file,textHash(join(root,file))])),
  baseline:{sourceSha256:baselineBuild.inputs['web-player/native/avr.c'], wasmSha256:hash(baselineWasm), bytes:baselineWasm.length, compiler:baselineBuild.compilerVersion},
  current:{sourceSha256:build.inputs['web-player/native/avr.c'], wasmSha256:hash(wasm), bytes:wasm.length, compiler:build.compilerVersion},
  geometricMeanSpeedup:Math.exp(rows.reduce((sum,row) => sum+Math.log(row.speedup),0)/rows.length), results:rows};
const destination = values.report ? resolve(values.report) : join(root, 'build/avr-native-benchmark/results.json');
writeFileSync(destination, JSON.stringify(report,null,2) + '\n');
console.log('Report: ' + destination);
