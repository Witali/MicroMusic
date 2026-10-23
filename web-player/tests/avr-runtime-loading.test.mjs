import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';

test('injected-runtime classes import without loading or compiling a default WASM image',()=>{
  const target=new URL('../lib/attiny13a-runtime.js',import.meta.url).href;
  const result=spawnSync(process.execPath,['--input-type=module','-e',
    `globalThis.WebAssembly=undefined;globalThis.fetch=()=>{throw Error('Unexpected runtime fetch');};await import(${JSON.stringify(target)});`],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
});
