import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
const root=fileURLToPath(new URL('../../../',import.meta.url)),dir=fileURLToPath(new URL('./',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex'),bytes=p=>readFileSync(join(dir,p)),json=p=>JSON.parse(bytes(p));
const inputs=new Map(),baseline='fc40b21a';
const git=p=>{if(!inputs.has(p))inputs.set(p,execFileSync('git',['show',baseline+':'+p],{cwd:root,maxBuffer:16*1024*1024}).toString().replaceAll('\r\n','\n'));return inputs.get(p);};
const evidence=json('evidence.json');
for(const [p,h]of Object.entries(evidence.filesSha256))assert.equal(sha(p.endsWith('.gz')?bytes(p):bytes(p).toString().replaceAll('\r\n','\n')),h,p);
const pooled=json('analysis.json');let profiles=0,samples=0;
assert.equal(pooled.complete,true);assert.equal(pooled.callTrace,null);
for(const label of ['music','clki']){
 const summary=json(label+'/summary.json');assert.equal(summary.complete,true);
 assert.equal(summary.git.head,'fc40b21ae7411171149f263b32a0c8d0e1889001');
 assert.equal(summary.provenance.runtimeSha256,pooled.runtimeSha256);
 for(const [p,h]of Object.entries(summary.provenance.sourceSha256NormalizedLF))assert.equal(sha(git(p)),h,p);
 const native=new Set(json(label+'/runtime-functions.json').map(x=>x.name));
 for(const result of summary.results){
  const combined=new Map();let count=0;
  for(const run of result.runs){
   assert.equal(run.productionEquality,true);assert.equal(run.architectureSha256,result.referenceArchitectureSha256);
   const raw=gunzipSync(bytes(label+'/'+run.profile+'.gz'));assert.equal(sha(raw),run.profileSha256);
   const profile=JSON.parse(raw),nodes=new Map(profile.nodes.map(x=>[x.id,x])),parent=new Map();
   for(const node of nodes.values())for(const child of node.children||[])parent.set(child,node.id);
   const counts=new Map();let work=0;
   for(const id of profile.samples){
    const stack=[];for(let at=id;at!==undefined;at=parent.get(at)){const node=nodes.get(at);assert.ok(node);stack.push(node.callFrame);}
    if(!stack.some(f=>f.functionName==='capturePhysical'&&/\/attiny13a-runtime\.js$/.test(f.url)))continue;
    work++;const seen=new Set();
    stack.forEach((f,n)=>{
     const plain=f.functionName.replace(/^\$/,''),key=native.has(plain)||plain.startsWith('cpu.')?plain:
       f.url?.startsWith('wasm:')?plain+'@'+f.url:f.functionName+'@'+f.url+':'+f.lineNumber;
     if(seen.has(key))return;seen.add(key);
     if(!counts.has(key))counts.set(key,{self:0,inclusive:0});const c=counts.get(key);c.inclusive++;if(n===0)c.self++;
    });
   }
   assert.equal(profile.samples.length,run.samples);assert.equal(work,run.workStackSamples);
   assert.equal(counts.size,run.workFrames.length);
   for(const f of run.workFrames){
    assert.deepEqual(counts.get(f.key),{self:f.selfSamples,inclusive:f.inclusiveSamples});
    const c=combined.get(f.key)||{self:0,inclusive:0};c.self+=f.selfSamples;c.inclusive+=f.inclusiveSamples;combined.set(f.key,c);
   }
   profiles++;samples+=work;count+=work;
  }
  const row=pooled.results.find(x=>x.id===result.id);assert.ok(row);assert.equal(row.samples,count);
  assert.equal(combined.size,row.frames.length);
  for(const f of row.frames){assert.deepEqual(combined.get(f.key),{self:f.selfSamples,inclusive:f.inclusiveSamples});
    assert.equal(f.selfPercent,100*f.selfSamples/count);assert.equal(f.inclusivePercent,100*f.inclusiveSamples/count);}
 }
}
assert.equal(profiles,12);assert.equal(samples,12383);assert.equal(pooled.profiles,profiles);assert.equal(pooled.samples,samples);
console.log(JSON.stringify({profiles,samples,cases:pooled.results.length,runtimeSha256:pooled.runtimeSha256}));
