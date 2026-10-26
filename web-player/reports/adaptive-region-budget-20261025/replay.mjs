import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,existsSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
const root=fileURLToPath(new URL('../../../',import.meta.url)),dir=fileURLToPath(new URL('./',import.meta.url));
const bytes=p=>readFileSync(join(dir,p)),text=p=>bytes(p).toString().replaceAll('\r\n','\n');
const json=p=>JSON.parse(p.endsWith('.gz')?gunzipSync(bytes(p)):text(p)),sha=b=>createHash('sha256').update(b).digest('hex');
const baseline='fc40b21a',cache=new Map();
const git=p=>{if(!cache.has(p))cache.set(p,execFileSync('git',['show',baseline+':'+p],{cwd:root,maxBuffer:16*1024*1024}));return cache.get(p);};
const replacements={'web-player/lib/avr-transpiler.js':'candidate-transpiler.js','web-player/lib/avr-wasm-regions.js':'candidate-regions.js'};
const evidence=json('evidence.json');
for(const [p,h]of Object.entries(evidence.filesSha256))assert.equal(sha(/\.(gz|png)$/.test(p)?bytes(p):text(p)),h,p);
assert.equal(text('benchmark-replay-source.mjs'),text('benchmark-timed-source.mjs')
  .replace("'ls-tree','-r','--name-only'","'ls-tree','-r','--full-tree','--name-only'"));
const native=JSON.parse(git('web-player/wasm/device-build.json'));
assert.equal(sha(git('web-player/wasm/attiny13a.wasm')),native.artifacts['attiny13a.wasm']);
for(const [p,h]of Object.entries(native.inputs))assert.equal(sha(git(p).toString().replaceAll('\r\n','\n')),h,p);
const design=await import('data:text/javascript;base64,'+git('web-player/scripts/lib/runtime-control-design.mjs').toString('base64'));
let timings=0,warmups=0,snapshots=0,comparisons=0;
const parity=json('parity.json.gz');
for(const name of ['parity','screen','confirmation']){
 const r=json(name+'.json.gz');assert.equal(r.complete,true);assert.equal(r.results.length,5);
 assert.equal(r.provenance.nativeSha256,native.artifacts['attiny13a.wasm']);
 for(const [p,h]of Object.entries(r.provenance.sourceSha256))assert.equal(sha(
   replacements[p]?text(replacements[p]):p==='web-player/scripts/benchmark-region-budgets.mjs'?text('benchmark-timed-source.mjs'):
   git(p).toString().replaceAll('\r\n','\n')),h,p);
 for(const [p,h]of Object.entries(r.provenance.baselineGeneratorSha256))assert.equal(sha(git(p).toString().replaceAll('\r\n','\n')),h,p);
 for(const row of r.results){
  const expected=parity.results.find(x=>x.id===row.id);assert.ok(expected);assert.deepEqual(row.generated,expected.generated);
  const runs=[...row.warmups,...row.runs],first=runs[0];
  if(row.id.startsWith('kernel-'))assert.equal(first.finalState.clockDivisor,1);
  for(const run of runs){for(const k of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(run[k],first[k]);
    assert.deepEqual(run.finalState,first.finalState);snapshots+=run.checkpoints;}
  assert.equal(row.checkpointsCompared,(runs.length-1)*first.checkpoints);comparisons+=row.checkpointsCompared;
  if(name!=='parity'){assert.deepEqual(row.ratios,design.controlRatios(row.runs,r.parameters.trials));timings+=row.runs.length;warmups+=row.warmups.length;}
 }
}
const tap=gunzipSync(bytes('full-test.tap.gz')).toString().replaceAll('\r\n','\n');
for(const n of ['tests 1729','pass 1729','fail 0','skipped 0'])assert.ok(tap.includes('# '+n+'\n'));
const browser=json('browser.json');
assert.equal(browser.complete,true);assert.equal(browser.parityComplete,true);assert.equal(browser.realtimeComplete,true);
assert.equal(browser.runtimeSha256,native.artifacts['attiny13a.wasm']);assert.equal(browser.realtimeAccepted,false);
assert.equal(browser.parity.length,3);assert.equal(browser.audio.length,6);
for(const [p,h]of Object.entries(browser.sourceSha256))assert.equal(sha(replacements[p]?text(replacements[p]):git(p).toString().replaceAll('\r\n','\n')),h,p);
for(const row of browser.parity){assert.ok(row.irqCount>0);assert.equal(row.checkpoints.length,4);
 const id=(row.id==='hq4-chego-tiny'?'hq4-chego-auto':row.id)+'-physical';
 assert.equal(row.cpuSha256[1],parity.results.find(x=>x.id===id).generated.new.sha256);}
for(const row of browser.audio){assert.equal(row.accepted,false);assert.ok(row.last.underruns>0);
 assert.equal(row.visibilityStart,'visible');assert.equal(row.visibilityEnd,'visible');assert.deepEqual(row.visibilityChanges,[]);
 assert.ok(row.contextMs>=9000&&row.wallMs<12000&&row.maximumIRQs>0);assert.ok(row.states.every(x=>x.deviceFault===0));}
function sameRebuild(r){
 assert.equal(r.complete,true);assert.equal(r.results.length,5);
 for(const row of r.results){const expected=parity.results.find(x=>x.id===row.id);assert.ok(expected);
  assert.deepEqual(row.generated,expected.generated);
  for(const run of row.runs){for(const k of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(run[k],expected.runs[0][k]);
    assert.deepEqual(run.finalState,expected.runs[0].finalState);}}
}
if(existsSync(join(dir,'rebuild-parity.json.gz')))sameRebuild(json('rebuild-parity.json.gz'));
else assert.ok(process.argv.includes('--rebuild'),'Run the isolated reconstruction before static replay');
if(process.argv.includes('--rebuild')){
 const base=join(root,'build/replays');mkdirSync(base,{recursive:true});const target=mkdtempSync(join(base,'adaptive-region-budget-'));
 const put=(p,b)=>{const dest=join(target,p);mkdirSync(dirname(dest),{recursive:true});writeFileSync(dest,b);};
 const libs=execFileSync('git',['ls-tree','-r','--full-tree','--name-only',baseline,'web-player/lib'],{cwd:root,encoding:'utf8'}).trim().split('\n');
 const paths=new Set([...libs,...Object.keys(native.inputs),'web-player/package.json','web-player/firmware.json','web-player/hq4-firmware.json',
   'web-player/wasm/attiny13a.wasm','web-player/wasm/device-build.json','web-player/scripts/lib/runtime-control-design.mjs',
   'web-player/tests/fixtures/attiny13a-system-firmware.mjs','web-player/tests/analog-test-build.mjs',
   'web-player/tests/helpers/avr-phase-probe.mjs','web-player/tests/helpers/avr-test-state.mjs',
   'web-player/reports/attiny13a-instructions.json']);
 for(const p of paths)put(p,replacements[p]?bytes(replacements[p]):git(p));
 put('web-player/scripts/benchmark-region-budgets.mjs',bytes('benchmark-replay-source.mjs'));
 put('web-player/tests/avr-bounded-regions.test.mjs',bytes('contract-test-source.mjs'));
 execFileSync(process.execPath,['--test','web-player/tests/avr-bounded-regions.test.mjs'],{cwd:target,stdio:'inherit'});
 execFileSync(process.execPath,['web-player/scripts/benchmark-region-budgets.mjs','--baseline-ref',baseline,'--validate-only','--out','rebuild-parity.json'],{cwd:target,stdio:'inherit'});
 sameRebuild(JSON.parse(readFileSync(join(target,'rebuild-parity.json'),'utf8')));
 console.log('Isolated replay: '+target);
}
console.log(JSON.stringify({timings,warmups,snapshots,comparisons,fullRegressionTests:1729}));
