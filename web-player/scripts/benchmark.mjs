import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { cpus, platform, arch } from 'node:os';
import { createHash } from 'node:crypto';
import { AVRCore } from '../lib/avr-core.js';
import { parseHex } from '../lib/hex.js';
const require = createRequire(import.meta.url);
const { AVRCore: Reference } = require('../../ATtiny13A/Music/final/attiny13a_synth_release/avr_core.js');
const catalog = JSON.parse(readFileSync(new URL('../firmware.json', import.meta.url)));
const median = list => list.sort((a,b) => a-b)[Math.floor(list.length / 2)];
const results = [];
for (const entry of catalog.entries) {
  const flash = parseHex(entry.flashHex), ep = entry.eepromHex ? parseHex(entry.eepromHex, 64) : null;
  function run(Core, count) {
    const core = new Core(flash, ep), started = performance.now();
    let checksum = 0;
    for (let i = 0; i < count; i++) checksum = (checksum + core.nextDuty()) >>> 0;
    return {ms:performance.now() - started, checksum, cycles:core.cyc};
  }
  run(Reference, 37500); run(AVRCore, 37500);
  const baseline = [], optimized = [];
  for (let i = 0; i < 5; i++) {
    const order = i % 2 ? [AVRCore, Reference] : [Reference, AVRCore];
    const samples = order.map(Core => [Core, run(Core, 37500)]);
    if (samples[0][1].checksum !== samples[1][1].checksum || samples[0][1].cycles !== samples[1][1].cycles) throw new Error('Benchmark mismatch');
    for (const [Core, result] of samples) (Core === Reference ? baseline : optimized).push(result.ms);
  }
  const referenceMs = median(baseline), optimizedMs = median(optimized);
  results.push({id:entry.id,flashSha256:entry.flashSha256,eepromSha256:entry.eepromSha256,referenceMs,optimizedMs,speedup:referenceMs / optimizedMs,realtimeHeadroom:1000 / optimizedMs});
}
const report = {runtime:process.version,platform:platform(),arch:arch(),cpu:cpus()[0].model,
  coreSha256:createHash('sha256').update(readFileSync(new URL('../lib/avr-core.js',import.meta.url))).digest('hex'),
  method:'Median of five alternating runs after warm-up; 37500 PWM samples (one emulated second) per run. Construction excluded. Same Flash/EEPROM, checksum and cycle count.',results};
mkdirSync(new URL('../reports/', import.meta.url), {recursive:true});
writeFileSync(new URL('../reports/avr-benchmark.json', import.meta.url), JSON.stringify(report,null,2)+'\n');
console.table(results.map(x => ({firmware:x.id,baseline_ms:x.referenceMs.toFixed(1),optimized_ms:x.optimizedMs.toFixed(1),speedup:x.speedup.toFixed(2)+'×'})));
