import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {AVRCore as JS13} from '../web-player/lib/avr-reference.js';
import {AVRCore as WASM13} from '../web-player/lib/avr-core.js';
import {AVRMusicTargetCore as JS88} from './avr-music-target-core.mjs';

export const baseline=JSON.parse(fs.readFileSync(new URL('./fixtures/attiny-music-startup-baseline.json',import.meta.url)));
export const engines=[['ATtiny13A','JS',JS13,'flash13'],['ATtiny13A','WASM',WASM13,'flash13'],['ATtiny88','JS',JS88,'flash88']];
const sha=b=>createHash('sha256').update(b).digest('hex');
const folder=(target,name)=>new URL(`../${target}/Music/variants/${name}/`,import.meta.url);
function startup(Core,rom,ep){
  const c=new Core(rom,ep,{fastIdle:false,fastBlocks:false}),writes=[];
  let steps=0;
  while(!c.i&&steps++<5000){
    const pc=c.pc*2,w=c.rom[pc]|c.rom[pc+1]<<8;
    if((w&0xf800)===0xb800)writes.push({address:32+((w>>5)&48)+(w&15),cycle:c.cyc,pc,bytes:2});
    if((w&0xfe0f)===0x9200)writes.push({address:c.rom[pc+2]|c.rom[pc+3]<<8,cycle:c.cyc,pc,bytes:4});
    if((w&0xff00)===0x9a00)writes.push({address:32+((w>>3)&31),cycle:c.cyc,pc,bytes:2});
    c.step();
  }
  assert.ok(steps<5000,'The real program must reach its first SEI');
  return {c,writes};
}
export function auditVariant(name,[target,engine,Core,key]){
  const saved=baseline.variants[name],dir=folder(target,name);
  const rom=fs.readFileSync(new URL('synth.bin',dir)),ep=fs.readFileSync(new URL('eeprom.bin',dir));
  const oldRom=Buffer.from(saved[key],'hex'),oldEp=Buffer.from(saved[target==='ATtiny88'?'eeprom88':'eeprom'],'hex');
  const originalHash=sha(oldRom),correctedStereoAddress=target==='ATtiny13A'&&name==='lumiere-stereo';
  if(correctedStereoAddress){
    // The old software model also used reserved I/O 0x2A for channel A.
    // Normalize exactly the two OUT instructions to real OCR0A=0x36.
    let corrected=0;
    for(let pc=0;pc<oldRom.length;pc+=2){
      const w=oldRom.readUInt16LE(pc);
      if((w&0xf800)===0xb800&&(((w>>5)&48)+(w&15))===0x2a){
        oldRom.writeUInt16LE(0xb800|(w&0x1f0)|((0x36&48)<<5)|(0x36&15),pc);corrected++;
      }
    }
    assert.equal(corrected,2,'Only startup and ISR left-channel OUT addresses change');
  }
  assert.deepEqual(ep,oldEp,'Wavetables and DDS data in EEPROM must remain unchanged');
  const {c:before,writes:oldWrites}=startup(Core,oldRom,oldEp),{c:after,writes}=startup(Core,rom,ep);
  assert.equal(after.pc,before.pc);assert.equal(rom.length,oldRom.length);
  assert.deepEqual(rom.subarray(after.pc*2),oldRom.subarray(before.pc*2),
    'Every executable byte and score byte after startup must remain identical');
  assert.deepEqual(after.data,before.data,'CPU registers, SRAM and peripheral registers after SEI');
  for(const field of ['cyc','sp','timer','pending','overflowAt','timerDivisor','irqDelay',
    'duty','dutyLeft','writes','leftWrites','irqCount','lost','workLost','timerTemp'])
    assert.equal(after[field],before[field],`Startup must preserve ${field}`);
  const tiny88=target==='ATtiny88',com=tiny88?0x80:0x4f,ddr=tiny88?0x24:0x37;
  const addresses=new Set([com,ddr,...(tiny88?[0x88,0x8a]:[0x49,0x56])]);
  const setup=[...oldWrites,...writes].filter(w=>addresses.has(w.address));
  const first=Math.min(...setup.map(w=>w.pc)),last=Math.max(...setup.map(w=>w.pc+w.bytes));
  assert.deepEqual(rom.subarray(0,first),oldRom.subarray(0,first),'Helpers preceding reset remain identical');
  assert.deepEqual(rom.subarray(last),oldRom.subarray(last),'All code outside pin setup remains identical');
  assert.ok(writes.findIndex(w=>w.address===com)<writes.findIndex(w=>w.address===ddr),
    'OC/COM must be configured before DDR enables the physical output');
  assert.equal(after.data[ddr],name==='lumiere-stereo'?(tiny88?6:3):(tiny88?4:2));
  assert.equal(after.data[tiny88?0x25:0x38],0,'PORTB latch starts low');
  assert.equal(after.timerMode(),tiny88?5:3);
  return {variant:name,target,engine,flashBytes:rom.length,flashSha256:sha(rom),
    eepromSha256:sha(ep),baselineFlashSha256:originalHash,seiByteAddress:after.pc*2,
    cyclesThroughSei:after.cyc,allStateBytesIdentical:true,allCodeAndMusicAfterSeiIdentical:true,
    compareConfiguredBeforeDdr:true,legacyStereoAddressNormalized:correctedStereoAddress};
}
export function audit(){
  const entries=Object.keys(baseline.variants).flatMap(name=>engines.map(engine=>auditVariant(name,engine)));
  return {baselineCommit:baseline.commit,method:'Execute both images through first SEI; compare complete CPU/SRAM/peripheral state, timer phase and ROM outside pin setup. For ATtiny13A stereo only, first normalize the two old reserved-address OUT instructions to real OCR0A=0x36. This preserves the old software-model audio while correcting its hardware mapping.',
    modelsOnly:true,electricalPwmEdgesMeasured:false,entries};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  const result=audit();
  fs.writeFileSync(new URL('../web-player/reports/music-startup-verification.json',import.meta.url),JSON.stringify(result,null,2)+'\n');
  console.log(`Startup equivalence: ${result.entries.length} checks passed for all 18 firmware images.`);
}
