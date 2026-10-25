// Untimed activation oracle; no diagnostic counters are added to CPU WASM.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a.js';
import {parseHex} from '../lib/hex.js';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{instructions:{type:'string',default:'1000000'},out:{type:'string',default:'build/bounded-regions-activation.json'}}});
const instructions=Number(values.instructions);assert.ok(Number.isInteger(instructions)&&instructions>=1000&&instructions<=10000000);
const sha=b=>createHash('sha256').update(b).digest('hex'),json=v=>JSON.stringify(v,(_,n)=>typeof n==='bigint'?n.toString():n,2)+'\n';
const entries=['firmware','hq4-firmware'].flatMap(name=>JSON.parse(readFileSync(resolve(root,'web-player/'+name+'.json'))).entries);
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),eeprom:c.eeprom.slice(),flash:c.rom.slice(),irq:Array.from(c.irqFrames)});
const report={schema:'micromusic-bounded-regions-activation-v1',complete:false,instructions,
  runtimeSha256:sha(readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url))),
  sourceSha256:Object.fromEntries(['web-player/lib/avr-transpiler.js','web-player/lib/avr-wasm-regions.js','web-player/lib/avr-transpiled-runtime.js','web-player/scripts/trace-bounded-regions.mjs']
    .map(p=>[p,sha(readFileSync(resolve(root,p),'utf8').replaceAll('\r\n','\n'))])),
  method:'Untimed public block/step prefix, idle acceleration disabled. A return greater than the original basic-block length (or positive at a non-block entry), with final phase PC inside the same region, proves region execution. Equal/shorter returns are ambiguous, not counted as proof. Baseline public run reaches equal retirement endpoints; complete state and pins are checked in bounded chunks. Not a speed or whole-song trace.',cases:[]};
const output=resolve(root,values.out);mkdirSync(dirname(output),{recursive:true});const save=()=>writeFileSync(output,json(report));save();
for(const id of ['rhythmic','lumiere-stereo','hq4-chego-tiny']){
  const entry=entries.find(e=>e.id===id),binary=parseHex(entry.flashHex);assert.equal(sha(binary),entry.flashSha256);
  const hz=entry.cpuHz||9600000,table=Array(128).fill(0);table[0]=hz;
  const options={resumable:true,oscillatorHz:hz,osccalHz:table,fastIdle:false,nvmClockProfile:1,nvmCalibrationReferenceHz:hz};
  const eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):undefined;
  const a=new ATtiny13A(binary,eeprom,{...options,boundedRegions:true}),b=new ATtiny13A(binary,eeprom,options);
  const regions=a.transpilation.regions.map(r=>({...r,attempts:0,provenBatches:0,provenInstructions:0,otherReturns:0,declined:0}));
  const byPc=new Map(regions.flatMap(r=>r.pcs.map(pc=>[pc,r]))),baseCounts=new Map(b.transpilation.blocks.map(r=>[r.start,r.instructions]));
  const p=a._phaseABI,view=new DataView(a._exports.memory.buffer),retired=()=>view.getBigUint64(p.retired,true);
  let done=0,pending=0,checkpoints=0;const pinDigests=[];
  while(done<instructions){
    const pc=a.pc,region=byPc.get(pc),before=retired(),count=a._execute('block',Infinity,Math.min(64,instructions-done));
    if(region){region.attempts++;
      if(count>(baseCounts.get(pc)||0)&&region.pcs.includes(view.getUint32(p.execPc,true))){region.provenBatches++;region.provenInstructions+=count;}
      else if(count)region.otherReturns++;else region.declined++;
    }
    if(!count)a.step();const n=Number(retired()-before);assert.ok(n>=0&&n<=64);done+=n;pending+=n;
    if(pending>=256||done===instructions){
      assert.equal(b.run(pending),pending);assert.deepEqual(snapshot(a),snapshot(b),id+' at'+done);
      const pins=a.drainPinsPs();assert.deepEqual(pins,b.drainPinsPs());pinDigests.push(sha(json(pins)));
      assert.equal(a.state().deviceFault,0);pending=0;checkpoints++;
    }
  }
  const row={id,flashSha256:sha(binary),moduleBytes:[b.transpiledBytes.length,a.transpiledBytes.length],
    generatedSha256:[sha(b.transpiledBytes),sha(a.transpiledBytes)],regions,checkpoints,stateSha256:sha(json(snapshot(a))),
    pinsSha256:sha(json(pinDigests)),finalTimePs:a.state().timePs,finalCycles:a.cyc,irqCount:a.irqCount};
  report.cases.push(row);save();console.log(json({id,regions:regions.length,
    provenBatches:regions.reduce((n,r)=>n+r.provenBatches,0),provenInstructions:regions.reduce((n,r)=>n+r.provenInstructions,0),checkpoints}).trim());
}
report.complete=true;save();
