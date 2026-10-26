// Offline audit only: no capture, compilation, download or execution timing.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,isAbsolute,relative,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {attributeAvrProfile} from './lib/avr-profile-attribution.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{input:{type:'string'},firmware:{type:'string'},
  'out-file':{type:'string',default:'build/profiles/attribution-audit.json'},help:{type:'boolean'}}});
if(values.help){
  console.log('node web-player/scripts/audit-device-profile.mjs --input build/profiles/case [--firmware id] [--out-file build/profiles/audit.json]');
  process.exit(0);
}
assert.ok(values.input,'--input profile directory is required');
function within(base,path){
  const absolute=resolve(base,path),local=relative(base,absolute);
  assert.ok(local&&!isAbsolute(local)&&local!=='..'&&!local.startsWith('..'+sep),'Path outside expected directory');
  return absolute;
}
const dir=within(root,values.input),output=within(resolve(root,'build'),resolve(root,values['out-file']));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const load=name=>{const bytes=readFileSync(within(dir,name));return {value:JSON.parse(bytes),sha256:hash(bytes)};};
const summary=load('summary.json'),runtime=load('runtime-functions.json');
assert.equal(summary.value.complete,true,'Incomplete source profile');
const operation=summary.value.parameters.operation??'capture';
const selected=summary.value.results.filter(row=>!values.firmware||row.id===values.firmware);
assert.ok(selected.length,'No matching firmware');
const counts=rows=>Object.fromEntries(rows.map(row=>[row.category,row.samples]).sort(([a],[b])=>a.localeCompare(b)));
const results=[];
for(const row of selected){
  assert.ok(typeof row.id==='string'&&/^[a-zA-Z0-9_-]+$/.test(row.id),'Invalid firmware ID');
  const generated=load(row.id+'-functions.json');
  const functions=[...runtime.value,...generated.value.functions];
  assert.ok(row.runs.length,'No source runs');
  for(const run of row.runs){
    assert.equal(run.productionEquality,true,'Source profile lacks production parity');
    const profile=load(run.profile);assert.equal(profile.sha256,run.profileSha256,'Raw profile hash mismatch');
    const attribution=attributeAvrProfile(profile.value,{functions,operation,requestedIntervalUs:summary.value.parameters.intervalUs});
    assert.equal(attribution.all.samples,run.samples);assert.equal(attribution.workAncestry.samples,run.workStackSamples);
    assert.deepEqual(counts(attribution.all.categories),counts(run.allLeafCategories),'Prior all-sample attribution differs');
    assert.deepEqual(counts(attribution.workAncestry.categories),counts(run.workLeafCategories),'Prior work attribution differs');
    results.push({firmware:row.id,repeat:run.repeat,profileSha256:profile.sha256,
      generatedMetadataSha256:generated.sha256,priorCountsMatch:true,attribution});
  }
}
const sourceHashes=Object.fromEntries(['audit-device-profile.mjs','lib/avr-profile-attribution.mjs'].map(path=>
  [path,hash(readFileSync(new URL(path,import.meta.url),'utf8').replaceAll('\r\n','\n'))]));
const report={schema:'micromusic-device-profile-audit-v1',sourceSummarySha256:summary.sha256,
  runtimeMetadataSha256:runtime.sha256,runtimeSha256:summary.value.provenance.runtimeSha256,
  sourceHashes,meaning:'Offline replay of retained captures; no current-runtime performance or profiler-overhead claim.',results};
mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({profiles:results.length,allPriorCountsMatch:true,
  samples:results.reduce((sum,row)=>sum+row.attribution.all.samples,0),output:relative(root,output).replaceAll('\\','/')}));
