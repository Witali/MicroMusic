import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath,pathToFileURL} from 'node:url';
import * as bridge from '../lib/avr-wasm.js';
import {candidateSource,fixture,hash,normalized,variants} from './helpers/native-candidates.mjs';
const source=normalized(fileURLToPath(new URL('../native/avr.c',import.meta.url)));
test('optimization controls are pinned to the reviewed C source and fail closed when stale',()=>{
  assert.equal(hash(source),fixture.baseSourceSha256);
  for(const variant of variants){
    const candidate=candidateSource(source,variant);
    assert.equal(hash(candidate)===hash(source),variant===((fixture.applied??[]).join('-')||'generic'));
    for(const [name,edit] of Object.entries(fixture.edits)){
      assert.equal(candidate.includes(edit.after),variant.split('-').includes(name),name);
    }
  }
  assert.throws(()=>candidateSource(source+'\n','budget'),/source changed/);
  assert.throws(()=>candidateSource(source,'unknown'),/Unknown candidate/);
});
test('test process actually loads the selected native artifact and verifies its provenance',async()=>{
  const selected=process.env.MICROMUSIC_AVR_TEST_MODULE;
  if(!selected){assert.equal('__testWasmModuleURL' in bridge,false);return;}
  assert.equal(bridge.__testWasmModuleURL,pathToFileURL(selected).href,'Candidate preload must reach each test child');
  const versionedBridge=await import('../lib/avr-wasm.js?v=20261025-board-um88-pipeline');
  assert.equal(versionedBridge.__testWasmModuleURL,pathToFileURL(selected).href,'Versioned production imports must load the candidate too');
  const manifest=JSON.parse(readFileSync(process.env.MICROMUSIC_AVR_TEST_MANIFEST));
  assert.equal(manifest.schema,'micromusic-avr-test-candidate-v1');
  assert.equal(hash(readFileSync(selected)),manifest.wasmSha256);
  assert.equal(hash(candidateSource(source,manifest.variant)),manifest.sourceSha256);
  assert.equal(hash(normalized(fileURLToPath(new URL('./fixtures/block-optimizations.json',import.meta.url)))),manifest.fixtureSha256);
  const module=await WebAssembly.compile(readFileSync(selected));assert.deepEqual(WebAssembly.Module.imports(module),[]);
  const cpu=new bridge.AVRCore(Uint8Array.of(0,0));assert.equal(cpu._exports.memory.buffer.byteLength,131072);
});
