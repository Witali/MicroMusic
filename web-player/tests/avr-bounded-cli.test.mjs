import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,flash} from './fixtures/attiny13a-system-firmware.mjs';
test('CLIs generate bounded physical CPU/package artifacts and reject incompatible flags',async()=>{
  const directory=mkdtempSync(join(tmpdir(),'micromusic-bounded-cli-'));
  try{
    const input=join(directory,'firmware.bin'),output=join(directory,'cpu.wasm'),config=join(directory,'physical.json'),pkg=join(directory,'device.json');
    writeFileSync(input,flash({instructions:[avr.inc(16),avr.rjmp(1,0)]}));
    writeFileSync(config,JSON.stringify({resumable:true,osccalHz:Array(128).fill(9600000)}));
    const run=(script,args)=>spawnSync(process.execPath,[fileURLToPath(new URL('../scripts/'+script,import.meta.url)),...args],{encoding:'utf8',windowsHide:true});
    const generated=run('transpile-avr.mjs',[input,output,'--device','--resumable','--bounded-regions']);assert.equal(generated.status,0,generated.stderr);
    const report=JSON.parse(readFileSync(output+'.json','utf8'));assert.equal(report.boundedRegions,true);assert.equal(report.executionMode,'resumable-v1');
    assert.equal(WebAssembly.validate(readFileSync(output)),true);
    const packed=run('package-attiny13a.mjs',['pack',input,pkg,'--configuration',config,'--bounded-regions']);assert.equal(packed.status,0,packed.stderr);
    const core=await ATtiny13A.fromPackage(readFileSync(pkg,'utf8'));assert.equal(core.transpilation.boundedRegions,true);
    assert.equal(core.run(100),100);assert.equal(core.r[16],50);assert.equal(core.cyc,150);assert.equal(core.state().deviceFault,0);
    for(const args of [[input,output,'--bounded-regions'],[input,output,'--resumable']]){
      const r=run('transpile-avr.mjs',args);assert.notEqual(r.status,0);assert.match(r.stderr,/requires/);
    }
    const invalid=run('package-attiny13a.mjs',['pack',input,join(directory,'invalid.json'),'--bounded-regions']);
    assert.notEqual(invalid.status,0);assert.match(invalid.stderr,/requires configuration.resumable/);
  }finally{assert.equal(dirname(directory),resolve(tmpdir()));rmSync(directory,{recursive:true,force:true});}
});
