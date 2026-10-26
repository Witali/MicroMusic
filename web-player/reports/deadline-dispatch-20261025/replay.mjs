import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
const root=fileURLToPath(new URL('../../../',import.meta.url)),dir=fileURLToPath(new URL('./',import.meta.url));
const bytes=p=>readFileSync(join(dir,p)),read=p=>bytes(p).toString().replaceAll('\r\n','\n');
const json=p=>JSON.parse(read(p)),sha=b=>createHash('sha256').update(b).digest('hex');
const git=p=>execFileSync('git',['show','cf9c91f6:'+p],{cwd:root,maxBuffer:16*1024*1024});
const evidence=json('evidence.json');
for(const [p,h]of Object.entries(evidence.filesSha256))assert.equal(sha(p.endsWith('.wasm')?bytes(p):read(p)),h,p);
const m=json('candidate-manifest.json'),old=JSON.parse(git('web-player/wasm/device-build.json'));
assert.equal(sha(bytes('candidate.wasm')),m.artifacts['attiny13a.wasm']);
for(const [p,h]of Object.entries(m.inputs))assert.equal(sha(p==='web-player/native/peripherals/device.c'?
  read('candidate-device.c'):git(p).toString().replaceAll('\r\n','\n')),h,p);
for(const key of ['exports','flags','compilerVersion','sources'])assert.deepEqual(m[key],old[key]);
const restored=read('candidate-device.c')
  .replace('/* Keep the large miss path out of the frequently reused same-state lookup. */\nstatic uint64_t next_event_scan(void) __attribute__((noinline));\n','')
  .replace('static inline uint64_t next_event(void) __attribute__((always_inline));\nstatic inline uint64_t next_event(void)', 'static uint64_t next_event(void)');
assert.equal(restored,git('web-player/native/peripherals/device.c').toString().replaceAll('\r\n','\n'));
const module=new WebAssembly.Module(bytes('candidate.wasm'));
assert.deepEqual(WebAssembly.Module.imports(module),[]);assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
const design=await import('data:text/javascript;base64,'+git('web-player/scripts/lib/runtime-control-design.mjs').toString('base64'));
let timings=0,warmups=0,snapshots=0,comparisons=0;
for(const name of ['parity','screen','confirmation']){
  const r=json(name+'.json');assert.equal(r.complete,true);
  assert.equal(r.provenance.runtimes.oldA.sha256,old.artifacts['attiny13a.wasm']);
  assert.equal(r.provenance.runtimes.newA.sha256,m.artifacts['attiny13a.wasm']);
  for(const [p,h]of Object.entries(r.provenance.sourceSha256))assert.equal(sha(p==='web-player/scripts/benchmark-runtime-controls.mjs'?
    read('benchmark-source.txt'):git(p).toString().replaceAll('\r\n','\n')),h,p);
  for(const row of r.results){
    const runs=[...row.warmups,...row.runs],first=runs[0];
    for(const x of runs){
      for(const k of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(x[k],first[k]);
      assert.deepEqual(x.finalState,first.finalState);snapshots+=x.checkpoints;
    }
    assert.equal(row.validation.checkpointsCompared,(runs.length-1)*first.checkpoints);comparisons+=row.validation.checkpointsCompared;
    if(name!=='parity'){assert.deepEqual(row.summary.ratios,design.controlRatios(row.runs,r.parameters.trials));timings+=row.runs.length;warmups+=row.warmups.length;}
  }
}
const comparison=json('function-comparison.json');
assert.equal(comparison.productionUnmodified,true);
assert.deepEqual(comparison.counts,{identical:198,'relocation-only':0,'body-changed':4,added:1,removed:1});
assert.ok(read('focused-test.tap').includes('# pass 34\n'));
for(const line of ['tests 1704','pass 1704','fail 0','skipped 0'])assert.ok(read('full-test.tap').includes('# '+line+'\n'));
const repeated=json('rebuild-parity.json');assert.equal(repeated.complete,true);assert.equal(repeated.results.length,15);
for(const row of repeated.results){
  const original=json('parity.json').results.find(x=>x.id===row.id);assert.ok(original);
  assert.equal(row.translationSha256,original.translationSha256);
  for(const x of row.runs){
    for(const key of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(x[key],original.runs[0][key]);
    assert.deepEqual(x.finalState,original.runs[0].finalState);
  }
}
if(process.argv.includes('--rebuild')){
  const base=join(root,'build/replays');mkdirSync(base,{recursive:true});const target=mkdtempSync(join(base,'deadline-dispatch-'));
  const put=(p,b)=>{const dest=join(target,p);mkdirSync(dirname(dest),{recursive:true});writeFileSync(dest,b);};
  const libs=execFileSync('git',['ls-tree','-r','--name-only','cf9c91f6','web-player/lib'],{cwd:root,encoding:'utf8'}).trim().split('\n');
  const paths=new Set([...libs,...Object.keys(m.inputs),'web-player/package.json','web-player/firmware.json','web-player/hq4-firmware.json',
    'web-player/scripts/lib/runtime-control-design.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs']);
  for(const p of paths)put(p,p==='web-player/native/peripherals/device.c'?bytes('candidate-device.c'):git(p));
  put('web-player/scripts/benchmark-runtime-controls.mjs',bytes('benchmark-source.txt'));
  const sdk=process.env.EMSDK||'C:/Work/MicroMusic/build/toolchains/emscripten-6.0.12';
  execFileSync(process.execPath,['web-player/scripts/build-device-wasm.mjs','--emsdk',sdk],{cwd:target,stdio:'inherit'});
  assert.equal(sha(readFileSync(join(target,'web-player/wasm/attiny13a.wasm'))),m.artifacts['attiny13a.wasm']);
  execFileSync(process.execPath,['web-player/scripts/benchmark-runtime-controls.mjs','--baseline-ref','cf9c91f6',
    '--change-set','deadline-dispatch','--validate-only','--out','parity-replay.json'],{cwd:target,stdio:'inherit'});
  console.log('Isolated replay: '+target);
}
console.log(JSON.stringify({timings,warmups,snapshots,comparisons,focusedTests:34,identicalFunctionBodies:198}));
