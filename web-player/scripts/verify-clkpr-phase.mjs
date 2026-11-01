// Independent absolute-time accounting and historical native artifact audit.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {runtimeABI} from '../lib/avr-transpiler.js';
import {executionOptions} from '../lib/emulation-configurations.js';
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';
import {avr,IO,sequential} from '../tests/fixtures/attiny13a-system-firmware.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{baseline:{type:'string',default:'312df174'},
  out:{type:'string',default:'build/clkpr-phase-evidence.json'},'test-tap':{type:'string'}}});
const read=p=>readFileSync(resolve(root,p)),normal=b=>b.toString('utf8').replaceAll('\r\n','\n');
const sha=b=>createHash('sha256').update(b).digest('hex');
const json=v=>JSON.stringify(v,(_,x)=>typeof x==='bigint'?x.toString():x,2)+'\n';
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:8*1024*1024});
const baseline=git('rev-parse','--verify',values.baseline+'^{commit}').toString().trim();
const nativePath='web-player/wasm/attiny13a.wasm',manifestPath='web-player/wasm/device-build.json';
const versions={before:{bytes:git('show',baseline+':'+nativePath),manifest:JSON.parse(git('show',baseline+':'+manifestPath))},
  after:{bytes:getRuntimeBytes(),manifest:JSON.parse(read(manifestPath))}};
for(const [label,v] of Object.entries(versions)){
  assert.equal(sha(v.bytes),v.manifest.artifacts['attiny13a.wasm']);assert.equal(v.bytes.length,v.manifest.bytes);
  for(const [p,h] of Object.entries(v.manifest.inputs))assert.equal(sha(normal(label==='before'?git('show',baseline+':'+p):read(p))),h,p);
  v.module=new WebAssembly.Module(v.bytes);v.exports=new WebAssembly.Instance(v.module).exports;
  assert.deepEqual(WebAssembly.Module.imports(v.module),[]);assert.equal(v.exports.memory.buffer.byteLength,131072);
}
for(const field of ['exports','flags','sources','compilerVersion','memoryPages','maximumMemoryPages','stackBytes'])
  assert.deepEqual(versions.before.manifest[field],versions.after.manifest[field],field);
assert.deepEqual(WebAssembly.Module.exports(versions.before.module),WebAssembly.Module.exports(versions.after.module));
const changedInputs=Object.keys(versions.after.manifest.inputs).filter(p=>versions.after.manifest.inputs[p]!==versions.before.manifest.inputs[p]);
assert.deepEqual(changedInputs,['web-player/native/peripherals/device.c']);
assert.deepEqual(runtimeABI(versions.before.exports,{resumable:true}),runtimeABI(versions.after.exports,{resumable:true}));
function bodies(bytes){
  let p=8;const u32=()=>{let n=0;for(let s=0;s<35;s+=7){const b=bytes[p++];n+=(b&127)*2**s;if(!(b&128))return n;}throw Error('Invalid WASM');};
  while(p<bytes.length){const id=bytes[p++],length=u32(),end=p+length;
    if(id===10)return Array.from({length:u32()},()=>{const n=u32(),body=bytes.subarray(p,p+n);p+=n;return body;});p=end;
  }throw Error('Missing code section');
}
const oldBodies=bodies(versions.before.bytes),newBodies=bodies(versions.after.bytes);assert.equal(oldBodies.length,newBodies.length);
const changedBodies=oldBodies.flatMap((b,n)=>Buffer.from(b).equals(Buffer.from(newBodies[n]))?[]:[{body:n,beforeBytes:b.length,afterBytes:newBodies[n].length}]);
assert.deepEqual(read('web-player/wasm/avr.wasm'),git('show',baseline+':web-player/wasm/avr.wasm'));
for(const [p,h] of Object.entries(AVR_CACHE_SOURCES))assert.equal(sha(normal(read(p))),h,p+' compiler identity');
// One initial LDI, then nine instructions / ten CPU cycles per loop. The
// selected /1->/2->/1 fixture consumes14 source periods per loop: no rounded
// native timestamp is ever used as the origin of the analytical reference.
const image=sequential([avr.ldi(16,128),avr.out(IO.CLKPR,16),avr.ldi(17,1),avr.out(IO.CLKPR,17),avr.nop(),
  avr.out(IO.CLKPR,16),avr.ldi(17,0),avr.out(IO.CLKPR,17),avr.nop(),avr.rjmp(9,1)]);
const runs=[];
for(const hz of [9000000,11000003,10000000])for(const [label,v] of Object.entries(versions)){
  const osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  const c=new ATtiny13A(image,null,{...executionOptions('verification'),resumable:true,
    oscillatorHz:hz,osccalHz,fuseLow:0x72,runtimeModule:v.module});c.run(1);
  const checkpoints=[];let previous=0;
  for(const loops of [1000,4000,8000,16000,32000]){
    assert.equal(c.run(9*(loops-previous)),9*(loops-previous));previous=loops;
    const expected=(BigInt(1+14*loops)*1000000000000n+BigInt(hz)-1n)/BigInt(hz),state=c.state();
    assert.equal(c.pc,1);assert.equal(c.cyc,1+10*loops);assert.equal(state.cpuPhase.retired,BigInt(1+9*loops));
    assert.equal(state.clockDivisor,1);assert.equal(state.deviceFault,0);assert.equal(c.sreg,0);
    if(label==='after')assert.equal(state.timePs,expected,'absolute rational endpoint');
    checkpoints.push({loops,sourcePeriods:1+14*loops,expectedTimePs:expected,actualTimePs:state.timePs,errorPs:state.timePs-expected});
  }
  runs.push({version:label,hz,cpuSha256:sha(c.transpiledBytes),checkpoints,dataSha256:sha(c.data),flashSha256:sha(c.rom),eepromSha256:sha(c.eeprom)});
}
for(const hz of [9000000,11000003,10000000]){
  const [a,b]=runs.filter(r=>r.hz===hz);
  for(const key of ['cpuSha256','dataSha256','flashSha256','eepromSha256'])assert.equal(a[key],b[key]);
  if(hz===9000000)assert.ok(a.checkpoints.at(-1).errorPs>10000n,'historical model exceeds the10ns software bound');
}
const stage=resolve(root,'build/clkpr-phase-baseline-20261101');mkdirSync(stage,{recursive:true});
const historicalRuntime=resolve(stage,'attiny13a.wasm');writeFileSync(historicalRuntime,versions.before.bytes);
const fixture='web-player/tests/attiny13a-clkpr-phase.test.mjs';
const result=spawnSync(process.execPath,['--test',fixture],{cwd:root,encoding:'utf8',
  env:{...process.env,MICROMUSIC_CLKPR_RUNTIME:historicalRuntime},maxBuffer:8*1024*1024});
if(result.error)throw result.error;assert.equal(result.status,1,'historical native must fail the final test source');
const beforeTap=resolve(stage,'before.tap');writeFileSync(beforeTap,result.stdout+result.stderr);
function counts(bytes){const s=bytes.toString('utf8');return Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo'].map(k=>{
  const m=s.match(new RegExp('^# '+k+' (\\d+)$','m'));assert.ok(m,k+' TAP');return[k,Number(m[1])];
}));}
const beforeCounts=counts(readFileSync(beforeTap));assert.deepEqual(beforeCounts,{tests:16,pass:3,fail:13,cancelled:0,skipped:0,todo:0});
const support=[fixture,'web-player/tests/device-deadline-cache.test.mjs','web-player/scripts/verify-clkpr-phase.mjs','web-player/scripts/verify-virtual-event-accuracy.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs'];
const report={schema:'micromusic-clkpr-phase-v1',complete:true,baseline,compilerIdentity:AVR_CACHE_COMPILER_ID,
  compilerSources:AVR_CACHE_SOURCES,sourceSha256:Object.fromEntries(support.map(p=>[p,sha(normal(read(p)))])),
  native:Object.fromEntries(Object.entries(versions).map(([k,v])=>[k,{bytes:v.bytes.length,sha256:sha(v.bytes)}])),
  nativeInputs:versions.after.manifest.inputs,changedInputs,functionBodies:oldBodies.length,changedBodies,
  beforeTests:{...beforeCounts,tapSha256:sha(readFileSync(beforeTap))},runs,
  method:'Same current host/compiler and final test source; only pinned native WASM differs. CPU bytes and final data/Flash/EEPROM hashes match. Absolute BigInt source-period accounting has no rounded-edge reanchoring. Lower-bound digital switching fixture, not measured silicon phase or a speed benchmark.'};
if(values['test-tap']){const b=read(values['test-tap']),c=counts(b);assert.equal(c.tests,c.pass);assert.equal(c.fail+c.cancelled+c.skipped+c.todo,0);report.tests={...c,tapSha256:sha(b)};}
const output=resolve(root,values.out);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,json(report));
console.log(json({native:report.native,functionBodies:report.functionBodies,changedBodies,old9MHzErrorPs:runs[0].checkpoints.at(-1).errorPs,beforeTests:beforeCounts}));
