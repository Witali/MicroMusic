// Re-run source-only PWM firmware and retain only project evidence.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs,isDeepStrictEqual} from 'node:util';
import {pwmBoundaryCases,runPwmBoundaryCase} from '../tests/fixtures/attiny13a-pwm-boundaries.mjs';
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{output:{type:'string',default:'build/pwm-boundaries-evidence.json'},
  'test-tap':{type:'string',default:'build/pwm-boundaries-20261101.tap'},'full-tap':{type:'string'}}});
const read=p=>readFileSync(resolve(root,p)),text=p=>read(p).toString().replaceAll('\r\n','\n'),
  hash=b=>createHash('sha256').update(b).digest('hex'),stringify=v=>JSON.stringify(v,(_,v)=>typeof v==='bigint'?v.toString():v);
const baseline='87173ce8',git=p=>execFileSync('git',['show',baseline+':'+p],{cwd:root,maxBuffer:4*1024*1024});
const native=read('web-player/wasm/attiny13a.wasm'),manifest=JSON.parse(text('web-player/wasm/device-build.json'));
assert.ok(native.equals(git('web-player/wasm/attiny13a.wasm')),'Production native differs');
assert.equal(hash(native),manifest.artifacts['attiny13a.wasm']);
for(const [path,h]of Object.entries(manifest.inputs)){
  assert.equal(hash(text(path)),h,'Native input differs');assert.equal(hash(git(path).toString().replaceAll('\r\n','\n')),h,'Native changed from baseline');
}
for(const [path,h]of Object.entries(AVR_CACHE_SOURCES)){
  assert.equal(hash(text(path)),h,'Compiler source differs');assert.equal(hash(git(path).toString().replaceAll('\r\n','\n')),h,'Compiler changed from baseline');
}
const twins=new Map(),cases=[];let edges=0,irqs=0;
for(const spec of pwmBoundaryCases){
  const result=runPwmBoundaryCase(spec),key=spec.id.slice(0,spec.id.lastIndexOf('/'));
  if(twins.has(key)){
    const previous=twins.get(key);
    assert.ok(isDeepStrictEqual(previous.state,result.state),'Policy state differs: '+key);
    assert.ok(isDeepStrictEqual(previous.data,result.data),'Policy SRAM/register data differs: '+key);
    assert.ok(isDeepStrictEqual(previous.trace,result.trace),'Policy pin trace differs: '+key);
    twins.delete(key);
  }else twins.set(key,result);
  edges+=result.trace.length;irqs+=result.state.irqs;
  cases.push({...spec,flashSha256:hash(result.flash),startPs:result.startPs.toString(),endPs:result.endPs.toString(),
    periodCycles:result.periodCycles,events:result.trace.map(p=>({timePs:p.timePs.toString(),levels:p.levels})),
    state:result.state,dataSha256:hash(result.data),stateSha256:hash(stringify(result.state)),
    expectedTraceSha256:hash(stringify(result.expected)),actualTraceSha256:hash(stringify(result.trace))});
}
assert.equal(cases.length,144);assert.equal(twins.size,0);assert.equal(edges,408);assert.ok(irqs>0);
const tap=(path,expected)=>{
  const bytes=read(path),counts=Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo'].map(key=>{
    const m=bytes.toString().match(new RegExp('^# '+key+' (\\d+)$','m'));assert.ok(m,'Incomplete TAP');return [key,Number(m[1])];
  }));assert.equal(counts.tests,counts.pass);assert.equal(counts.fail+counts.cancelled+counts.skipped+counts.todo,0);
  assert.ok(counts.pass>0);if(expected!==undefined)assert.equal(counts.pass,expected);
  return {...counts,path,sha256:hash(bytes)};
};
const sources=['web-player/scripts/verify-pwm-boundaries.mjs','web-player/tests/attiny13a-pwm-boundaries.test.mjs',
  'web-player/tests/fixtures/attiny13a-pwm-boundaries.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs',
  'web-player/lib/attiny13a-registers.js','web-player/lib/emulation-configurations.js'];
const report={schema:'micromusic-pwm-boundary-firmware-v1',date:'2026-11-01',baselineRef:baseline,
  node:process.versions.node,v8:process.versions.v8,native:{bytes:native.length,sha256:hash(native)},
  compilerIdentity:AVR_CACHE_COMPILER_ID,productionUnchanged:true,
  sources:Object.fromEntries(sources.map(p=>[p,hash(text(p))])),nativeInputs:manifest.inputs,compilerSources:AVR_CACHE_SOURCES,
  focusedSuite:tap(values['test-tap'],144),...(values['full-tap']?{fullSuite:tap(values['full-tap'])}:{}),
  totals:{cases:cases.length,policyPairs:72,comparedPinEvents:edges,activeInterrupts:irqs},cases,
  plan:{complete:24,total:31,open:7},
  limits:['Steady preloaded OCR values, Timer0 /1 and nominal 1 MHz software fixtures only; not dynamic TOP or buffer-boundary measurements.',
    'Exact selected-pin times follow the documented digital compare-pulse phase; this is not a silicon clock/phase oracle.',
    'No WGM5/TOP0, physical calibration, official simulator or audio-underrun acceptance is established.']};
const output=resolve(root,values.output);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n');
console.log(JSON.stringify(report.totals));
