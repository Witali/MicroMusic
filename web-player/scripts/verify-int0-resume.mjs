// Same final firmware tests against pinned native runtimes; no silicon oracle.
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
const {values}=parseArgs({options:{baseline:{type:'string',default:'62103e92'},
  out:{type:'string',default:'build/int0-resume-evidence.json'},'test-tap':{type:'string'},'full-test-tap':{type:'string'}}});
const sha=b=>createHash('sha256').update(b).digest('hex'),read=p=>readFileSync(resolve(root,p));
const normal=b=>b.toString('utf8').replaceAll('\r\n','\n');
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:8*1024*1024});
const baseline=git('rev-parse','--verify',values.baseline+'^{commit}').toString().trim();
const wasmPath='web-player/wasm/attiny13a.wasm',manifestPath='web-player/wasm/device-build.json';
const versions={before:{bytes:git('show',baseline+':'+wasmPath),manifest:JSON.parse(git('show',baseline+':'+manifestPath))},
  after:{bytes:getRuntimeBytes(),manifest:JSON.parse(read(manifestPath))}};
for(const [label,v] of Object.entries(versions)){
  assert.equal(sha(v.bytes),v.manifest.artifacts['attiny13a.wasm']);assert.equal(v.bytes.length,v.manifest.bytes);
  for(const [p,h] of Object.entries(v.manifest.inputs)){
    const b=label==='before'&&h!==versions.after.manifest.inputs[p]?git('show',baseline+':'+p):read(p);
    assert.equal(sha(normal(b)),h,p+' native source');
  }
  v.module=new WebAssembly.Module(v.bytes);v.exports=new WebAssembly.Instance(v.module).exports;
  assert.deepEqual(WebAssembly.Module.imports(v.module),[]);assert.equal(v.exports.memory.buffer.byteLength,131072);
}
const changedInputs=Object.keys(versions.after.manifest.inputs).filter(p=>versions.after.manifest.inputs[p]!==versions.before.manifest.inputs[p]);
assert.deepEqual([...changedInputs].sort(),['web-player/native/peripherals/system_gpio.c','web-player/native/peripherals/system_gpio.h']);
for(const key of ['exports','flags','sources','compilerVersion','memoryPages','maximumMemoryPages','stackBytes'])
  assert.deepEqual(versions.before.manifest[key],versions.after.manifest[key]);
assert.deepEqual(WebAssembly.Module.exports(versions.before.module),WebAssembly.Module.exports(versions.after.module));
assert.deepEqual(runtimeABI(versions.before.exports,{resumable:true}),runtimeABI(versions.after.exports,{resumable:true}));
assert.deepEqual(read('web-player/wasm/avr.wasm'),git('show',baseline+':web-player/wasm/avr.wasm'));
function bodies(bytes){
  let p=8;const u32=()=>{let n=0;for(let s=0;s<35;s+=7){const b=bytes[p++];n+=(b&127)*2**s;if(!(b&128))return n;}throw Error('Invalid WASM');};
  while(p<bytes.length){const id=bytes[p++],size=u32(),end=p+size;
    if(id===10)return Array.from({length:u32()},()=>{const n=u32(),body=bytes.subarray(p,p+n);p+=n;return body;});p=end;
  }throw Error('Missing code section');
}
const a=bodies(versions.before.bytes),b=bodies(versions.after.bytes);assert.equal(a.length,b.length);
const changedBodies=a.flatMap((body,n)=>Buffer.from(body).equals(Buffer.from(b[n]))?[]:[{body:n,beforeBytes:body.length,afterBytes:b[n].length}]);
const counts=bytes=>Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo'].map(k=>{
  const m=bytes.toString('utf8').match(new RegExp('^# '+k+' (\\d+)$','m'));assert.ok(m,k+' completed TAP');return[k,Number(m[1])];
}));
const folder=resolve(root,'build/int0-resume-reference-20261101');mkdirSync(folder,{recursive:true});
const fixture='web-player/tests/attiny13a-int0-resume.test.mjs',tests={};
for(const [label,v] of Object.entries(versions)){
  const wasm=resolve(folder,label+'.wasm');writeFileSync(wasm,v.bytes);
  const r=spawnSync(process.execPath,['--test',fixture],{cwd:root,encoding:'utf8',
    env:{...process.env,MICROMUSIC_INT0_RUNTIME:wasm},maxBuffer:8*1024*1024});
  if(r.error)throw r.error;assert.equal(r.status,label==='before'?1:0);
  const tap=Buffer.from(r.stdout+r.stderr);writeFileSync(resolve(folder,label+'.tap'),tap);
  tests[label]={...counts(tap),tapSha256:sha(tap)};
  assert.equal(tests[label].tests,18);assert.equal(tests[label].pass,label==='before'?4:18);
  assert.equal(tests[label].fail,label==='before'?14:0);assert.equal(tests[label].cancelled+tests[label].skipped+tests[label].todo,0);
}
for(const [p,h] of Object.entries(AVR_CACHE_SOURCES))assert.equal(sha(normal(read(p))),h,p+' compiler graph');
const support=[fixture,'web-player/tests/system-gpio.test.mjs','web-player/scripts/verify-int0-resume.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs'];
const report={schema:'micromusic-int0-resume-evidence-v1',complete:true,baseline,compilerIdentity:AVR_CACHE_COMPILER_ID,
  compilerSources:AVR_CACHE_SOURCES,sourceSha256:Object.fromEntries(support.map(p=>[p,sha(normal(read(p)))])),
  native:Object.fromEntries(Object.entries(versions).map(([k,v])=>[k,{bytes:v.bytes.length,sha256:sha(v.bytes)}])),
  nativeInputs:versions.after.manifest.inputs,changedInputs,functionBodies:a.length,changedBodies,tests,
  method:'Same final firmware source and host/compiler, with only the pinned native WASM changed. WDT and PCINT wake, all three masked INT0 edge senses, internal/CLKI sources, verification/optimized execution and Idle/ADC Noise controls. INTF0 is read by the first post-SLEEP firmware instruction. The first resumed clkI/O rise is an explicit digital-fixture phase choice, not an official simulator observation or measured silicon phase. No performance claim.'};
for(const [key,arg] of [['focused','test-tap'],['fullSuite','full-test-tap']])if(values[arg]){
  const tap=read(values[arg]),c=counts(tap);assert.ok(c.tests>0);assert.equal(c.pass,c.tests);assert.equal(c.fail+c.cancelled+c.skipped+c.todo,0);
  report[key]={...c,tapSha256:sha(tap)};
}
const output=resolve(root,values.out);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({native:report.native,changedBodies,tests,focused:report.focused,fullSuite:report.fullSuite}));
