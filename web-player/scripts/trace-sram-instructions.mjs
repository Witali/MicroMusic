// Untimed retired-instruction census, with a paired production block runner.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {parseArgs} from 'node:util';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {parseHex} from '../lib/hex.js';
import {decodeAVR} from '../lib/avr-transpiler.js';
import {deviceProfile} from '../lib/devices/profiles.js';
import {resolveAVRProfile} from '../lib/avr-profiles.js';
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{instructions:{type:'string',default:'50000'},case:{type:'string',multiple:true},
  out:{type:'string',default:'build/sram-instruction-trace.json'}}});
const instructions=Number(values.instructions);assert.ok(Number.isInteger(instructions)&&instructions>=256&&instructions<=1000000);
const selected=values.case??['rhythmic','lumiere-stereo','hq4-chego-tiny'];assert.equal(new Set(selected).size,selected.length);
const sha=b=>createHash('sha256').update(b).digest('hex');
const json=v=>JSON.stringify(v,(_,x)=>typeof x==='bigint'?x.toString():x,2)+'\n';
const source=p=>readFileSync(resolve(root,p),'utf8').replaceAll('\r\n','\n');
for(const [p,expected] of Object.entries(AVR_CACHE_SOURCES))assert.equal(sha(source(p)),expected,p+' compiler identity');
const catalogs=['web-player/firmware.json','web-player/hq4-firmware.json'];
const entries=catalogs.flatMap(p=>JSON.parse(source(p)).entries);
const out=resolve(root,values.out);mkdirSync(dirname(out),{recursive:true});
const {ramStart,ramEnd}=deviceProfile('ATtiny13A');
const snapshot=c=>({state:c.state(),data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),irq:Array.from(c.irqFrames)});
const report={schema:'micromusic-sram-instruction-trace-v1',complete:false,
  revision:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  node:process.version,instructions,checkpointInstructions:256,compilerIdentity:AVR_CACHE_COMPILER_ID,
  sourceSha256:{...AVR_CACHE_SOURCES,...Object.fromEntries([...catalogs,'web-player/scripts/trace-sram-instructions.mjs'].map(p=>[p,sha(source(p))]))},
  runtimeSha256:sha(getRuntimeBytes()),
  method:'Untimed instruction prefix. Native ready arbitrates IRQ before reading PC. Each step must retire exactly one instruction. Every256 instructions, compare full state/data/Flash/EEPROM/IRQ frames and exact retained pins against the ordinary production run path. No host timing or exclusive-cost claim. Flash self-modification is rejected so PC counts have one opcode identity.',cases:[]};
const save=()=>writeFileSync(out,json(report));save();
for(const id of selected){
  const entry=entries.find(e=>e.id===id);assert.ok(entry,id+' catalog entry');
  assert.equal(resolveAVRProfile(entry.device).id,'attiny13a','ATtiny13A trace target');
  const image=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):undefined;
  assert.equal(sha(image),entry.flashSha256);
  const hz=entry.cpuHz||9600000,table=Array(128).fill(0);table[0]=hz;
  const options={resumable:true,oscillatorHz:hz,osccalHz:table,fastIdle:false,nvmClockProfile:1,nvmCalibrationReferenceHz:hz};
  const a=new ATtiny13A(image,eeprom,options),b=new ATtiny13A(image,eeprom,options);a.run(0);b.run(0);
  const counts=new Map();let checked=0,checkpoints=0;
  for(let n=0;n<instructions;n++){
    assert.equal(a._exports.avr_device_ready(),1);const pc=a.pc,before=a.state().cpuPhase.retired;
    a.step();assert.equal(a.state().cpuPhase.retired,before+1n);counts.set(pc,(counts.get(pc)||0)+1);
    if((n+1)%256===0||n+1===instructions){
      assert.equal(b.run(n+1-checked),n+1-checked);
      assert.equal(a._exports.avr_device_ready(),1);assert.equal(b._exports.avr_device_ready(),1);
      assert.deepEqual(snapshot(a),snapshot(b),id+' '+(n+1));assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
      assert.equal(a._exports.avr_device_generation(),0n,'SPM needs opcode-versioned tracing');checked=n+1;checkpoints++;
    }
  }
  const word=p=>a.rom[p*2]|(a.rom[p*2+1]<<8);
  const memory=[...counts].map(([pc,count])=>({pc,count,word:word(pc),...decodeAVR(word(pc),word((pc+1)&511))}))
    .filter(i=>['LD','ST','LDS','STS','LPM'].includes(i.name));
  const direct=memory.filter(i=>['LDS','STS'].includes(i.name)&&i.k>=ramStart&&i.k<=ramEnd);
  const row={id,options,flashSha256:sha(image),eepromSha256:eeprom?sha(eeprom):null,memory,
    directExecutions:direct.reduce((n,i)=>n+i.count,0),memoryExecutions:memory.reduce((n,i)=>n+i.count,0),
    checkpoints,finalTimePs:a.state().timePs,irqs:a.state().irqs,stateSha256:sha(json(snapshot(a)))};
  report.cases.push(row);save();console.log(JSON.stringify({id,direct:row.directExecutions,memory:row.memoryExecutions,checkpoints}));
}
report.complete=true;save();
