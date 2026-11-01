// Reproduce the INT0 flag/request regression with only the native WASM varied.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {parseArgs} from 'node:util';
import {getRuntimeBytes} from '../lib/attiny13a.js';
import {runtimeABI} from '../lib/avr-transpiler.js';
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{out:{type:'string',default:'build/int0-adc-evidence.json'},
  'test-tap':{type:'string'},'full-test-tap':{type:'string'},'timing-report':{type:'string'}}});
const read=p=>readFileSync(resolve(root,p)),sha=b=>createHash('sha256').update(b).digest('hex');
const normal=b=>b.toString('utf8').replaceAll('\r\n','\n');
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:8*1024*1024});
const baseline=git('rev-parse','01632f9c^{commit}').toString().trim(),wasmPath='web-player/wasm/attiny13a.wasm';
const versions={before:{bytes:git('show',baseline+':'+wasmPath),manifest:JSON.parse(git('show',baseline+':web-player/wasm/device-build.json'))},
  after:{bytes:getRuntimeBytes(),manifest:JSON.parse(read('web-player/wasm/device-build.json'))}};
for(const [label,v]of Object.entries(versions)){
  assert.equal(sha(v.bytes),v.manifest.artifacts['attiny13a.wasm']);assert.equal(v.bytes.length,v.manifest.bytes);
  for(const [p,h]of Object.entries(v.manifest.inputs)){
    const bytes=label==='before'&&h!==versions.after.manifest.inputs[p]?git('show',baseline+':'+p):read(p);
    assert.equal(sha(normal(bytes)),h,p);
  }
  v.module=new WebAssembly.Module(v.bytes);v.exports=new WebAssembly.Instance(v.module).exports;
  assert.deepEqual(WebAssembly.Module.imports(v.module),[]);assert.equal(v.exports.memory.buffer.byteLength,131072);
}
const changedInputs=Object.keys(versions.after.manifest.inputs).filter(p=>versions.after.manifest.inputs[p]!==versions.before.manifest.inputs[p]);
assert.deepEqual(changedInputs,['web-player/native/peripherals/device.c']);
for(const key of ['exports','flags','sources','compilerVersion','memoryPages','maximumMemoryPages','stackBytes'])
  assert.deepEqual(versions.before.manifest[key],versions.after.manifest[key]);
assert.deepEqual(WebAssembly.Module.exports(versions.before.module),WebAssembly.Module.exports(versions.after.module));
assert.deepEqual(runtimeABI(versions.before.exports,{resumable:true}),runtimeABI(versions.after.exports,{resumable:true}));
assert.deepEqual(read('web-player/wasm/avr.wasm'),git('show',baseline+':web-player/wasm/avr.wasm'));
const counts=tap=>Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo'].map(k=>{
  const match=tap.toString('utf8').match(new RegExp('^# '+k+' (\\d+)$','m'));assert.ok(match,k);return[k,Number(match[1])];
}));
const fixture='web-player/tests/attiny13a-int0-adc.test.mjs',tests={},folder=resolve(root,'build/int0-adc-reference-20261101');mkdirSync(folder,{recursive:true});
for(const [label,v]of Object.entries(versions)){
  const wasm=resolve(folder,label+'.wasm');writeFileSync(wasm,v.bytes);
  const r=spawnSync(process.execPath,['--test',fixture],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024,
    env:{...process.env,MICROMUSIC_INT0_ADC_RUNTIME:wasm}});if(r.error)throw r.error;
  assert.equal(r.status,label==='before'?1:0);const tap=Buffer.from(r.stdout+r.stderr);writeFileSync(resolve(folder,label+'.tap'),tap);
  const c=counts(tap);assert.equal(c.tests,28);assert.equal(c.pass,label==='before'?18:28);assert.equal(c.fail,label==='before'?10:0);
  assert.equal(c.cancelled+c.skipped+c.todo,0);tests[label]={...c,tapSha256:sha(tap)};
}
for(const [p,h]of Object.entries(AVR_CACHE_SOURCES))assert.equal(sha(normal(read(p))),h,p);
const sources=[fixture,'web-player/tests/attiny13a-device-analog.test.mjs','web-player/native/peripherals/device-test.c',
  'web-player/tests/device-scheduler.test.mjs','web-player/scripts/verify-int0-adc.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs'];
const report={schema:'micromusic-int0-adc-evidence-v1',baseline,complete:true,compilerIdentity:AVR_CACHE_COMPILER_ID,
  compilerSources:AVR_CACHE_SOURCES,sourceSha256:Object.fromEntries(sources.map(p=>[p,sha(normal(read(p)))])),nativeInputs:versions.after.manifest.inputs,
  changedInputs,native:Object.fromEntries(Object.entries(versions).map(([k,v])=>[k,{bytes:v.bytes.length,sha256:sha(v.bytes)}])),tests,
  method:'Same final firmware source and compiler with only pinned native WASM varied. Low-level CPU pending/wake remains live with INTF0 clear and cannot auto-trigger ADC. All edge senses, masked/enabled vectors with SREG.I clear, manual ADSC, held flags, W1C/retrigger, internal/CLKI and verification/optimized execution are covered. Sleep restoration uses the explicit first-resumed-edge fixture. No official simulator, silicon phase or performance claim.'};
for(const [key,arg]of [['focused','test-tap'],['fullSuite','full-test-tap']])if(values[arg]){
  const tap=read(values[arg]),c=counts(tap);assert.ok(c.tests>0);assert.equal(c.tests,c.pass);assert.equal(c.fail+c.cancelled+c.skipped+c.todo,0);
  report[key]={...c,tapSha256:sha(tap)};
}
if(values['timing-report']){
  const bytes=read(values['timing-report']),r=JSON.parse(bytes);assert.equal(r.native.sha256,sha(versions.after.bytes));
  assert.equal(r.compilerIdentity,AVR_CACHE_COMPILER_ID);assert.equal(r.configuration,'verification');
  assert.deepEqual(r.nativeInputs,versions.after.manifest.inputs);assert.deepEqual(r.compilerSources,AVR_CACHE_SOURCES);
  for(const [p,h]of Object.entries(r.sources))assert.equal(sha(normal(read(p))),h,p);
  assert.ok(BigInt(r.maxErrorPs)<=BigInt(r.tolerancePs));assert.equal(r.tolerancePs,'10000');
  report.timingReplay={reportSha256:sha(bytes),sources:r.sources,scenarios:r.results.length,
    events:r.results.reduce((n,r)=>n+r.eventCount,0),maxErrorPs:r.maxErrorPs,tolerancePs:r.tolerancePs,meaning:r.meaning};
}
const output=resolve(root,values.out);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({native:report.native,tests,focused:report.focused,fullSuite:report.fullSuite,timing:report.timingReplay&&
  {scenarios:report.timingReplay.scenarios,events:report.timingReplay.events,maxErrorPs:report.timingReplay.maxErrorPs}}));
