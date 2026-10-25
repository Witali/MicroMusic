import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {gunzipSync} from 'node:zlib';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const bytes=n=>readFileSync(new URL(n,import.meta.url));
const read=n=>bytes(n).toString('utf8').replaceAll('\r\n','\n'),json=n=>JSON.parse(read(n));
const sha=b=>createHash('sha256').update(b).digest('hex');
const git=(p,ref='9583026')=>execFileSync('git',['show',ref+':'+p],{cwd:root,maxBuffer:16*1024*1024});
for(const [p,ref,n]of [
  ['web-player/scripts/profile-device.mjs','3b10842f','profile-source.txt'],
  ['web-player/scripts/analyze-device-profiles.mjs','8a99fac9','analysis-source.txt'],
  ['web-player/tests/device-io-publication.test.mjs','ac738d45','publication-test-source.txt']])
  assert.equal(git(p,ref).toString().replaceAll('\r\n','\n'),read(n));
const uleb=value=>{const out=[];do{let b=value&127;value=Math.floor(value/128);out.push(b|(value?128:0));}while(value);return out;};
const str=s=>{const b=Buffer.from(s);return [...uleb(b.length),...b];};
function sections(b){
  let at=8;const result=[];
  const uint=()=>{let n=0,m=1,x;do{x=b[at++];n+=(x&127)*m;m*=128;}while(x&128);return n;};
  assert.deepEqual([...b.subarray(0,8)],[0,97,115,109,1,0,0,0]);
  while(at<b.length){const start=at,id=b[at++],size=uint(),payload=at;at+=size;assert.ok(at<=b.length);result.push({start,id,payload,end:at});}
  return result;
}
const executable=b=>Buffer.concat([b.subarray(0,8),...sections(b).filter(s=>s.id!==0).map(s=>b.subarray(s.start,s.end))]);
function namedRuntime(binary,functions){
  const entries=[...uleb(functions.length),...functions.flatMap(f=>[...uleb(f.index),...str(f.name)])];
  const module=str('micromusic.profile.native');
  const payload=[...str('name'),0,...uleb(module.length),...module,1,...uleb(entries.length),...entries];
  return Buffer.concat([binary,Buffer.from([0,...uleb(payload.length),...payload])]);
}
const nativeNames=json('runtime-names.json'),rawFiles=json('raw-manifest.json');
assert.equal(rawFiles.length,12);
const benchmark=JSON.parse(git('web-player/reports/adc-idle-20261025/long-confirmation.json'));
const summaries=new Map(),allCounts={profiles:0,workSamples:0};
for(const kind of ['kernel','hq4'])for(const version of ['before','after']){
  const file=kind+'-'+version+'.json',report=json(file),ref=version==='before'?'238aab2':'9583026';
  const manifest=JSON.parse(git('web-player/wasm/device-build.json',ref)),native=git('web-player/wasm/attiny13a.wasm',ref);
  const r=report.results[0];assert.equal(report.complete,true);assert.equal(report.results.length,1);
  assert.equal(report.provenance.runtimeRebuildByteEqual,true);
  assert.equal(report.provenance.runtimeSha256,sha(native));assert.equal(sha(native),manifest.artifacts['attiny13a.wasm']);
  assert.equal(report.provenance.executableSectionsSha256,sha(executable(native)));
  assert.equal(report.provenance.namedRuntimeSha256,sha(namedRuntime(native,nativeNames[version])));
  assert.equal(report.parameters.benchmarkControls,true);assert.equal(report.parameters.fastIdle,true);
  assert.equal(report.parameters.clock,'physical');assert.equal(report.parameters.repeats,3);
  assert.equal(report.parameters.frames,kind==='kernel'?4800:48000);assert.equal(report.parameters.rate,48000);
  assert.equal(report.parameters.operation,'capture');assert.equal(r.runs.length,3);
  if(version==='before')assert.ok(report.provenance.runtimeCommit.startsWith('238aab2'));
  else assert.equal(report.provenance.runtimeCommit,null);
  for(const [p,digest]of Object.entries(manifest.inputs))assert.equal(report.provenance.sourceSha256NormalizedLF[p],digest);
  for(const [p,digest]of Object.entries(report.provenance.sourceSha256NormalizedLF)){
    const source=p==='web-player/scripts/profile-device.mjs'?read('profile-source.txt'):
      git(p,Object.hasOwn(manifest.inputs,p)?ref:'9583026').toString().replaceAll('\r\n','\n');
    assert.equal(sha(source),digest,p);
  }
  const bench=benchmark.results.find(x=>x.id===(kind==='kernel'?'kernel-internal-20m-div1':'hq4-chego-auto-physical'));
  assert.equal(r.generatedOriginalSha256,bench.translationSha256);assert.deepEqual(r.finalState,bench.runs[0].finalState);
  const cpu=bytes('cpu/'+kind+'-named.wasm'),last=sections(cpu).at(-1);
  assert.equal(last.id,0);assert.equal(sha(cpu),r.generatedNamedSha256);
  assert.equal(sha(cpu.subarray(0,last.start)),r.generatedOriginalSha256);
  assert.equal(sha(executable(cpu)),r.generatedExecutableSectionsSha256);
  const known=new Set(nativeNames[version].map(f=>f.name));
  for(const run of r.runs){
    assert.equal(run.productionEquality,true);assert.equal(run.architectureSha256,r.referenceArchitectureSha256);
    assert.equal(run.rawPcmSha256,bench.runs[0].rawSha256);
    const entry=rawFiles.find(x=>x.summary===file&&x.repeat===run.repeat);assert.ok(entry);
    const compressed=bytes(entry.file);assert.equal(sha(compressed),entry.compressedSha256);
    const raw=gunzipSync(compressed);assert.equal(sha(raw),entry.rawSha256);assert.equal(sha(raw),run.profileSha256);
    const profile=JSON.parse(raw),nodes=new Map(profile.nodes.map(n=>[n.id,n])),parents=new Map(),counts=new Map();
    for(const n of profile.nodes)for(const child of n.children||[])parents.set(child,n.id);
    let work=0;
    for(const id of profile.samples){
      const stack=[];for(let at=id;at!==undefined;at=parents.get(at)){
        const node=nodes.get(at);assert.ok(node);stack.push(node.callFrame);
      }
      if(!stack.some(f=>f.functionName.replace(/^\$/,'')==='capturePhysical'&&/\/attiny13a-runtime\.js$/.test(f.url)))continue;
      work++;const seen=new Set();
      for(const [i,f]of stack.entries()){
        const name=f.functionName.replace(/^\$/,'');if(!known.has(name)||seen.has(name))continue;seen.add(name);
        const c=counts.get(name)||{self:0,inclusive:0};c.inclusive++;if(i===0)c.self++;counts.set(name,c);
      }
    }
    assert.equal(profile.samples.length,run.samples);assert.equal(work,run.workStackSamples);
    for(const name of known){const c=counts.get(name)||{self:0,inclusive:0},f=run.workFrames.find(x=>x.name===name);
      assert.equal(c.self,f?.selfSamples??0,name);assert.equal(c.inclusive,f?.inclusiveSamples??0,name);}
    allCounts.profiles++;allCounts.workSamples+=work;
  }
  summaries.set(file,report);
}
for(const kind of ['kernel','hq4']){
  const a=summaries.get(kind+'-before.json').results[0],b=summaries.get(kind+'-after.json').results[0];
  assert.equal(a.referenceArchitectureSha256,b.referenceArchitectureSha256);assert.equal(a.generatedOriginalSha256,b.generatedOriginalSha256);
}
for(const version of ['before','after']){
  const a=json(version+'-analysis.json');assert.equal(a.complete,true);assert.equal(a.profiles,6);assert.equal(a.callTrace,null);
  for(const row of a.results){
    const report=[...summaries.values()].find(x=>x.results[0].id===row.id&&x.provenance.runtimeSha256===a.runtimeSha256);
    assert.ok(report);const r=report.results[0],samples=r.runs.reduce((n,x)=>n+x.workStackSamples,0);
    assert.equal(row.samples,samples);assert.equal(row.profiles,3);
    for(const f of row.frames){
      const observed=r.runs.map(x=>x.workFrames.find(y=>(y.key??y.name)===(f.key??f.name)));
      assert.equal(f.selfSamples,observed.reduce((n,x)=>n+(x?.selfSamples??0),0));
      assert.equal(f.inclusiveSamples,observed.reduce((n,x)=>n+(x?.inclusiveSamples??0),0));
      assert.equal(f.selfPercent,100*f.selfSamples/samples);assert.equal(f.inclusivePercent,100*f.inclusiveSamples/samples);
    }
  }
}
const inventory=json('register-inventory.json'),source=git('web-player/native/peripherals/device.c').toString().replaceAll('\r\n','\n');
assert.equal(inventory.deviceSourceSha256,sha(source));
assert.equal(inventory.officialMapSha256,sha(git('web-player/lib/attiny13a-registers.js').toString().replaceAll('\r\n','\n')));
assert.equal(read('mirror-source.txt'),source.match(/^static void mirror\(void\) \{[\s\S]*?^\}/m)[0]+'\n');
assert.equal(inventory.registers.length,31);assert.equal(inventory.registers.filter(r=>r.group==='software-or-reset').length,16);
const wat=read('mirror.wat');assert.equal([...wat.matchAll(/\(i32\.load(?=\s)/g)].length,1);
assert.deepEqual([...wat.matchAll(/i32\.store8 offset=(\d+)/g)].map(x=>Number(x[1])).sort((a,b)=>a-b),inventory.registers.map(r=>r.data).sort((a,b)=>a-b));
for(const line of ['tests 3','pass 3','fail 0','skipped 0'])assert.ok(read('publication-test.tap').includes('# '+line+'\n'));
assert.deepEqual(allCounts,{profiles:12,workSamples:13723});
console.log(JSON.stringify({...allCounts,benchmarkMatchedCases:2,nativeVersions:2,publicationTests:3,mirrorStores:31,mirrorPointerLoads:1}));
