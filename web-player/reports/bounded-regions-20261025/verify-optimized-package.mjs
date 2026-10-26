// Untimed composition smoke test: bounded regions -> Binaryen Oz -> package.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ATtiny13A} from '../../lib/attiny13a.js';
import {parseHex} from '../../lib/hex.js';
import {createPackage} from '../../lib/attiny13a-package.js';
import {optimizeAVRWasm} from '../../scripts/lib/optimize-avr-wasm.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),runtime=readFileSync(new URL('../../wasm/attiny13a.wasm',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex'),json=v=>JSON.stringify(v,(_,n)=>typeof n==='bigint'?n.toString():n,2)+'\n';
const entries=['firmware','hq4-firmware'].flatMap(n=>JSON.parse(readFileSync(new URL('../../'+n+'.json',import.meta.url))).entries);
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),eeprom:c.eeprom.slice(),flash:c.rom.slice(),irq:Array.from(c.irqFrames)});
const report={schema:'micromusic-bounded-optimized-package-v1',complete:false,runtimeSha256:sha(runtime),cases:[]};
for(const id of ['rhythmic','lumiere-stereo','hq4-chego-tiny']){
  const entry=entries.find(e=>e.id===id),flash=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):undefined;
  const hz=entry.cpuHz||9600000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  const configuration={resumable:true,oscillatorHz:hz,osccalHz,nvmClockProfile:1,nvmCalibrationReferenceHz:hz};
  const a=new ATtiny13A(flash,eeprom,{...configuration,boundedRegions:true});
  const optimized=optimizeAVRWasm({bytes:a.transpiledBytes,manifest:a.transpilation},{level:'Oz'});
  const pkg=await createPackage({flash,eeprom,runtime,translated:optimized.bytes,configuration});
  const b=await ATtiny13A.fromPackage(pkg);let checkpoints=0;
  for(let n=0;n<4;n++){
    assert.deepEqual(a.capturePhysical(256,48000,entry.audioChannels||1),b.capturePhysical(256,48000,entry.audioChannels||1));
    assert.deepEqual(snapshot(a),snapshot(b));assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());checkpoints++;
  }
  assert.equal(a.state().deviceFault,0);assert.ok(a.irqCount>0);
  report.cases.push({id,flashSha256:sha(flash),optimization:optimized.optimization,checkpoints,irqCount:a.irqCount,stateSha256:sha(json(snapshot(a)))});
}
report.complete=true;
const output=resolve(root,process.argv[2]||'build/bounded-regions-optimized-package.json');mkdirSync(dirname(output),{recursive:true});writeFileSync(output,json(report));
console.log(json({complete:true,cases:report.cases.length,checkpoints:report.cases.reduce((n,c)=>n+c.checkpoints,0)}).trim());
