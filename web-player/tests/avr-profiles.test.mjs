// These constants are independent of the implementation profiles. Register
// addresses are DATA-space values from Microchip DS40002307A and doc8008.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore as JS, AVR_PROFILES, resolveAVRProfile} from '../lib/avr-reference.js';
import {AVRCore as WASM} from '../lib/avr-core.js';

const targets = [
  {id:'attiny13a',folder:'ATtiny13A',flash:1024,start:0x60,end:0x9f,hz:9600000,
    a:0x4f,b:0x53,mode:3,mask:0x59,flag:0x58,bit:2,vector:3,first:255,
    counter:0x52,ocra:0x56,ocrb:0x49,eecr:0x3c,eedr:0x3d,eear:0x3e},
  {id:'attiny88',folder:'ATtiny88',flash:8192,start:0x100,end:0x2ff,hz:8000000,
    a:0x80,b:0x81,mode:1,mask:0x6f,flag:0x36,bit:1,vector:11,first:255,
    counter:0x84,ocra:0x88,ocrb:0x8a,eecr:0x3f,eedr:0x40,eear:0x41},
];
const engines = [['JS',JS],['WASM',WASM]];
const rom = words => Uint8Array.from(words.flat().flatMap(w=>[w&255,w>>8]));
const ldi = (d,k) => 0xe000|((d-16)<<4)|(k&15)|((k&240)<<4);
const rr = (op,d,s) => op|(d<<4)|(s&15)|((s&16)<<5);
const io = (op,d,a) => op|(d<<4)|(a&15)|((a&48)<<5);
const sts = (address,d) => [0x9200|(d<<4),address];
const make = (Core,t,words=[0],options={}) => new Core(rom(words),null,
  {target:t.id,fastIdle:false,fastBlocks:false,...options});
const write = (c,address,value) => c.writeIO(address-32,value);
const start = (c,t) => {write(c,t.a,t.mode);write(c,t.b,t.id==='attiny88'?9:1);};
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

test('profiles are canonical, recursively immutable and reject unknown devices',()=>{
  assert.equal(resolveAVRProfile(),AVR_PROFILES.attiny13a);
  for(const [alias,target]of [['tiny13','attiny13a'],['tiny13a','attiny13a'],
    ['attiny13','attiny13a'],['tiny88','attiny88']])
    assert.equal(resolveAVRProfile(alias),AVR_PROFILES[target]);
  assert.ok(Object.isFrozen(AVR_PROFILES));
  for(const profile of Object.values(AVR_PROFILES)){
    assert.ok(Object.isFrozen(profile));assert.ok(Object.isFrozen(profile.timer));
    assert.ok(Object.isFrozen(profile.system.externalInterrupts));
    assert.ok(Object.isFrozen(profile.system.externalInterrupts[0]));
    assert.throws(()=>{profile.timer.ocra=0x2a;},TypeError);
  }
  for(const invalid of ['unknown','atmega88a','constructor','__proto__',null,{}])
    assert.throws(()=>resolveAVRProfile(invalid),/Unsupported AVR target/);
});

for(const [engine,Core]of engines){
  test(`${engine}: default target and mixed-target instances own independent memory and decoder state`,()=>{
    const a=new Core(rom([ldi(17,3)])),b=make(Core,targets[1],[ldi(17,9)]),
      c=new Core(rom([ldi(17,5)]));
    assert.equal(a.target,'attiny13a');assert.equal(b.target,'attiny88');
    assert.equal(c.target,'attiny13a');
    for(const [x,y]of [[a,b],[a,c],[b,c]]){
      assert.notEqual(x.data.buffer,y.data.buffer);assert.notEqual(x.rom,y.rom);
      assert.notEqual(x.eeprom,y.eeprom);assert.notEqual(x.op,y.op);
    }
    a.r[0]=77;a.eeprom[0]=66;a.rom[0]=0;a.decode(0);
    assert.equal(b.r[0],0);assert.equal(c.r[0],0);
    assert.equal(b.eeprom[0],255);assert.equal(c.eeprom[0],255);
    b.step();c.step();assert.equal(b.r[17],9);assert.equal(c.r[17],5);
    assert.equal(a.pc,0);assert.equal(a.cyc,0);
    for(const invalid of ['unknown','atmega88a','constructor','__proto__',null,{}])
      assert.throws(()=>new Core(rom([0]),null,{target:invalid}),/Unsupported AVR target/);
  });

  for(const t of targets){
    const name=`${engine}/${t.id}`;
    test(`${name}: Flash, SRAM, mapped register aliases and image capacities`,()=>{
      const c=make(Core,t);
      assert.deepEqual(c.profile,AVR_PROFILES[t.id]);assert.ok(Object.isFrozen(c.profile));
      assert.equal(c.cpuHz,t.hz);
      assert.equal(c.rom.length,t.flash);assert.equal(c.words,t.flash/2);
      assert.equal(c.pcMask,t.flash/2-1);assert.equal(c.data.length,t.end+1);
      assert.equal(c.r.length,32);assert.equal(c.io.length,t.start-32);
      assert.equal(c.sram.length,t.end-t.start+1);assert.equal(c.sp,t.end);
      assert.equal(c.ram,c.sram);assert.equal(c.eeprom.length,64);
      c.r[7]=23;assert.equal(c.data[7],23);
      c.io[0]=41;assert.equal(c.data[32],41);
      c.sram[0]=67;c.data[t.end]=89;
      assert.equal(c.data[t.start],67);assert.equal(c.sram.at(-1),89);
      c.sreg=0x73;assert.equal(c.data[0x5f],0x73);
      c.sp=t.end-7;assert.equal(c.data[0x5d],(t.end-7)&255);
      if(t.id==='attiny88')assert.equal(c.data[0x5e],2);
      assert.equal(c.profile.timer.ocra,t.ocra);assert.equal(c.profile.timer.ocrb,t.ocrb);
      assert.equal(c.profile.timer.vector,t.vector);
      assert.throws(()=>new Core(new Uint8Array(0),null,{target:t.id}),/Flash/);
      assert.throws(()=>new Core(new Uint8Array(t.flash+1),null,{target:t.id}),/Flash/);
      assert.throws(()=>new Core(rom([0]),new Uint8Array(65),{target:t.id}),/EEPROM/);
      if(t.id==='attiny13a')
        assert.throws(()=>new Core(rom([0]),new Uint8Array(63),{target:t.id}),/EEPROM/);
      else {
        const short=new Core(rom([0]),Uint8Array.of(0x81),{target:t.id});
        assert.equal(short.eeprom[0],0x81);assert.equal(short.eeprom[63],255);
      }
    });

    test(`${name}: one common instruction program has independently specified results and timing`,()=>{
      // RCALL/RET, stack data, preserved carry, arithmetic flags, and a skip
      // over a two-word STS use exactly the same bytes on both devices.
      const c=make(Core,t,[ldi(16,255),ldi(17,1),rr(0x0c00,16,17),io(0xb000,20,63),
        ldi(18,127),ldi(19,0),rr(0x1c00,18,19),io(0xb000,21,63),
        0x920f|(18<<4),ldi(18,0),0x900f|(22<<4),0xd004,
        0xfc00|(16<<4),sts(0x5f,17),0xc002,0x9403|(22<<4),0x9508,
        io(0xb000,23,63),0xcfff]);
      const trace=[[1,1],[2,2],[3,3],[4,4],[5,5],[6,6],[7,7],[8,8],
        [9,10],[10,11],[11,13],[16,16],[17,17],[12,21],[15,24],[18,26],[19,27]];
      for(const [pc,cycles]of trace){c.step();assert.equal(c.pc,pc);assert.equal(c.cyc,cycles);}
      assert.deepEqual(Array.from(c.r.subarray(16,24)),[0,1,0,0,0x23,0x2c,0x81,0x34]);
      assert.equal(c.sreg,0x34);assert.equal(c.sp,t.end);assert.equal(c.minSP,t.end-2);
    });

    test(`${name}: final Flash word wraps a two-word STS operand and preserves the full return PC`,()=>{
      const binary=new Uint8Array(t.flash),last=t.flash/2-1;
      const word=0x9200|(17<<4);binary[t.flash-2]=word;binary[t.flash-1]=word>>8;
      binary[0]=t.start&255;binary[1]=t.start>>8;
      const c=new Core(binary,null,{target:t.id,fastIdle:false,fastBlocks:false});
      c.pc=last;c.r[17]=0xa5;c.step();
      assert.equal(c.data[t.start],0xa5);assert.equal(c.pc,1);assert.equal(c.cyc,2);
      c.pushPC(last);assert.equal(c.sp,t.end-2);
      assert.equal(c.data[t.end],last&255);assert.equal(c.data[t.end-1],last>>8);
      assert.equal(c.popPC(),last);assert.equal(c.sp,t.end);
    });

    test(`${name}: LPM uses the final Flash byte and increments all sixteen Z bits`,()=>{
      const binary=new Uint8Array(t.flash);binary.set(rom([0x9005|(17<<4)]));binary[t.flash-1]=0xa5;
      const c=new Core(binary,null,{target:t.id,fastIdle:false,fastBlocks:false});
      c.r[30]=(t.flash-1)&255;c.r[31]=(t.flash-1)>>8;c.step();
      assert.equal(c.r[17],0xa5);assert.equal(c.r[30]|c.r[31]<<8,t.flash);assert.equal(c.cyc,3);
    });

    test(`${name}: stack/data bounds use the configured SRAM instead of the other chip's limits`,()=>{
      const c=make(Core,t);c.sp=t.start;c.push(0x57);
      assert.equal(c.data[t.start],0x57);assert.equal(c.sp,t.start-1);
      assert.equal(c.pop(),0x57);assert.equal(c.sp,t.start);
      for(const operation of [x=>{x.sp=t.start;x.push(1);x.push(2);},
        x=>x.pop(),x=>x.readData(t.end+1),x=>x.writeData(t.end+1,1)])
        assert.throws(()=>operation(make(Core,t)),/Stack|Data/);
    });

    test(`${name}: configured PWM registers emit paired duties; other-chip/reserved addresses do not`,()=>{
      const scratch=t.id==='attiny13a'?0x4a:0x49;
      const c=make(Core,t,[sts(scratch,16),sts(t.ocra,17),sts(t.ocrb,18)]);
      start(c,t);c.r[16]=203;c.r[17]=51;c.r[18]=31;c.sreg=0x73;
      c.step();assert.equal(c.leftWrites,0);assert.equal(c.writes,0);
      assert.equal(c.nextStereoDuty(),51|(31<<8));
      assert.equal(c.leftWrites,1);assert.equal(c.writes,1);assert.equal(c.cyc,6);
      assert.equal(c.data[t.ocra],51);assert.equal(c.data[t.ocrb],31);assert.equal(c.sreg,0x73);
    });

    test(`${name}: overflow timing and dispatch use this chip's flag, mask and vector`,()=>{
      const c=make(Core,t);start(c,t);write(c,t.mask,t.bit);c.clock(t.first-1);
      assert.equal(c.pending,false);assert.equal(c.overflowAt,t.first);
      c.i=1;c.step();
      assert.equal(c.pc,t.vector);assert.equal(c.cyc,t.first+4);assert.equal(c.irqCount,1);
      assert.equal(c.pending,false);assert.equal(c.data[t.flag]&t.bit,0);
      assert.equal(c.sp,t.end-2);assert.equal(c.data[t.end],1);assert.equal(c.data[t.end-1],0);
      assert.equal(c.data[t.counter],3);
    });

    test(`${name}: SEI latency and RETI preserve the selected vector and two-byte return address`,()=>{
      const words=Array(t.vector+1).fill(0);words[0]=0x9478;words[t.vector]=0x9518;
      const c=make(Core,t,words);write(c,t.mask,t.bit);c.data[t.flag]=t.bit;
      c.step();assert.equal(c.pc,1);assert.equal(c.irqCount,0);
      c.step();assert.equal(c.pc,t.vector);assert.equal(c.sp,t.end-2);assert.equal(c.cyc,6);
      c.step();assert.equal(c.pc,2);assert.equal(c.sp,t.end);assert.equal(c.i,1);
      assert.equal(c.cyc,10);assert.equal(c.maxIRQ,8);
    });

    test(`${name}: EEPROM read map, four-cycle stall and programming rejection stay explicit`,()=>{
      const c=make(Core,t,[io(0xb800,17,t.eecr-32)]);c.r[17]=1;c.eeprom[63]=0xa5;
      write(c,t.eear,255);c.step();assert.equal(c.data[t.eear],63);
      assert.equal(c.data[t.eedr],0xa5);assert.equal(c.data[t.eecr]&1,0);assert.equal(c.cyc,5);
      // No write engine or EEPE startup polling is introduced by sharing CPU code.
      assert.throws(()=>write(make(Core,t),t.eecr,2),/EEPROM programming/);
    });
  }
}

const baseline=JSON.parse(readFileSync(new URL('./fixtures/avr-profile-baseline.json',import.meta.url)));
for(const entry of baseline.entries)for(const [engine,Core]of engines)
  test(`${engine}/${entry.target}/${entry.variant}: real firmware preserves immutable pre-refactor PWM and complete machine state`,()=>{
    const t=targets.find(t=>t.id===entry.target),base=`../../${t.folder}/Music/variants/${entry.variant}/`;
    const binary=readFileSync(new URL(base+'synth.bin',import.meta.url));
    const ep=readFileSync(new URL(base+'eeprom.bin',import.meta.url));
    assert.equal(hash(binary),entry.flashSha256);assert.equal(hash(ep),entry.eepromSha256);
    const c=new Core(binary,ep,{target:entry.target}),pwm=new Uint8Array(baseline.frames*2);
    for(let i=0;i<baseline.frames;i++){
      const value=entry.variant==='lumiere-stereo'?c.nextStereoDuty():c.nextDuty();
      pwm[i*2]=value&255;pwm[i*2+1]=value>>8;
    }
    assert.equal(hash(pwm),entry.pwmSha256);assert.equal(hash(c.data),entry.dataSha256);
    for(const [key,value]of Object.entries(entry.state))assert.equal(c[key],value,key);
    assert.deepEqual(Array.from(c.irqFrames),entry.irqFrames);
  });
