import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { cpus, platform, arch } from 'node:os';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { AVRCore } from '../lib/avr-core.js';
import { parseHex } from '../lib/hex.js';
const require = createRequire(import.meta.url);
const { AVRCore: DefaultReference } = require('../../ATtiny13A/Music/variants/rhythmic/avr_core.js');
const { values } = parseArgs({ options: { 'baseline-ref': {type:'string'}, report: {type:'string'} } });
let Baseline, baseline;
if (values['baseline-ref']) {
  const cwd = fileURLToPath(new URL('../../', import.meta.url));
  const revision = execFileSync('git', ['rev-parse', '--verify', '--end-of-options', values['baseline-ref'] + '^{commit}'], {cwd,encoding:'utf8'}).trim();
  const source = execFileSync('git', ['show', revision + ':web-player/lib/avr-core.js'], {cwd});
  ({ AVRCore: Baseline } = await import('data:text/javascript;base64,' + source.toString('base64')));
  baseline = {revision, coreSha256:createHash('sha256').update(source).digest('hex')};
}
const catalog = JSON.parse(readFileSync(new URL('../firmware.json', import.meta.url)));
const median = list => list.sort((a,b) => a-b)[Math.floor(list.length / 2)];
const count = 3 * 37500, repetitions = 7;
const results = [];
for (const entry of catalog.entries) {
  const Reference=Baseline ?? (entry.referenceCore?require(fileURLToPath(new URL(entry.referenceCore,new URL('../',import.meta.url)))).AVRCore:DefaultReference);
  const flash = parseHex(entry.flashHex), ep = entry.eepromHex ? parseHex(entry.eepromHex, 64) : null;
  function run(Core, count, options) {
    const core = new Core(flash, ep, options), started = performance.now();
    let checksum = 0;
    for (let i = 0; i < count; i++) checksum = (checksum + core.nextDuty()) >>> 0;
    return {ms:(performance.now() - started) * 37500 / count, checksum, cycles:core.cyc,core};
  }
  run(Reference, 37500); run(AVRCore, 37500);
  const baseline = [], optimized = [];
  for (let i = 0; i < repetitions; i++) {
    // The archived core is a speed baseline, not a hardware correctness oracle.
    // Validate the optimized execution against the corrected single-step core.
    if (i === 0) {
      const a=run(AVRCore,37500),b=run(AVRCore,37500,{fastIdle:false});
      assert.equal(a.checksum,b.checksum); assert.equal(a.cycles,b.cycles);
      assert.deepEqual(a.core.data,b.core.data);
    }
    const order = i % 2 ? [AVRCore, Reference] : [Reference, AVRCore];
    const samples = order.map(Core => [Core, run(Core, count)]);
    assert.equal(samples[0][1].checksum,samples[1][1].checksum,'Baseline musical output');
    assert.ok(Math.abs(samples[0][1].cycles-samples[1][1].cycles)<=2,'Documented RETI foreground latency');
    for (const [Core, result] of samples) (Core === Reference ? baseline : optimized).push(result.ms);
  }
  const referenceMs = median(baseline), optimizedMs = median(optimized);
  results.push({id:entry.id,flashSha256:entry.flashSha256,eepromSha256:entry.eepromSha256,referenceMs,optimizedMs,speedup:referenceMs / optimizedMs,realtimeHeadroom:1000 / optimizedMs});
}
const report = {runtime:process.version,platform:platform(),arch:arch(),cpu:cpus()[0].model,
  ...(baseline ? {baseline} : {}),
  wasm:JSON.parse(readFileSync(new URL('../wasm/build.json',import.meta.url))),
  coreSha256:createHash('sha256').update(readFileSync(new URL('../lib/avr-core.js',import.meta.url))).digest('hex'),
  method:'Median of seven alternating runs after warm-up; 112500 OCR0B writes (three nominal seconds for these images) per run, times normalized to one nominal second. Construction excluded. Corrected fast/slow cores match state, checksum and cycles; baseline matches checksum, with up to 2 cycles of RETI latency difference. This is not a physical PWM accuracy measurement.',results};
const destination = values.report ? resolve(values.report) : new URL('../reports/avr-benchmark.json', import.meta.url);
mkdirSync(new URL('../reports/', import.meta.url), {recursive:true});
writeFileSync(destination, JSON.stringify(report,null,2)+'\n');
console.table(results.map(x => ({firmware:x.id,baseline_ms:x.referenceMs.toFixed(1),optimized_ms:x.optimizedMs.toFixed(1),speedup:x.speedup.toFixed(2)+'×'})));
