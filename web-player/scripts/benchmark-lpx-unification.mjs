import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {fileURLToPath} from 'node:url';
import {createEncoder} from '../lpx/encoder.js';
import {createDecoder} from '../lpx/codec.js';

const root=new URL('../../',import.meta.url);
const revision='b428477f5e4f39797dc7c91b53c01469d7b4944f';
const path='web-player/lpx/encoder-adaptive.wasm';
const old=execFileSync('git',['show',`${revision}:${path}`],{cwd:fileURLToPath(root),maxBuffer:4*1024*1024});
const current=readFileSync(new URL(path,root));
const beforeBuild=JSON.parse(execFileSync('git',['show',`${revision}:web-player/lpx/encoder-adaptive-build.json`],{cwd:fileURLToPath(root)}));
const afterBuild=JSON.parse(readFileSync(new URL('web-player/lpx/encoder-adaptive-build.json',root)));
assert.equal(beforeBuild.compiler,afterBuild.compiler,'paired compiler');
assert.deepEqual(beforeBuild.flags,afterBuild.flags,'paired build flags');
const encoders=await Promise.all([old,current].map(createEncoder));
const decode=await createDecoder(readFileSync(new URL('web-player/lpx/decoder.wasm',root)));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const median=values=>[...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];
const warmups=3,repetitions=7;
const rows=[];
// Aligned frames keep this a successful-encoding timing comparison. Partial
// packets and the baseline's short-input no-fit errors belong to the tests.
for(const [level,rate,samples] of [[3,8000,640],[4,12000,2560],[6,16000,640],[8,8000,2560]]) {
  const pcm=Int16Array.from({length:samples},(_,i)=>Math.round(5000*Math.sin(i*.17)+1000*Math.sin(i*.037)));
  const options={accuracy:true,calls:4},times=[[],[]];let expected;
  for(let repetition=-warmups;repetition<repetitions;++repetition) {
    // Alternate order after a warm-up of both instances.
    for(const index of repetition&1?[1,0]:[0,1]) {
      const start=performance.now(),bytes=encoders[index](pcm,rate,level,()=>{},options),elapsed=performance.now()-start;
      if(!expected)expected=bytes;else assert.deepEqual(bytes,expected);
      if(repetition>=0)times[index].push(elapsed);
    }
  }
  assert.equal(decode(expected).samples,samples);
  rows.push({level,rate,samples,bytes:expected.length,sha256:sha(expected),beforeMs:times[0],afterMs:times[1],
    beforeMedianMs:median(times[0]),afterMedianMs:median(times[1]),ratio:median(times[0])/median(times[1])});
  console.log(`P${level}/${rate}/${samples}: ${rows.at(-1).ratio.toFixed(3)}x; identical bytes`);
}
const report={schema:'lpx-unification-benchmark-v1',baselineRevision:revision,node:process.version,
  compiler:afterBuild.compiler,flags:afterBuild.flags,
  platform:process.platform,arch:process.arch,backend:'scalar WASM',calls:4,warmups,repetitions,
  beforeModuleBytes:old.length,afterModuleBytes:current.length,beforeSha256:sha(old),afterSha256:sha(current),
  timing:'Alternating paired warm encodes in one Node process; includes encoding and verification; excludes input preparation and module loading.',rows};
mkdirSync(new URL('build/',root),{recursive:true});
writeFileSync(new URL('build/lpx-unification-benchmark.json',root),JSON.stringify(report,null,2)+'\n');
