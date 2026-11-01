// Pin the native artifacts and run the same pad contract against both.
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
const {values}=parseArgs({options:{baseline:{type:'string',default:'8ccb5c73'},
  out:{type:'string',default:'build/clki-pad-evidence.json'},'test-tap':{type:'string'}}});
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
assert.deepEqual(changedInputs,['web-player/native/peripherals/device.c','web-player/native/devices/attiny13a/clki_board.inc']);
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
const folder=resolve(root,'build/clki-pad-reference-20261101');mkdirSync(folder,{recursive:true});
const fixture='web-player/tests/attiny13a-clki-pad.test.mjs',tests={};
for(const [label,v] of Object.entries(versions)){
  const wasm=resolve(folder,label+'.wasm');writeFileSync(wasm,v.bytes);
  const r=spawnSync(process.execPath,['--test',fixture],{cwd:root,encoding:'utf8',
    env:{...process.env,MICROMUSIC_CLKI_PAD_RUNTIME:wasm},maxBuffer:8*1024*1024});
  if(r.error)throw r.error;assert.equal(r.status,label==='before'?1:0);
  const tap=Buffer.from(r.stdout+r.stderr);writeFileSync(resolve(folder,label+'.tap'),tap);
  tests[label]={...counts(tap),tapSha256:sha(tap)};
  assert.equal(tests[label].tests,28);assert.equal(tests[label].pass,label==='before'?2:28);
  assert.equal(tests[label].fail,label==='before'?26:0);assert.equal(tests[label].cancelled+tests[label].skipped+tests[label].todo,0);
}
for(const [p,h] of Object.entries(AVR_CACHE_SOURCES))assert.equal(sha(normal(read(p))),h,p+' compiler graph');
const support=[fixture,'web-player/tests/device-gpio-idle.test.mjs','web-player/scripts/verify-clki-pad.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs'];
const report={schema:'micromusic-clki-pad-evidence-v1',complete:true,baseline,compilerIdentity:AVR_CACHE_COMPILER_ID,
  compilerSources:AVR_CACHE_SOURCES,sourceSha256:Object.fromEntries(support.map(p=>[p,sha(normal(read(p)))])),
  native:Object.fromEntries(Object.entries(versions).map(([k,v])=>[k,{bytes:v.bytes.length,sha256:sha(v.bytes)}])),
  nativeInputs:versions.after.manifest.inputs,changedInputs,functionBodies:a.length,changedBodies,tests,
  method:'Same final test source and host/compiler, with only pinned native WASM changed. Cases check legal matching PB3 output drives, raw/periodic phases, CPU/Timer0/ADC3 and exact pin equality after driver release, conflict-before-consumer ordering, RESET/WDT/analog reset ties, held clocks, Power-down and package verification. No opposed-driver voltage, debugWIRE behavior, silicon accuracy or speed is inferred.'};
if(values['test-tap']){
  const tap=read(values['test-tap']),c=counts(tap);assert.equal(c.pass,c.tests);assert.equal(c.fail+c.cancelled+c.skipped+c.todo,0);
  report.focused={...c,tapSha256:sha(tap)};
}
const output=resolve(root,values.out);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({native:report.native,changedBodies,tests,focused:report.focused}));
