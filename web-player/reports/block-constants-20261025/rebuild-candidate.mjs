import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseHex} from '../../lib/hex.js';
import {avr,flash} from '../../tests/fixtures/attiny13a-system-firmware.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const json=name=>JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
const sources=json('candidate-sources.json'),report=json('validation.json'),sha=b=>createHash('sha256').update(b).digest('hex');
for(const name of ['avr-wasm-phases.js','avr-phase-locals.js']){
  const path='web-player/lib/'+name;
  assert.equal(sha(readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n')),report.sourceSha256[path],path+' changed');
}
const url=s=>'data:text/javascript;base64,'+Buffer.from(s).toString('base64');
for(const path of ['web-player/lib/avr-transpiler.js','web-player/lib/avr-block-constants.js'])assert.equal(sha(sources[path]),report.sourceSha256[path]);
let compiler=sources['web-player/lib/avr-transpiler.js'].replace("'./avr-block-constants.js'",JSON.stringify(url(sources['web-player/lib/avr-block-constants.js'])));
for(const name of ['devices/profiles.js','avr-wasm-phases.js','avr-phase-locals.js'])compiler=compiler.replace("'./"+name+"'",JSON.stringify(new URL('../../lib/'+name,import.meta.url).href));
const generator=await import(url(compiler));
assert.match(report.baseline.revision,/^[a-f0-9]{40}$/);
const runtime=execFileSync('git',['show',report.baseline.revision+':web-player/wasm/attiny13a.wasm'],{cwd:root,maxBuffer:1024*1024});
assert.equal(sha(runtime),report.runtimeSha256);const exports=new WebAssembly.Instance(new WebAssembly.Module(runtime)).exports;
const catalog=['firmware','hq4-firmware'].flatMap(n=>JSON.parse(readFileSync(new URL('../../'+n+'.json',import.meta.url))).entries);
const kernel=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
const out=resolve(root,'build/rejected-block-constants-reproduction'),generated=new Map();mkdirSync(out,{recursive:true});
for(const row of report.cases){
  assert.match(row.id,/^[a-z0-9-]+$/);
  const binary=row.id.startsWith('kernel-')?kernel:parseHex(catalog.find(e=>e.id===row.actualId).flashHex);
  assert.equal(sha(binary),row.flashSha256);const resumable=!!row.optimization.constantFolding,abi=generator.runtimeABI(exports,{resumable});
  const raw=generator.transpileAVR(binary,abi,{resumable}),candidate=generator.transpileAVR(binary,abi,{resumable,foldBlockConstants:resumable});
  assert.equal(sha(raw.bytes),row.optimization.inputSha256,row.id+' baseline');assert.equal(sha(candidate.bytes),row.optimization.outputSha256,row.id+' candidate');
  assert.equal(WebAssembly.validate(candidate.bytes),true);generated.set(row.actualId,[raw,candidate]);
  writeFileSync(resolve(out,row.id+'.wasm'),candidate.bytes);
}
if(process.argv.includes('--with-optimizer')){
  const {optimizeAVRWasm}=await import('../../scripts/lib/optimize-avr-wasm.mjs');
  const code=bytes=>{let at=8;const leb=()=>{let n=0,s=0,b;do{b=bytes[at++];n|=(b&127)<<s;s+=7;}while(b&128);return n;};while(at<bytes.length){const id=bytes[at++],n=leb();if(id===10)return bytes.slice(at,at+n);at+=n;}throw Error('No code');};
  for(const row of json('optimizer-comparison.json').cases){
    const pair=generated.get(row.id).map(g=>optimizeAVRWasm(g,{level:row.level}));
    pair.forEach(g=>assert.equal(g.optimization.executableSha256,row.executableSha256));
    assert.deepEqual(pair.map(g=>sha(code(g.bytes))),row.codeSha256);
  }
}
console.log(JSON.stringify({reproduced:report.cases.length,optimizerCompared:process.argv.includes('--with-optimizer'),out}));
