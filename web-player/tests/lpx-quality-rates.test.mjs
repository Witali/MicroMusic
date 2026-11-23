import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {qualityCases,qualityTemporalCases} from './helpers/lpx-quality-cases.mjs';

const fixture=JSON.parse(readFileSync(new URL('./fixtures/lpx-quality-reference.json',import.meta.url)));
const cases=qualityCases();
async function load(path) {
  if(!path)return null;
  const {instance}=await WebAssembly.instantiate(readFileSync(path));
  instance.exports.__wasm_call_ctors();return instance.exports;
}
const scalar=await load(process.env.LPX_QUALITY_WASM);
const simd=await load(process.env.LPX_QUALITY_SIMD_WASM);
const legacy=await load(process.env.LPX_QUALITY_LEGACY_WASM);
const fullBandV1=await load(process.env.LPX_FULLBAND_V1_WASM);
function prepare(api,c) {
  assert.ok(api.quality_reserve(c.reference.length));
  new Int16Array(api.memory.buffer,api.quality_reference(),c.reference.length).set(c.reference);
  new Int16Array(api.memory.buffer,api.quality_candidate(),c.candidate.length).set(c.candidate);
}
function measure(api,c,rate=c.rate) {
  prepare(api,c);const pointer=api.quality_measure(rate);
  return Array.from(new Float64Array(api.memory.buffer,pointer,18));
}
function close(a,b,tolerance=1e-10) {
  if(b===null)assert.ok(Number.isNaN(a));
  else assert.ok(Math.abs(a-b)<=tolerance,`${a} vs ${b}`);
}
function bands(api,c,count=90) {
  prepare(api,c);const pointer=api.quality_fullband(c.rate);
  return Array.from(new Float64Array(api.memory.buffer,pointer,count));
}
function closeBands(actual,expected) {
  assert.equal(actual.length,expected.length);
  for(let j=0;j<expected.length;j++)close(actual[j],expected[j],2e-10*Math.max(1,Math.abs(expected[j])));
}

test('quality metrics retain exact scalar/SIMD output and match true-rate pystoi', {skip:!scalar||!simd},()=>{
  assert.equal(cases.length,fixture.cases.length);
  for(let i=0;i<cases.length;i++) {
    const c=cases[i],expected=fixture.cases[i];
    assert.equal(c.name,expected.name);assert.equal(c.rate,expected.rate);assert.equal(c.reference.length,expected.count);
    const actual=measure(scalar,c);assert.deepEqual(measure(simd,c),actual);
    close(actual[2],expected.stoi);
    close(actual[3],expected.stoiPwm);
    if(c.rate===8000) {
      assert.deepEqual(measure(scalar,c,0),actual,'default and explicit 8 kHz remain identical');
      for(let j=0;j<18;j++)close(actual[j],expected.legacy8k[j]);
    }
  }
});

test('8 kHz measurements, source masks and quiet/tail diagnostics match frozen evaluator exactly', {skip:!scalar||!legacy},()=>{
  for(const c of cases.filter(c=>c.rate===8000)) {
    assert.deepEqual(measure(scalar,c),measure(legacy,c,0),c.name);
    assert.deepEqual(measure(scalar,c,0),measure(legacy,c,0),c.name);
  }
});

test('analysis FIRs retain double precision and sub-LSB quiet information', {skip:!scalar||!simd},()=>{
  for(let i=0;i<cases.length;i++) {
    const c=cases[i],expected=fixture.cases[i],outputs=[];
    for(const api of [scalar,simd]) {
      prepare(api,c);const count=api.quality_resample(c.rate);assert.equal(count,expected.analysisCount);
      const values=Array.from(new Float64Array(api.memory.buffer,api.quality_analysis(),count));
      for(const [at,value] of expected.analysis)close(values[at],value,2e-10);
      if(c.name==='quiet'&&c.rate!==8000)assert.ok(values.some(x=>Math.abs(x)>0&&Math.abs(x)<.5));
      outputs.push(values);
    }
    assert.deepEqual(outputs[1],outputs[0]);
  }
});

test('native and WASM evaluators agree on all synthetic full-rate measurements', {skip:!scalar||!process.env.LPX_QUALITY_NATIVE},()=>{
  for(const c of cases) {
    const done=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_QUALITY_NATIVE,String(c.rate),'measure',String(c.reference.length)],
      {input:Buffer.concat([Buffer.from(c.reference.buffer),Buffer.from(c.candidate.buffer)]),maxBuffer:1024*1024});
    assert.equal(done.status,0,done.stderr?.toString());
    const native=Array.from({length:18},(_,i)=>done.stdout.readDoubleLE(i*8)),wasm=measure(scalar,c);
    for(let j=0;j<18;j++)close(wasm[j],Number.isNaN(native[j])?null:native[j]);
  }
});

test('prospective full-band floors match NumPy FFT and protect Nyquist, silence, quiet inputs and tails', {skip:!scalar||!simd},()=>{
  assert.equal(scalar.quality_fullband_selftest(),21);
  assert.equal(simd.quality_fullband_selftest(),21);
  for(let i=0;i<cases.length;i++) {
    const c=cases[i];
    const values=[bands(scalar,c),bands(simd,c)];
    assert.deepEqual(values[0],values[1]);
    closeBands(values[0],[...fixture.cases[i].fullBand,...fixture.cases[i].fullBandTemporal]);
  }
});

test('temporal and balanced errors match an independent FFT oracle for phase/noise/envelope cases', {skip:!scalar||!simd},()=>{
  const inputs=qualityTemporalCases();assert.equal(inputs.length,fixture.temporalCases.length);
  for(let i=0;i<inputs.length;i++) {
    const c=inputs[i],expected=fixture.temporalCases[i];
    assert.equal(c.name,expected.name);assert.equal(c.rate,expected.rate);assert.equal(c.reference.length,expected.count);
    const values=bands(scalar,c);assert.deepEqual(bands(simd,c),values);closeBands(values,expected.fullBand);
    if(c.name==='phase-noise') {
      let waveformError=0;for(let j=0;j<c.reference.length;j++)waveformError+=(c.reference[j]-c.candidate[j])**2;
      assert.ok(waveformError>1e9,'phase-changed noise need not be sample-identical');
      for(const at of [2,84,86,88])assert.equal(values[at],0,'identical native magnitude and magnitude changes');
    } else if(c.name==='silence') {
      assert.ok(values.every(Number.isFinite));for(const at of [2,3,84,85,86,87,88,89])assert.equal(values[at],0);
    } else {
      assert.ok(values[84]>0&&values[88]>0,`${c.name}: temporal mismatch remains visible`);
    }
    if(c.name==='lost-high-band') {
      assert.ok(values[4+6*8+1]||values[4+7*8+1],'actual 16 kHz source supports 6–8 kHz');
      assert.ok(values[4+6*8+2]+values[4+7*8+2]<values[4+6*8]+values[4+7*8],'removed upper-band noise loses power');
    }
  }
});

test('all original v1 full-band fields remain byte-identical after temporal additions', {skip:!scalar||!fullBandV1},()=>{
  for(const c of [...cases,...qualityTemporalCases()])assert.deepEqual(bands(scalar,c,68),bands(fullBandV1,c,68),c.name);
});

test('native/scalar/SIMD temporal measurements agree for actual high-band noise and padded tails', {skip:!scalar||!simd||!process.env.LPX_QUALITY_NATIVE},()=>{
  for(const c of qualityTemporalCases()) {
    const done=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_QUALITY_NATIVE,String(c.rate),'temporal',String(c.reference.length)],
      {input:Buffer.concat([Buffer.from(c.reference.buffer),Buffer.from(c.candidate.buffer)]),maxBuffer:1024*1024});
    assert.equal(done.status,0,done.stderr?.toString());
    const native=Array.from({length:90},(_,i)=>done.stdout.readDoubleLE(i*8));
    closeBands(bands(scalar,c),native);closeBands(bands(simd,c),native);
  }
});
