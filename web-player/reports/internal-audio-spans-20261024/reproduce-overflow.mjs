// Correctness reproduction only. Run from any working directory.
import assert from 'node:assert/strict';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const parent=resolve(root,'build/internal-audio-spans-reproduction');mkdirSync(parent,{recursive:true});
const folder=mkdtempSync(join(parent,'baseline-'));
const binary=execFileSync('git',['show','4f09550:web-player/wasm/attiny13a.wasm'],{cwd:root,maxBuffer:1024*1024});
assert.equal(createHash('sha256').update(binary).digest('hex'),
  '794f8f961e8bf89ad2649c2fa470ea60fac0802f671395b3205504a740a94a4e');
const wasmPath=join(folder,'baseline.wasm');writeFileSync(wasmPath,binary);
const original=readFileSync(resolve(root,'web-player/tests/attiny13a-long-audio-span.test.mjs'),'utf8');
const needle='spmCommandCycles:4800});';
assert.equal(original.split(needle).length,2,'exactly one runtime injection point');
const library=pathToFileURL(resolve(root,'web-player/lib')).href+'/',
  fixtures=pathToFileURL(resolve(root,'web-player/tests/fixtures')).href+'/';
const source="import {readFileSync as readBaseline} from 'node:fs';\n"+
  'const baselineRuntime=new WebAssembly.Module(readBaseline('+JSON.stringify(wasmPath)+'));\n'+
  original.replaceAll("'../lib/","'"+library).replaceAll("'./fixtures/","'"+fixtures)
    .replace(needle,'spmCommandCycles:4800,runtimeModule:baselineRuntime});');
const target=join(folder,'baseline-oracle.test.mjs');writeFileSync(target,source);
const run=spawnSync(process.execPath,['--test',target],{cwd:root,encoding:'utf8',maxBuffer:4*1024*1024});
assert.ifError(run.error);writeFileSync(join(folder,'baseline.tap'),run.stdout+run.stderr);
assert.equal(run.status,1,'the old runtime must fail the overflow checks');
for(const line of ['# tests 12','# pass 6','# fail 6'])assert.ok(run.stdout.includes(line),line);
assert.equal((run.stdout.match(/error: 'ATtiny13A peripheral fault 9, detail 1024'/g)||[]).length,6);
console.log('Reproduced six old-runtime ring overflows; six control/fractional-grid cases passed.');
console.log('Retained source, baseline WASM and TAP: '+folder);
