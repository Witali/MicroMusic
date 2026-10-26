// Rebuild the rejected CPU binaries without touching production or installing it.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {parseHex} from '../../lib/hex.js';
import {avr,flash} from '../../tests/fixtures/attiny13a-system-firmware.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
const sources=read('candidate-sources.json'),report=read('validation.json');
const sha=b=>createHash('sha256').update(b).digest('hex');
for(const path of ['web-player/lib/avr-wasm-phases.js','web-player/lib/avr-phase-locals.js'])
  assert.equal(sha(readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n')),report.sourceSha256[path],path+' dependency changed');
const compilerPath='web-player/lib/avr-transpiler.js';assert.equal(sha(sources[compilerPath]),report.sourceSha256[compilerPath]);
let source=sources[compilerPath];
for(const specifier of ['devices/profiles.js','avr-wasm-phases.js','avr-phase-locals.js'])
  source=source.replace("'./"+specifier+"'",JSON.stringify(new URL('../../lib/'+specifier,import.meta.url).href));
const generator=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const runtime=execFileSync('git',['show',report.baseline.revision+':web-player/wasm/attiny13a.wasm'],{cwd:root,maxBuffer:1024*1024});
assert.equal(sha(runtime),report.runtimeSha256);const exports=new WebAssembly.Instance(new WebAssembly.Module(runtime)).exports;
const catalog=['firmware','hq4-firmware'].flatMap(name=>JSON.parse(readFileSync(new URL('../../'+name+'.json',import.meta.url))).entries);
const kernel=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
const out=resolve(root,'build/rejected-flag-regions-reproduction');mkdirSync(out,{recursive:true});
for(const row of report.cases){
  assert.match(row.id,/^[a-z0-9-]+$/);
  const binary=row.id.startsWith('kernel-')?kernel:parseHex(catalog.find(e=>e.id===row.actualId).flashHex);
  assert.equal(sha(binary),row.flashSha256);const resumable=!!row.optimization.flagRegions;
  const abi=generator.runtimeABI(exports,{resumable});
  const raw=generator.transpileAVR(binary,abi,{resumable}),candidate=generator.transpileAVR(binary,abi,{resumable,fuseFlagBlocks:resumable});
  assert.equal(sha(raw.bytes),row.optimization.inputSha256,row.id+' baseline');
  assert.equal(sha(candidate.bytes),row.optimization.outputSha256,row.id+' candidate');
  assert.equal(WebAssembly.validate(candidate.bytes),true);
  writeFileSync(resolve(out,row.id+'.wasm'),candidate.bytes);
}
console.log(JSON.stringify({reproduced:report.cases.length,runtimeSha256:sha(runtime),out}));
