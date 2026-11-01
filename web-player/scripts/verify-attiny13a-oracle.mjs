// Preparation check in our model; never an official-simulator observation.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';
import {ATtiny13A} from '../lib/attiny13a.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
import {AT13_MEMORY as MEMORY} from '../lib/attiny13a-registers.js';
import {decodeAttiny13aOracle} from './lib/attiny13a-oracle-record.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{bundle:{type:'string',default:'build/probes/attiny13a-studio'},output:{type:'string'}}});
const folder=resolve(root,values.bundle),read=name=>readFileSync(resolve(folder,name));
const hash=b=>createHash('sha256').update(b).digest('hex');
const d=JSON.parse(read('descriptor.json')),binary=new Uint8Array(read('oracle.bin'));
assert.equal(hash(binary),d.flashSha256);assert.equal(hash(read('oracle.elf')),d.elfSha256);
assert.equal(hash(read('debughooks.py')),d.debughooksSha256);
for(const [path,expected]of Object.entries(d.sources))
  assert.equal(hash(Buffer.from(readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n'))),expected,path);
const c=new ATtiny13A(binary,null,{...nominalVerificationDeviceOptions(9600000),fuseLow:0x72,fuseStartupProfile:0});
const start=new Map(d.caseSpans.map((x,n)=>[x.targetByteAddress/2,n]));
const after=new Map(d.caseSpans.map((x,n)=>[x.afterByteAddress/2,n]));
const entered=new Map(),cycles=[];let steps=0;
while(c.pc!==d.stopByteAddress/2){
  assert.ok(steps++<5000,'Fixture did not complete');
  if(start.has(c.pc))entered.set(start.get(c.pc),c.cyc);
  if(after.has(c.pc)){const n=after.get(c.pc);assert.ok(entered.has(n));
    const delta=c.cyc-entered.get(n);assert.equal(delta,d.cases[n].cycles,d.cases[n].id+' original CPU cycles');cycles[n]=delta;}
  c.step();assert.equal(c.state().deviceFault,0);
}
assert.equal(cycles.length,d.cases.length);assert.equal(c.sp,MEMORY.RAMEND);
const record=c.data.slice(d.recordAddress,d.recordAddress+d.recordBytes);
const decoded=decodeAttiny13aOracle(record,d,{captureKind:'synthetic-emulator'});assert.equal(decoded.passed,true);
const result={schema:'micromusic-attiny13a-oracle-preparation-v1',officialSessionExecuted:false,
  descriptorSha256:hash(read('descriptor.json')),flashSha256:d.flashSha256,elfSha256:d.elfSha256,
  nativeSha256:hash(readFileSync(resolve(root,'web-player/wasm/attiny13a.wasm'))),
  steps,record:Array.from(record),measuredModelSequenceCycles:cycles,decoded};
const out=values.output?resolve(root,values.output):resolve(folder,'synthetic-validation.json');
writeFileSync(out,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({cases:decoded.cases.length,passed:decoded.passed,overheadTicks:decoded.overheadTicks,
  steps,officialSessionExecuted:false,hostVerified:false}));
