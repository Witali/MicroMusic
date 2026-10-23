import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{input:{type:'string',multiple:true},
  calls:{type:'string',default:'build/traces/current/summary.json'},
  'out-dir':{type:'string',default:'build/profiles/analysis'}}});
const inputs=values.input??['current-firmware','kernel-compatible-direct','kernel-physical-direct',
  'kernel-internal-20m','kernel-clki-20m-div1','kernel-clki-20m-div256'].map(p=>'build/profiles/'+p);
const out=resolve(root,values['out-dir']);mkdirSync(out,{recursive:true});
const sha=b=>createHash('sha256').update(b).digest('hex');
const read=p=>JSON.parse(readFileSync(p,'utf8'));
const save=(p,v)=>writeFileSync(join(out,p),JSON.stringify(v,null,2)+'\n');
const repoPath=p=>relative(root,p).replaceAll('\\','/');
const median=v=>{const a=[...v].sort((a,b)=>a-b);return a.length%2?a[a.length>>1]:(a[a.length/2-1]+a[a.length/2])/2;};
const report={schema:'micromusic-device-profile-analysis-v1',createdAt:new Date().toISOString(),
  method:'Pool self/inclusive sample counts across five fresh-state profiles per case, divided by samples with the relevant public run/capturePhysical ancestor. Self samples are disjoint leaf-frame observations. Inclusive samples overlap and must not be added. O3/V8 inlining remains attributed to containing frames. Counts identify source-level function entries in a separate diagnostic binary and are never used to assign production time. Raw first-repeat profiles are copied as representatives; all-repeat hashes and original paths are retained. All percentages and wall times are profiling observations, not exact exclusive time or unprofiled benchmark timings.',
  results:[]};
let profileCount=0;
for(const input of inputs){
  const dir=resolve(root,input),inputBytes=readFileSync(join(dir,'summary.json')),summary=JSON.parse(inputBytes);
  assert.equal(summary.complete,true,input);
  if(report.runtimeSha256)assert.equal(summary.provenance.runtimeSha256,report.runtimeSha256);
  else{
    report.runtimeSha256=summary.provenance.runtimeSha256;report.host=summary.host;report.node=summary.node;
    report.nativeProvenance=summary.provenance;
    copyFileSync(join(dir,'runtime-functions.json'),join(out,'runtime-functions.json'));
  }
  for(const result of summary.results){
    let sampleCount=0,allSamples=0;const frames=new Map(),categories=new Map(),evidence=[];
    for(const run of result.runs){
      assert.equal(run.productionEquality,true,result.id);
      sampleCount+=run.workStackSamples;allSamples+=run.samples;profileCount++;
      for(const f of run.workFrames){
        const key=f.key??f.name,row=frames.get(key)??{name:f.name,category:f.category,selfSamples:0,inclusiveSamples:0};
        row.selfSamples+=f.selfSamples;row.inclusiveSamples+=f.inclusiveSamples;frames.set(key,row);
      }
      for(const c of run.workLeafCategories)categories.set(c.category,(categories.get(c.category)||0)+c.samples);
      const file=join(dir,run.profile);assert.equal(sha(readFileSync(file)),run.profileSha256);
      evidence.push({repeat:run.repeat,path:repoPath(file),sha256:run.profileSha256,
        workWallMs:run.workWallMs,workSamples:run.workStackSamples,allSamples:run.samples,sampleDeltasUs:run.sampleDeltasUs,
        productionEquality:true,rawPcmSha256:run.rawPcmSha256,architectureSha256:run.architectureSha256});
    }
    assert.ok(sampleCount>0,result.id+' has no attributed samples');
    assert.equal([...categories.values()].reduce((a,b)=>a+b,0),sampleCount);
    const representative=result.id+'.cpuprofile';copyFileSync(join(dir,result.runs[0].profile),join(out,representative));
    const row={id:result.id,parameters:summary.parameters,profiles:result.runs.length,samples:sampleCount,allSamples,
      workWallMs:{median:median(evidence.map(r=>r.workWallMs)),min:Math.min(...evidence.map(r=>r.workWallMs)),max:Math.max(...evidence.map(r=>r.workWallMs))},
      categories:[...categories].map(([category,samples])=>({category,samples,percent:100*samples/sampleCount})).sort((a,b)=>b.samples-a.samples),
      frames:[...frames.values()].map(f=>({...f,selfPercent:100*f.selfSamples/sampleCount,
        inclusivePercent:100*f.inclusiveSamples/sampleCount})).sort((a,b)=>b.selfSamples-a.selfSamples||b.inclusiveSamples-a.inclusiveSamples),
      representativeProfile:representative,evidence,inputSummary:{path:repoPath(join(dir,'summary.json')),sha256:sha(inputBytes),
        parameters:summary.parameters,provenance:summary.provenance}};
    report.results.push(row);
  }
}
const callFile=resolve(root,values.calls),calls=read(callFile);
assert.equal(calls.complete,true);assert.equal(calls.productionRuntimeSha256,report.runtimeSha256);
assert.ok(calls.results.every(r=>r.productionEquality));
copyFileSync(callFile,join(out,'call-counts-and-prefix.json'));
report.callTrace={file:'call-counts-and-prefix.json',sha256:sha(readFileSync(callFile)),
  cases:calls.results.length,selectedFunctions:calls.functions.length,allCasesMatchProduction:true};
report.profiles=profileCount;report.samples=report.results.reduce((n,r)=>n+r.samples,0);report.complete=true;
save('summary.json',report);
console.table(report.results.map(r=>({case:r.id,samples:r.samples,top:r.frames[0].name,
  self:r.frames[0].selfPercent.toFixed(1)+'%',profiledMs:r.workWallMs.median.toFixed(1)})));
console.log(`${profileCount}profiles/${report.samples}work samples and${calls.results.length}counter traces verified. Output: ${repoPath(out)}`);
