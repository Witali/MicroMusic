// Compare retained software acquisition controls without relaxing chip timings.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=path=>JSON.parse(readFileSync(resolve(root,path)));
const sha=path=>createHash('sha256').update(readFileSync(resolve(root,path))).digest('hex');
const cpu=read('web-player/reports/pin-observation-20261024/cpu-probes.json');
const oldCpu=read('web-player/reports/cpu-phase-probe-20261024/verification.json');
const hardware=read('web-player/reports/pin-observation-20261024/hardware-probes.json');
const oldHardware=read('web-player/reports/cpu-phase-probe-20261024/previous-probe-compatibility.json');
const summary={schema:'micromusic-pin-observation-probe-comparison-v1',
  baselineRuntimeSha256:oldCpu.identities.runtimeSha256,
  candidateRuntimeSha256:cpu.identities.runtimeSha256,
  method:'Compare all profile fields except fingerprints of decoded JSON files. For every such fingerprint, verify both actual files against their recorded hashes, then require equality of the full parsed decoder output excluding only waveformCsv, which names the different acquisition output directories. Raw waveform hashes, every frame/timestamp/marker, source identities and CPU binaries remain exact. No clock/chip state normalization.',
  cpuRuns:0,cpuResetCuts:0,peripheralProfiles:0,comparisons:[]};
function jsonPair(oldPath,newPath,oldHash,newHash){
  assert.equal(sha(oldPath),oldHash,oldPath+' original identity');
  assert.equal(sha(newPath),newHash,newPath+' current identity');
  const before=read(oldPath),after=read(newPath),oldCsv=before.waveformCsv,newCsv=after.waveformCsv;
  delete before.waveformCsv;delete after.waveformCsv;
  assert.ok(oldCsv&&newCsv&&oldCsv!==newCsv);
  assert.ok(JSON.stringify(before)===JSON.stringify(after),'decoder output '+oldPath);
  summary.comparisons.push({oldPath,newPath,oldHash,newHash,
    oldWaveformCsv:oldCsv,newWaveformCsv:newCsv,allOtherDecoderFieldsEqual:true});
}
assert.equal(cpu.profiles.length,oldCpu.profiles.length);
for(const profile of cpu.profiles){
  const before=oldCpu.profiles.find(p=>p.id===profile.id);assert.ok(before,profile.id);
  const current=structuredClone(profile),prior=structuredClone(before);
  for(const [name,a,b] of [['uncut',current.preview,prior.preview],
    ...current.cuts.map((cut,i)=>[cut.name,cut,prior.cuts[i]])]){
    jsonPair(join('build/cpu-phase-probe-verification',profile.id,name+'.json'),
      join('build/pin-observation-cpu-probe-final',profile.id,name+'.json'),b.decodedSha256,a.decodedSha256);
    delete a.decodedSha256;delete b.decodedSha256;summary.cpuRuns++;
    if(name!=='uncut')summary.cpuResetCuts++;
  }
  assert.ok(JSON.stringify(current)===JSON.stringify(prior),'complete CPU profile '+profile.id);
}
assert.equal(hardware.probes.length,oldHardware.probes.length);
for(const probe of hardware.probes){
  const before=oldHardware.probes.find(p=>p.name===probe.name);assert.ok(before,probe.name);
  const current=structuredClone(probe),prior=structuredClone(before);
  for(const [index,profile] of current.profiles.entries()){
    const old=prior.profiles[index];assert.equal(profile.id,old.id);
    jsonPair(join('build/cpu-phase-compatibility-20261024',probe.name,profile.id+'.json'),
      join('build/pin-observation-hardware-probes-final',probe.name,profile.id+'.json'),
      old.software.traceSha256,profile.software.traceSha256);
    delete old.software.traceSha256;delete profile.software.traceSha256;summary.peripheralProfiles++;
  }
  assert.ok(JSON.stringify(current)===JSON.stringify(prior),'complete peripheral probe '+probe.name);
}
summary.complete=true;
writeFileSync(new URL('./probe-compatibility.json',import.meta.url),JSON.stringify(summary,null,2)+'\n');
console.log(`${summary.cpuRuns} CPU runs/${summary.cpuResetCuts} reset cuts and ${summary.peripheralProfiles} peripheral profiles exactly match; only acquisition output paths differ.`);
