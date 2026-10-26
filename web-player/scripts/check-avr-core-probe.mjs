// Software acquisition check only; never opens a USB device or writes EEPROM.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as WASM} from '../lib/avr-wasm.js';
import {AVRCore as Transpiled} from '../lib/avr-transpiled.js';
import {AT88_DATA as R,AT88_MEMORY as M} from '../lib/attiny88-registers.js';
import {coreProbeCases,decodeCoreProbe} from './lib/avr-core-probe-cases.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'build-dir':{type:'string',default:'build/probes/avr88-core'},out:{type:'string'}}});
const dir=resolve(root,values['build-dir']),descriptor=JSON.parse(readFileSync(join(dir,'descriptor.json')));
const rom=readFileSync(join(dir,'probe.bin')),sha=b=>createHash('sha256').update(b).digest('hex');
assert.equal(descriptor.schema,'micromusic-avr-core-probe-v1');
assert.equal(descriptor.hardwareTested,false);
assert.deepEqual(descriptor.cases,coreProbeCases);
assert.equal(sha(rom),descriptor.flashSha256);assert.equal(rom.length,descriptor.flashBytes);
for(const [p,hash] of Object.entries(descriptor.sources))
  assert.equal(sha(readFileSync(join(root,p),'utf8').replaceAll('\r\n','\n')),hash,'Stale probe source: '+p);
const stop=descriptor.symbols.probe_measured/2,address=descriptor.symbols.probe_packet&65535;
assert.ok(Number.isInteger(stop)&&stop>=0&&stop*2<rom.length);
assert.ok(address>=M.ramStart&&address+64<=M.ramEnd+1);
const records=[];
for(const handoff of [false,true]){
  let reference;
  for(const [engine,Core] of Object.entries({js:JS,wasm:WASM,transpiled:Transpiled})){
    const eeprom=Uint8Array.from({length:64},(_,n)=>handoff?(n*67+15)&255:255);
    const c=new Core(rom,eeprom,{target:'attiny88',cpuHz:16000000,fastIdle:false,fastBlocks:false});
    if(handoff){c.data[R.MCUSR]=8;c.data[R.WDTCSR]=0x2b;c.sp=0x17f;}
    let steps=0;while(c.pc!==stop){assert.ok(++steps<=100000,'Probe instruction limit');c.step();}
    const packet=c.data.slice(address,address+64),result=decodeCoreProbe(packet,descriptor);
    assert.equal(result.passed,true,engine+' expected instruction results/flags/cycles');
    assert.equal(result.overheadTicks,5,'Two LDS boundaries plus SREG read');
    assert.equal(c.irqCount,0);assert.equal(c.data[R.MCUSR],0);assert.equal(c.data[R.WDTCSR],0);
    assert.equal(c.data[R.CLKPR],0);assert.equal(c.data[R.TCCR1B],0);
    assert.deepEqual(c.eeprom,eeprom,'Stops before EEPROM invalidation/programming');
    const snapshot={pc:c.pc,cycles:c.cyc,steps,data:Array.from(c.data),irqFrames:Array.from(c.irqFrames)};
    if(reference)assert.deepEqual(snapshot,reference,'Complete CPU/SRAM/timer snapshot');else reference=snapshot;
    records.push({engine,handoff,steps,cycles:c.cyc,packet:Array.from(packet),result});
  }
}
const report={schema:'micromusic-avr-core-probe-software-v1',hardwareTested:false,
  boundary:'probe_measured, before all EEPROM programming and LED output',
  flashSha256:descriptor.flashSha256,flashBytes:rom.length,buildId:descriptor.buildId,
  compilerVersion:descriptor.compilerVersion,sources:descriptor.sources,records};
if(values.out)writeFileSync(resolve(root,values.out),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({hardwareTested:false,flashBytes:rom.length,executions:records.length,
  casesPerExecution:coreProbeCases.length,cycles:records.map(r=>r.cycles),passed:true}));
