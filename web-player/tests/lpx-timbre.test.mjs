import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createEncoder} from '../lpx/encoder.js';
import {createDecoder} from '../lpx/codec.js';
import {createInputResampler} from '../lpx/audio-source.js';
import {timbreCases,transitionTimbreCases,renderPartials,inharmonicPartials,brightPartials,measureTimbre,spectrumBandFraction} from './helpers/lpx-timbre-cases.mjs';

const root=new URL('../lpx/',import.meta.url);
const scalar=await createEncoder(readFileSync(new URL('encoder-adaptive.wasm',root)));
const simd=await createEncoder(readFileSync(new URL('encoder-adaptive-simd.wasm',root)));
const decode=await createDecoder(readFileSync(new URL('decoder.wasm',root)));
const rms=(pcm,start=0)=>Math.sqrt(pcm.subarray(start).reduce((sum,x)=>sum+x*x,0)/(pcm.length-start));
const options={accuracy:true,calls:0};

test('independent timbre metrics accept identity and polarity changes without fitting gain or delay',()=>{
  for(const rate of [8000,12000,16000])for(const c of [...timbreCases(rate),...transitionTimbreCases(rate)]) {
    for(const pcm of [c.reference,Int16Array.from(c.reference,x=>-x)]) {
      const m=measureTimbre(c.reference,pcm,rate,c.partials);
      assert.equal(m.spectralShapeError,0);assert.equal(m.partialShapeError,0);
      assert.equal(m.envelopeError,0);assert.equal(m.energyRatio,1);
    }
  }
});

test('same-rate metrics detect an inharmonic bell collapsed to one equal-energy tone',()=>{
  const rate=8000,reference=renderPartials(rate,inharmonicPartials);
  const tone=renderPartials(rate,[inharmonicPartials[0]]),gain=rms(reference)/rms(tone);
  const candidate=Int16Array.from(tone,x=>Math.round(x*gain));
  const m=measureTimbre(reference,candidate,rate,inharmonicPartials);
  assert.ok(Math.abs(m.energyRatio-1)<.02,'collapse remains visible without a loudness difference');
  assert.equal(m.sourcePartials,4);assert.equal(m.retainedPartials,1);
  assert.ok(m.partialShapeError>.3,'one-tone collapse is not accepted as the original timbre');
});

test('temporal metrics detect a delayed noise attack even with the same carrier',()=>{
  const c=timbreCases(16000).find(x=>x.name==='noise-attack'),delay=1600;
  const candidate=new Int16Array(c.reference.length);candidate.set(c.reference.subarray(0,-delay),delay);
  const m=measureTimbre(c.reference,candidate,c.rate);
  assert.ok(m.envelopeError>.4);
});

async function preparedBrightBell(target) {
  const rate=48000,source=renderPartials(rate,brightPartials),binary=readFileSync(new URL('input-resampler.wasm',root));
  const resampler=await createInputResampler(binary);resampler.init(rate,target,1);
  const chunks=[];
  for(let at=0;at<source.length;at+=1024) {
    const count=Math.min(1024,source.length-at);
    for(let i=0;i<count;++i)resampler.input[i]=source[at+i]/32768;
    chunks.push(resampler.push(count).slice());
  }
  chunks.push(resampler.push(0,true).slice());
  return Int16Array.from(chunks.flatMap(chunk=>Array.from(chunk)));
}

test('8 kHz bandwidth loss is separated from same-rate codec timbre loss',async()=>{
  const narrow=await preparedBrightBell(8000),wide=await preparedBrightBell(16000);
  assert.ok(spectrumBandFraction(narrow,8000,2500,3000)>.95,'anti-aliasing leaves the legal lower partial');
  assert.ok(spectrumBandFraction(narrow,8000,2000,2300)<.001,'the removed high partial does not fold into the passband');
  assert.ok(spectrumBandFraction(wide,16000,5500,6200)>.65,'16 kHz retains the strong legal bright partial');
  const a=measureTimbre(narrow,narrow,8000,brightPartials),b=measureTimbre(wide,wide,16000,brightPartials);
  assert.deepEqual(a.frequencies,[2731]);assert.deepEqual(b.frequencies,[2731,5837]);
  assert.equal(a.partialShapeError,0);assert.equal(b.partialShapeError,0);
  assert.equal(a.sourcePartials,1);assert.equal(b.sourcePartials,2);
});

test('every accuracy level preserves legal decaying tones and harmonic controls without self-oscillation', {timeout:60000},()=>{
  for(const rate of [8000,12000,16000])for(const c of timbreCases(rate).filter(x=>['high-ring','harmonic-control'].includes(x.name)))for(const level of [3,4,6,8]) {
    const bytes=scalar(c.reference,rate,level,()=>{},options),pcm=decode(bytes).pcm;
    assert.deepEqual(bytes,simd(c.reference,rate,level,()=>{},options));
    const m=measureTimbre(c.reference,pcm,rate,c.partials);
    const label=`${c.name}/P${level}/${rate}`;
    assert.ok(m.energyRatio<=4,`${label}: generated energy exceeds a generous +6 dB bound (${m.energyRatio})`);
    assert.ok(m.spectralShapeError<.5,`${label}: dominant energy moved off the source spectrum (${m.spectralShapeError})`);
    assert.equal(m.retainedPartials,m.sourcePartials,`${label}: a significant source partial was lost`);
    const start=Math.floor(pcm.length*.75);
    assert.ok(rms(pcm,start)<=Math.max(64,3*rms(c.reference,start)),`${label}: the decayed tail becomes self-oscillation`);
  }
});

test('every accuracy level retains multiple inharmonic bell partials at the same actual rate', {timeout:60000},()=>{
  for(const rate of [8000,12000,16000])for(const level of [3,4,6,8]) {
    const c=timbreCases(rate).find(x=>x.name==='inharmonic-bell');
    const bytes=scalar(c.reference,rate,level,()=>{},options),pcm=decode(bytes).pcm;
    assert.deepEqual(bytes,simd(c.reference,rate,level,()=>{},options));
    const m=measureTimbre(c.reference,pcm,rate,c.partials);
    assert.equal(m.sourcePartials,4);assert.ok(m.retainedPartials>=3,`P${level}/${rate}: only ${m.retainedPartials} significant partials retained`);
    assert.ok(m.partialShapeError<.2,`P${level}/${rate}: the spectral balance collapses to one partial`);
  }
});

test('every accuracy level retains the timing and broad spectrum of a short noise attack', {timeout:60000},()=>{
  for(const rate of [8000,12000,16000])for(const level of [3,4,6,8]) {
    const c=timbreCases(rate).find(x=>x.name==='noise-attack');
    const bytes=scalar(c.reference,rate,level,()=>{},options),pcm=decode(bytes).pcm;
    assert.deepEqual(bytes,simd(c.reference,rate,level,()=>{},options));
    const m=measureTimbre(c.reference,pcm,rate),label=`P${level}/${rate}`;
    assert.ok(m.envelopeError<.3,`${label}: the short attack is lost or displaced (${m.envelopeError})`);
    assert.ok(m.spectralShapeError<.2,`${label}: broadband excitation collapses to a narrow spectrum`);
    assert.ok(m.energyRatio>.2&&m.energyRatio<=4,`${label}: suppressing or amplifying the source is not attack preservation`);
  }
});

test('every accuracy level retains ring timbre after a harmonic carrier transition', {timeout:60000},()=>{
  for(const rate of [8000,12000,16000])for(const c of transitionTimbreCases(rate))for(const level of [3,4,6,8]) {
    const bytes=scalar(c.reference,rate,level,()=>{},options),pcm=decode(bytes).pcm;
    assert.deepEqual(bytes,simd(c.reference,rate,level,()=>{},options));
    const {start,end}=c.window,label=`${c.name}/P${level}/${rate}`;
    const m=measureTimbre(c.reference.subarray(start,end),pcm.subarray(start,end),rate,c.partials);
    assert.equal(m.sourcePartials,c.partials.length,'the measured source ring has significant legal partials');
    assert.ok(m.spectralShapeError<.5,`${label}: ring energy moved off its source spectrum (${m.spectralShapeError})`);
    assert.ok(m.minimumPartialRetention>=.5,`${label}: a significant ring partial lost more than half its amplitude (${m.minimumPartialRetention})`);
  }
});

test('adaptive accuracy retains the admissible ring when an optional seed is unsafe', {timeout:120000},()=>{
  // This valid source admits the ordinary seed, while the optional pre=0
  // seed exhausts its safety recovery. Reject that proposal, not the encode.
  const rate=16000,level=3,c=transitionTimbreCases(rate).find(x=>x.name==='harmonic-to-upper-ring');
  const settings={accuracy:true,calls:4},bytes=scalar(c.reference,rate,level,()=>{},settings);
  assert.deepEqual(bytes,simd(c.reference,rate,level,()=>{},settings));
  const result=decode(bytes);
  assert.equal(result.samples,c.reference.length);assert.equal(result.sampleRate,rate);assert.equal(result.profile,4);
  const {start,end}=c.window,m=measureTimbre(c.reference.subarray(start,end),result.pcm.subarray(start,end),rate,c.partials);
  assert.ok(m.spectralShapeError<.5,`the admitted ring moved off its source spectrum (${m.spectralShapeError})`);
  assert.ok(m.minimumPartialRetention>=.5,`the admitted ring lost more than half its amplitude (${m.minimumPartialRetention})`);
  for(const [executable,backend] of [
    ...(process.env.LPX_ACCURACY_NATIVE?[[process.env.LPX_ACCURACY_NATIVE,'cpu']]:[]),
    ...(process.env.LPX_ACCURACY_CUDA?[[process.env.LPX_ACCURACY_CUDA,'cpu'],[process.env.LPX_ACCURACY_CUDA,'cuda']]:[])
  ]) {
    const native=spawnSync(executable,['--accuracy',String(level),'--rate',String(rate),'--calls','4','--backend',backend],
      {input:Buffer.from(c.reference.buffer),maxBuffer:1024*1024,windowsHide:true,timeout:30000});
    assert.equal(native.status,0,native.stderr?.toString());assert.deepEqual(native.stdout,Buffer.from(bytes));
  }
});

test('native and optional CUDA match scalar/SIMD timbre streams at every accuracy level',
  {skip:!process.env.LPX_ACCURACY_NATIVE,timeout:60000},()=>{
    for(const rate of [8000,12000,16000])for(const c of [
      ...timbreCases(rate).filter(x=>['high-ring','inharmonic-bell'].includes(x.name)),
      ...transitionTimbreCases(rate).filter(x=>x.name==='harmonic-to-upper-ring')
    ])for(const level of [3,4,6,8]) {
      const expected=scalar(c.reference,rate,level,()=>{},options);
      for(const [executable,backend] of [[process.env.LPX_ACCURACY_NATIVE,'cpu'],
        ...(process.env.LPX_ACCURACY_CUDA?[[process.env.LPX_ACCURACY_CUDA,'cpu'],[process.env.LPX_ACCURACY_CUDA,'cuda']]:[])]) {
        const result=spawnSync(executable,['--accuracy',String(level),'--rate',String(rate),'--quality','fast','--backend',backend],
          {input:Buffer.from(c.reference.buffer),maxBuffer:1024*1024,windowsHide:true,timeout:30000});
        assert.equal(result.status,0,result.stderr?.toString());assert.deepEqual(result.stdout,Buffer.from(expected));
      }
    }
  });
