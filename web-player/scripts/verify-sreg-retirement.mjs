// Reproduce flag-retirement failures and unchanged timed output, without timing claims.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
import {parseHex} from '../lib/hex.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';
const root=fileURLToPath(new URL('../../',import.meta.url)),read=p=>readFileSync(join(root,p));
const sha=b=>createHash('sha256').update(b).digest('hex'),textSha=b=>sha(b.toString().replaceAll('\r\n','\n'));
const {values}=parseArgs({options:{baseline:{type:'string',default:'47fe829b'},
  'manual-audit':{type:'string',default:'build/avr-sreg-manual.json'},'full-tap':{type:'string',default:'build/sreg-retirement-full.tap'},
  output:{type:'string',default:'build/sreg-retirement-evidence.json'}}});
const manualAudit=JSON.parse(read(values['manual-audit'])),catalogPath='web-player/reports/attiny13a-instructions.json';
assert.equal(manualAudit.catalogSha256,textSha(read(catalogPath)));assert.equal(manualAudit.rows.length,123);
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:16*1024*1024});
const commit=git('rev-parse','--verify',values.baseline+'^{commit}').toString().trim();
mkdirSync(join(root,'build'),{recursive:true});const baseline=mkdtempSync(join(root,'build/sreg-retirement-baseline-'));
const sources=git('ls-tree','-r','--name-only',commit,'web-player/lib').toString().trim().split('\n').filter(p=>p.endsWith('.js'));
for(const p of [...sources,'web-player/package.json','web-player/wasm/attiny13a.wasm','web-player/wasm/avr.wasm',catalogPath]){
  const bytes=git('show',commit+':'+p);mkdirSync(dirname(join(baseline,p)),{recursive:true});writeFileSync(join(baseline,p),bytes);
  if(p.endsWith('.wasm'))assert.equal(sha(bytes),sha(read(p)),'Unchanged native runtime');
  if(p===catalogPath)assert.equal(textSha(bytes),manualAudit.catalogSha256);
}
const regression='web-player/tests/avr-sreg-retirement.test.mjs';
for(const p of [regression,'web-player/tests/fixtures/attiny13a-system-firmware.mjs']){
  mkdirSync(dirname(join(baseline,p)),{recursive:true});writeFileSync(join(baseline,p),read(p));
}
function check(dir,label){
  const result=spawnSync(process.execPath,['--test',regression],{cwd:dir,encoding:'utf8',maxBuffer:8*1024*1024});
  assert.ifError(result.error);assert.ok([0,1].includes(result.status));
  writeFileSync(join(root,'build/sreg-retirement-'+label+'.tap'),result.stdout+result.stderr);
  return [...result.stdout.matchAll(/^(ok|not ok) \d+ - (.+)$/gm)].map(m=>({name:m[2],pass:m[1]==='ok'}));
}
const before=check(baseline,'before'),after=check(root,'after');
assert.equal(before.length,296);assert.equal(after.length,296);assert.ok(before.some(t=>!t.pass));
assert.ok(after.every(t=>t.pass));assert.deepEqual(before.map(t=>t.name),after.map(t=>t.name));
const [{ATtiny13A:Old},{ATtiny13A:Current}]=await Promise.all([
  import(pathToFileURL(join(baseline,'web-player/lib/attiny13a.js')).href),import('../lib/attiny13a.js')]);
const catalogBytes=read('web-player/firmware.json'),catalog=JSON.parse(catalogBytes),audio=[];
for(const id of ['rhythmic','lumiere-stereo'])for(const optimized of [false,true]){
  const entry=catalog.entries.find(e=>e.id===id);assert.ok(entry,id);
  const options={...nominalVerificationDeviceOptions(entry.cpuHz),cacheTranslation:false,
    ...(optimized?{fastBlocks:true,optimizeFlags:true,maxBlockInstructions:32,boundedRegions:true,optimizePhaseLocals:true}:{})};
  const cores=[Old,Current].map(Core=>new Core(parseHex(entry.flashHex),null,options));
  for(const c of cores)c.observePins(63,{retainDuringAudio:true});
  const pcm=createHash('sha256'),pins=createHash('sha256');let pinCount=0;
  for(let chunk=0;chunk<16;chunk++){
    const samples=cores.map(c=>c.capturePhysical(256,48000,entry.audioChannels||1));assert.deepEqual(...samples);
    pcm.update(new Uint8Array(samples[0].buffer,samples[0].byteOffset,samples[0].byteLength));
    const traces=cores.map(c=>c.drainPinsPs());assert.deepEqual(...traces);pinCount+=traces[0].length;
    pins.update(JSON.stringify(traces[0],(_k,v)=>typeof v==='bigint'?v+'n':v));
    for(const field of ['data','eeprom','rom'])assert.deepEqual(cores[0][field],cores[1][field]);
    assert.deepEqual(Array.from(cores[0]._state),Array.from(cores[1]._state));
    for(const field of ['pc','cyc'])assert.equal(cores[0][field],cores[1][field]);
    for(const c of cores)assert.equal(c.state().deviceFault,0);
    assert.equal(cores[0].state().cpuPhase.retired,cores[1].state().cpuPhase.retired);
    assert.equal(cores[0].state().timePs,cores[1].state().timePs);
  }
  const state=cores[1].state();assert.ok(state.irqs>0);assert.ok(pinCount>0);
  audio.push({id,policy:optimized?'bounded-phase-locals':'verification',frames:4096,sampleRate:48000,
    pcmSha256:pcm.digest('hex'),pinsSha256:pins.digest('hex'),pinCount,irqs:state.irqs,
    retired:state.cpuPhase.retired.toString(),timePs:state.timePs.toString(),
    generatedBytes:{before:cores[0].transpiledBytes.length,after:cores[1].transpiledBytes.length}});
}
const tap=read(values['full-tap']).toString(),metric=name=>{const m=tap.match(new RegExp('^# '+name+' ([0-9.]+)$','m'));assert.ok(m,name);return Number(m[1]);};
const fullSuite=Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo','duration_ms'].map(k=>[k,metric(k)]));
assert.equal(fullSuite.pass,fullSuite.tests);assert.ok(fullSuite.tests>=2322);assert.equal(fullSuite.skipped,0);
const native=read('web-player/wasm/attiny13a.wasm');
const report={schema:'micromusic-sreg-retirement-v1',baselineCommit:commit,compilerIdentity:AVR_CACHE_COMPILER_ID,
  sourceSha256:textSha(read('web-player/lib/avr-transpiler.js')),
  baselineSourceSha256:textSha(git('show',commit+':web-player/lib/avr-transpiler.js')),
  harnessSha256:textSha(readFileSync(fileURLToPath(import.meta.url))),
  auditHarnessSha256:textSha(read('web-player/scripts/audit-avr-sreg.py')),
  regressionSha256:textSha(read(regression)),catalogSha256:textSha(catalogBytes),
  native:{bytes:native.length,sha256:sha(native)},node:process.version,v8:process.versions.v8,
  hardwareTested:false,realtimeTested:false,executionSpeedMeasured:false,manualAudit,
  regression:{tests:after.length,beforePass:before.filter(t=>t.pass).length,beforeFailures:before.filter(t=>!t.pass).map(t=>t.name),afterPass:after.length},
  fullSuite,audio};
mkdirSync(dirname(join(root,values.output)),{recursive:true});writeFileSync(join(root,values.output),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({beforePass:report.regression.beforePass,beforeFail:report.regression.beforeFailures.length,
  afterPass:after.length,manualForms:manualAudit.rows.length,fullSuite,audio:audio.map(({id,policy,pinCount,irqs,generatedBytes})=>({id,policy,pinCount,irqs,generatedBytes}))},null,2));
