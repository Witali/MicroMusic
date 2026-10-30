// Audit retained source-entry counts; never infer elapsed time from them.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{input:{type:'string'},control:{type:'string'}}});
assert.ok(values.input&&values.control,'Pass --input and --control completed trace summaries');
const read=path=>readFileSync(resolve(root,path));
const hash=b=>createHash('sha256').update(b).digest('hex');
const source=path=>read(path).toString().replaceAll('\r\n','\n');
const manifest=JSON.parse(source('web-player/wasm/device-build.json'));
const runtimeHash=hash(read('web-player/wasm/attiny13a.wasm'));
assert.equal(runtimeHash,manifest.artifacts['attiny13a.wasm']);
function load(path,deadline){
  const r=JSON.parse(read(path));assert.equal(r.complete,true);assert.equal(r.policy.deadlineCounters,deadline);
  assert.equal(r.productionRuntimeSha256,runtimeHash);assert.equal(new Set(r.functions.map(f=>f.name)).size,r.functions.length);
  assert.equal(new Set(r.results.map(x=>x.id)).size,r.results.length);
  for(const [path,expected]of Object.entries(r.sourceSha256NormalizedLF)){
    const rel=relative(root,resolve(root,path));assert.ok(rel&&!isAbsolute(rel)&&!rel.startsWith('..'));
    assert.equal(hash(source(path)),expected,'Changed captured source '+path);
  }
  for(const [path,expected]of Object.entries(manifest.inputs))assert.equal(r.sourceSha256NormalizedLF[path],expected);
  for(const x of r.results){
    assert.equal(x.productionEquality,true);assert.equal(x.counts.length,r.functions.length);
    x.counts.forEach((c,n)=>{
      const {count,...metadata}=c;assert.deepEqual(metadata,r.functions[n]);assert.equal(metadata.id,n);
      assert.match(count,/^(0|[1-9][0-9]*)$/);assert.ok(BigInt(count)<(1n<<64n));
    });
  }
  return r;
}
const a=load(values.input,true),b=load(values.control,false);
const count=(x,name)=>{const c=x.counts.find(c=>c.name===name);assert.ok(c,'Missing '+name);return BigInt(c.count);};
for(const x of a.results){
  const c=name=>count(x,name),d=x.deadline;assert.ok(d&&d.missReasonsOverlap&&d.counterResetClearsPendingReasons);
  assert.equal(c('next_event'),c('next_event:hit')+c('next_event:miss'));
  assert.equal(c('next_event:miss'),c('next_event_scan'));assert.equal(c('next_event_scan'),c('next_event_scan:exit'));
  assert.equal(c('duration'),c('duration:scan')+c('duration:outside-scan'));
  assert.equal(c('at_half'),['never','due','unknown-clki','convert'].reduce((n,k)=>n+c('at_half:'+k),0n));
  assert.equal(c('elapse'),['zero','positive','backwards'].reduce((n,k)=>n+c('elapse:'+k),0n));
  assert.ok(c('elapse:zero-cached-future')<=c('elapse:zero'));assert.equal(c('elapse:backwards'),0n);
  for(const [key,name]of Object.entries({queries:'next_event',hits:'next_event:hit',misses:'next_event:miss',
    noPendingReason:'miss:no-pending-reason',scanDurationCalls:'duration:scan',outsideScanDurationCalls:'duration:outside-scan',
    zeroElapseCachedFuture:'elapse:zero-cached-future'}))assert.equal(BigInt(d[key]),c(name));
  assert.equal(d.reasons.reduce((n,z)=>n+BigInt(z.attempts),0n),c('deadline_invalidate'));
  for(const z of d.reasons){assert.equal(BigInt(z.attempts),c('invalidate:'+z.reason));
    assert.equal(BigInt(z.validInvalidations),c('invalidate-valid:'+z.reason));
    assert.equal(BigInt(z.missesWithReason),c('miss:'+z.reason));
    assert.ok(BigInt(z.validInvalidations)<=BigInt(z.attempts));assert.ok(BigInt(z.missesWithReason)<=c('next_event:miss'));}
}
let comparisons=0;
for(const x of b.results){
  const y=a.results.find(y=>y.id===x.id);assert.ok(y,'Missing control workload');
  for(const key of ['frames','sampleRate','channels','cycles','flashSha256','rawPcmSha256','pinSha256'])assert.equal(y[key],x[key]);
  for(const c of x.counts){assert.equal(count(y,c.name),BigInt(c.count),x.id+' '+c.name);comparisons++;}
}
console.log(JSON.stringify({deadlineCases:a.results.length,controlCases:b.results.length,
  commonSourceEntryComparisons:comparisons,productionEquality:true,sourceAndNativeHashes:true,
  elapsedTimeMeasured:false}));
