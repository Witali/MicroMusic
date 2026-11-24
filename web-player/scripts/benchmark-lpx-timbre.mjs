// Synthetic same-rate quality comparison; never reads user recordings.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {parseArgs} from 'node:util';
import {createEncoder} from '../lpx/encoder.js';
import {createDecoder} from '../lpx/codec.js';
import {timbreCases,measureTimbre} from '../tests/helpers/lpx-timbre-cases.mjs';

const {values}=parseArgs({options:{baseline:{type:'string',default:'f1f9a0d9fc76fdc52f5787b54f2ba5471bd3db8c'}}});
const root=new URL('../../',import.meta.url);
const baseline=execFileSync('git',['show',`${values.baseline}:web-player/lpx/encoder-adaptive.wasm`],{cwd:root,maxBuffer:16*1024*1024,windowsHide:true});
const current=readFileSync(new URL('../lpx/encoder-adaptive.wasm',import.meta.url));
const decoder=readFileSync(new URL('../lpx/decoder.wasm',import.meta.url));
const encoders={old:await createEncoder(baseline),current:await createEncoder(current)};
const decode=await createDecoder(decoder),options={accuracy:true,calls:0};
const median=a=>a.slice().sort((x,y)=>x-y)[Math.floor(a.length/2)];
const rms=(pcm,start=0)=>Math.sqrt(pcm.subarray(start).reduce((sum,v)=>sum+v*v,0)/(pcm.length-start));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex'),rows=[];
for(const encode of Object.values(encoders))encode(new Int16Array(161),8000,4,()=>{},options);
for(const rate of [8000,12000,16000])for(const source of timbreCases(rate).filter(c=>c.name!=='silence'))for(const level of [3,4,6,8]) {
  const sourceTailRms=rms(source.reference,Math.floor(source.reference.length*.75));
  const row={name:source.name,rate,level,samples:source.reference.length,sourceTailRms};
  for(const key of rows.length%2?['current','old']:['old','current']) {
    const times=[];let bytes;
    for(let repetition=0;repetition<3;++repetition) {
      const start=performance.now();bytes=encoders[key](source.reference,rate,level,()=>{},options);times.push(performance.now()-start);
    }
    const pcm=decode(bytes).pcm,tailRms=rms(pcm,Math.floor(pcm.length*.75));
    row[key]={...measureTimbre(source.reference,pcm,rate,source.partials),bytes:bytes.length,
      encodeMilliseconds:median(times),encodeMillisecondsAll:times,tailRms,
      rmsGain:rms(pcm)/rms(source.reference),clipFraction:pcm.filter(v=>v<=-32760||v>=32760).length/pcm.length};
    row[key].boundedGainAndTail=row[key].energyRatio<=4&&tailRms<=Math.max(64,3*sourceTailRms);
  }
  rows.push(row);
}
const safe=rows.filter(r=>r.old.boundedGainAndTail);
const regressions=safe.filter(r=>r.current.spectralShapeError>r.old.spectralShapeError+.05
  ||r.current.envelopeError>r.old.envelopeError+.1||r.current.retainedPartials<r.old.retainedPartials
  ||r.current.minimumPartialRetention<r.old.minimumPartialRetention-.1);
const report={baselineRevision:values.baseline,encoderBaselineSha256:sha(baseline),encoderCurrentSha256:sha(current),decoderSha256:sha(decoder),
  method:'7 deterministic synthetic families x 3 actual rates x 4 levels; scalar accuracy, calls=0. Three warm calls per case, alternating old/current order. Same-rate metrics, no gain or delay fitting.',
  summary:{cases:rows.length,baselineBounded:safe.length,currentBounded:rows.filter(r=>r.current.boundedGainAndTail).length,
    substantialRegressions:regressions.map(r=>({name:r.name,rate:r.rate,level:r.level})),
    totals:Object.fromEntries(['old','current'].map(k=>[k,{bytes:rows.reduce((s,r)=>s+r[k].bytes,0),
      sumMedianEncodeMs:rows.reduce((s,r)=>s+r[k].encodeMilliseconds,0),
      stableMeanSpectralError:safe.reduce((s,r)=>s+r[k].spectralShapeError,0)/safe.length,
      stableMeanEnvelopeError:safe.reduce((s,r)=>s+r[k].envelopeError,0)/safe.length}]))},rows};
mkdirSync(new URL('build/',root),{recursive:true});
writeFileSync(new URL('build/lpx-timbre-benchmark.json',root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report.summary,null,2));
