import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {ROOT,HTML,loadReference,encodeReference,decodeReference,validateContainer,main} from './lpc2-reference-cli.mjs';

const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const source=Array.from({length:3001},(_,i)=>{
  const envelope=i<900?.15:i<1800?.4:.08;
  return envelope*(Math.sin(2*Math.PI*(i<1500?220:340)*i/7500)+.2*Math.sin(i*1.971));
});
const input={sampleRate:7500,samples:source};
const model=encodeReference(input);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));

test('native LPC2 encoding is deterministic and records exact original-source provenance',async()=>{
  const first=await model,second=await encodeReference(input),{bytes,decoded,engine}=first;
  assert.deepEqual(bytes,second.bytes);
  assert.deepEqual(validateContainer(bytes),{version:2,sr:7500,hop:150,window:240,frames:21,samples:3001,bits:decoded.meta.payloadBits});
  assert.equal(decoded.coefficients.length,30010);
  for(const pcm of Object.values(decoded.outputs))assert.equal(pcm.length,3001);
  assert.deepEqual(decoded.independentAgreement,{header:true,frames:true,lsfAndPredictorTrajectoryExact:true});
  const html=(await fs.readFile(HTML,'utf8')).replace(/\r\n/g,'\n');
  const start=html.indexOf('const LPC_CHIRP='),end=html.indexOf('function splitForBlocks(',start);
  assert.equal(sha(html.slice(start,end)),engine.provenance.core.sha256NormalizedLf);
  assert.equal(html.slice(0,start).split('\n').length,engine.provenance.core.startLine);
  assert.equal(html.slice(0,end).split('\n').length-1,engine.provenance.core.endLine);
  assert.equal(decoded.meta.pre,Math.fround(.85));
  assert.equal(decoded.meta.pitchMin,65);assert.equal(decoded.meta.pitchMax,850);
  await assert.rejects(()=>encodeReference({...input,config:{pitchGuideHz:[220]}}),/external pitch guides/);
});

test('exported samplewise predictors reproduce independent existing LPX3 decoder PCM exactly',async()=>{
  const {bytes,decoded,engine}=await model,n=decoded.meta.samples,bits=3,blocksize=80,nb=Math.ceil(n/blocksize);
  const codes=Uint8Array.from({length:n},(_,i)=>(i*7+3)%8);
  const payload=Buffer.alloc(Math.ceil(n*bits/8));
  for(let i=0;i<n;i++)for(let k=0;k<bits;k++)payload[(i*bits+k)>>3]|=((codes[i]>>k)&1)<<((i*bits+k)&7);
  const header=Buffer.alloc(24);header.write('LPX3');header[4]=1;header[5]=bits;
  header.writeUInt16LE(7500,6);header.writeUInt32LE(n,8);header.writeUInt32LE(bytes.length,12);
  header.writeUInt16LE(blocksize,16);header.writeUInt32LE(nb,20);
  const blob=Buffer.concat([header,bytes,Buffer.alloc(nb,128),payload]);
  const actual=engine.pure.decodeLPX3(blob.buffer.slice(blob.byteOffset,blob.byteOffset+blob.byteLength)).pcm;
  const expected=new Float32Array(n),history=new Float64Array(10);let last=0;
  for(let i=0;i<n;i++){
    let acc=0;for(let k=0;k<10;k++)acc+=decoded.coefficients[i*10+k]*history[k];
    const pre=clamp((codes[i]-4)*.001-acc,-2,2);
    for(let k=9;k>0;k--)history[k]=history[k-1];history[0]=pre;
    const x=pre+decoded.meta.pre*last;last=clamp(x,-2,2);expected[i]=clamp(x,-1,1);
  }
  assert.equal(actual.length,n);
  for(let i=0;i<n;i++)assert.equal(actual[i],expected[i],`sample ${i}`);
});

test('strict wrapper rejects structural corruption and noncanonical lengths/padding',async()=>{
  const {bytes}=await model;
  for(const mutate of [b=>b[0]=0,b=>b[4]=9,b=>b.writeUInt16LE(0,6),b=>b.writeUInt32LE(1,12),b=>b.writeUInt32LE(0,20)]){
    const corrupt=Buffer.from(bytes);mutate(corrupt);assert.throws(()=>validateContainer(corrupt));
  }
  assert.throws(()=>validateContainer(bytes.subarray(0,-1)));
  assert.throws(()=>validateContainer(Buffer.concat([bytes,Buffer.of(0)])));
  const bits=bytes.readUInt32LE(20);
  if(bits%8){const corrupt=Buffer.from(bytes);corrupt[corrupt.length-1]|=0x80;assert.throws(()=>validateContainer(corrupt),/padding/);}
});

test('clamp observer preserves every output sample and distinguishes headroom from protective clipping',async()=>{
  const loud=await encodeReference({sampleRate:7500,samples:source.map(x=>x*12)});
  const without=await decodeReference(loud.engine,loud.bytes,[0,.1,.35],{audit:false});
  for(const post of ['0','0.1','0.35'])assert.deepEqual(loud.decoded.outputs[post],without.outputs[post]);
  assert.ok(Object.values(loud.decoded.clippingAudit).some(a=>a.rawOutput.samplesOutsideUnitRange>0));
  assert.ok(Object.values(loud.decoded.clippingAudit).every(a=>a.protectiveClamps['8'].calls>=source.length*2));
  const frames=loud.decoded.frames.map(frame=>({...frame,energy:31}));
  const forced=Buffer.from(new Uint8Array(loud.engine.api.packLPC2(loud.decoded.meta,frames).buffer));
  const saturated=await decodeReference(loud.engine,forced,[0]);
  assert.ok(saturated.clippingAudit['0'].protectiveClamps['8'].outside>0);
  assert.ok(saturated.clippingAudit['0'].protectiveClamps['8'].maxUnclippedAbs>8);
});

test('parameter-only CLI decode reproduces raw PCM and predictors with no source samples',async()=>{
  const {bytes,decoded}=await model,build=path.resolve(ROOT,'build');
  await fs.mkdir(build,{recursive:true});
  const temporary=await fs.mkdtemp(path.join(build,'test-lpc2-reference-'));
  try{
    const base=path.join(temporary,'input.lp2'),out=path.join(temporary,'output');
    await fs.writeFile(base,bytes);await main(['--base',base,'--output',out]);
    assert.deepEqual(await fs.readFile(path.join(out,'base.lp2')),bytes);
    const raw=await fs.readFile(path.join(out,'decoded.f32'));
    const pcm=decoded.outputs['0.35'];
    for(let i=0;i<pcm.length;i++)assert.equal(raw.readFloatLE(i*4),pcm[i]);
    const predictors=await fs.readFile(path.join(out,'coefficients.f64le'));
    for(let i=0;i<decoded.coefficients.length;i++)assert.equal(predictors.readDoubleLE(i*8),decoded.coefficients[i]);
    const meta=JSON.parse(await fs.readFile(path.join(out,'meta.json'),'utf8'));
    assert.equal(meta.mode,'parameter-only-decode');assert.equal(meta.config,null);
    assert.equal(meta.baseSha256,sha(bytes));assert.equal(meta.meta.samples,source.length);
  }finally{
    const resolved=path.resolve(temporary);
    assert.ok(resolved.startsWith(build+path.sep));
    await fs.rm(resolved,{recursive:true});
  }
});
