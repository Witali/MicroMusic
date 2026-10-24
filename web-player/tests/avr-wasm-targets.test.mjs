import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore as Native} from '../lib/avr-wasm.js';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {Renderer as NativeRenderer} from '../lib/renderer.js';
import {Renderer as JSRenderer} from '../lib/renderer-js.js';
import {AVR_PROFILES} from '../lib/avr-profiles.js';
import {parseHex} from '../lib/hex.js';
const bytes=words=>Uint8Array.from(words.flat().flatMap(w=>[w&255,w>>8]));
const out=(a,d=17)=>0xb800|(d<<4)|(a&15)|((a&48)<<5);
const ldi=(d,k)=>0xe000|((d-16)<<4)|(k&15)|((k&240)<<4);
const sts=(a,d=17)=>[0x9200|(d<<4),a];
const lds=(a,d=17)=>[0x9000|(d<<4),a];
const make=(Type,words=[0],options={})=>new Type(bytes(words),null,{target:'attiny88',...options});
const pair=(words,options)=>[make(Native,words,options),make(JS,words,options)];
const same=(a,b)=>{
 assert.deepEqual(a.data,b.data);assert.deepEqual(a.irqFrames,b.irqFrames);
 for(const key of ['pc','cyc','timer','timerDivisor','prescalerAt','overflowAt','irqDelay',
  'irqStart','irqCount','lost','maxIRQ','writes','leftWrites','inIRQ','minSP','workLost',
  'duty','dutyLeft','eempeUntil','clkprUntil','timerTemp','wdtUntil','watchdogResetAt','watchdogResets'])
  assert.equal(a[key],b[key],key);
};
const both=(cores,operation)=>{const result=cores.map(operation);assert.equal(result[0],result[1]);same(...cores);return result[0];};

test('native instances apply shared profiles, isolate configuration and retain fixed memory',()=>{
 const small=new Native(bytes([0])),large=make(Native);
 assert.deepEqual(small.profile,AVR_PROFILES.attiny13a);assert.deepEqual(large.profile,AVR_PROFILES.attiny88);
 for(const c of [small,large]){
  assert.equal(c.rom.length,c.profile.flashBytes);assert.equal(c.data.length,c.profile.ramEnd+1);
  assert.equal(c.sram.length,c.profile.ramEnd-c.profile.sramStart+1);
  assert.equal(c.sp,c.profile.ramEnd);assert.equal(c._exports.memory.buffer.byteLength,2*65536);
  assert.throws(()=>c._exports.memory.grow(1),RangeError);
 }
 const configuration=small._configuration.slice();large._configuration.fill(0);
 assert.deepEqual(small._configuration,configuration);
 assert.throws(()=>new Native(new Uint8Array(8193),null,{target:'attiny88'}),/Flash/);
 assert.throws(()=>make(Native,[0],{target:'unsupported'}),/Unsupported AVR target/);
 assert.equal(new Native(bytes([0]),Uint8Array.of(1),{target:'tiny88'}).eeprom[0],1);
 assert.throws(()=>new Native(bytes([0]),Uint8Array.of(1)),/EEPROM must contain 64/);
});

test('native ATtiny88 decoder agrees with shared JS on every opcode and full LDS operand',()=>{
 const [a,b]=pair();
 for(const c of [a,b]){c.rom[2]=0x90;c.rom[3]=0x81;}
 for(let word=0;word<65536;word++){
  for(const c of [a,b]){c.rom[0]=word;c.rom[1]=word>>8;c.decode(0);}
  for(const key of ['op','d','s','k','batch','idle'])assert.equal(a[key][0],b[key][0],key+' '+word.toString(16));
 }
});

test('native ATtiny88 reads, writes and batches full pointers across SRAM pages',()=>{
 const cores=pair([0x900d|(17<<4),0x920d|(18<<4),0x900e|(19<<4),out(0x1e)]);
 for(const c of cores){c.r[26]=255;c.r[27]=1;c.data[0x1ff]=0x81;c.r[18]=0x53;}
 for(let n=0;n<3;n++)both(cores,c=>c.step());
 assert.equal(cores[0].r[19],0x53);assert.equal(cores[0].r[27],2);
 const block=pair([0x900d|(17<<4),0x920d|(18<<4),0x900d|(19<<4),out(0x1e)]);
 for(const c of block){c.r[26]=255;c.r[27]=1;c.r[18]=73;c.data[0x1ff]=129;c.data[0x201]=17;}
 assert.equal(both(block,c=>c.runBlock()),true);assert.equal(block[0].cyc,6);
 for(const c of cores){c.sp=0x2e0;c.pushPC(0xabc);assert.equal(c.popPC(),0xabc);}
 same(...cores);
});

test('native Timer1 TEMP latches high bytes and normal/fast overflow events match large clocks',()=>{
 const cores=pair();
 for(const [a,v] of [[0x85,0x12],[0x84,0x34],[0x89,0x56],[0x88,0x78]])both(cores,c=>c.writeData(a,v));
 assert.equal(cores[0].data[0x85],0x12);assert.equal(cores[0].data[0x89],0x56);
 both(cores,c=>c.readData(0x84));assert.equal(both(cores,c=>c.readData(0x85)),0x12);
 for(const [a,v] of [[0x85,0],[0x84,0],[0x80,0x21],[0x81,9]])both(cores,c=>c.writeData(a,v));
 assert.equal(cores[0].overflowAt,255);
 for(const n of [254,1,256,2**32+768])both(cores,c=>c.clock(n));
 assert.equal(cores[0].pending,true);
 both(cores,c=>c.writeData(0x36,1));
 assert.equal(cores[0].pending,false);
 for(const [a,v] of [[0x81,0],[0x80,0],[0x81,1]])both(cores,c=>c.writeData(a,v));
 assert.equal(cores[0].timerTop(),65535);
 both(cores,c=>c.clock(65536*7+3));
});

test('native protected watchdog reset/disable and expiration retain shared JS errors',()=>{
 const words=[0x94f8,0x95a8,ldi(17,0),out(0x34),lds(0x60,16),0x6108,sts(0x60,16),sts(0x60,17)];
 for(const prescaler of [0,1,7,0x20,0x21]){
  const cores=pair(words);
  for(const c of cores){c.data[0x54]=8;c.data[0x60]=8|prescaler;}
  for(let n=0;n<8;n++)both(cores,c=>c.step());
  assert.equal(cores[0].data[0x60],0);assert.equal(cores[0].watchdogResets,1);
 }
 const cores=pair();both(cores,c=>c.writeData(0x60,24));both(cores,c=>c.clock(3));
 for(const c of cores)assert.throws(()=>c.clock(1),/Watchdog disable window expired/);same(...cores);
 for(const c of cores)assert.throws(()=>c.writeData(0x60,0),/Enabled watchdog/);same(...cores);
});

test('instruction-boundary EEPROM observations capture every real JS/native read',()=>{
 // Firmware audits observe the SBI boundary, which is visible in both engines.
 // Native bus operations run inside C and need no JavaScript I/O callback.
 const eeprom=Uint8Array.from({length:64},(_,a)=>(a*67+15)&255);
 const program=[ldi(26,0xe0),ldi(27,1)],readPCs=new Set();
 for(let a=0;a<eeprom.length;a++){
  program.push(ldi(16,a),out(33,16));readPCs.add(program.length);
  program.push(0x9af8,0xb000|(17<<4)|((32&48)<<5),0x920d|(17<<4));
 }
 const end=program.length,rom=bytes([...program,0x94f8]),cores=[];
 for(const Type of [Native,JS]){
  const c=new Type(rom,eeprom,{target:'attiny88'}),observed=[];cores.push(c);
  for(const pc of readPCs)c.batch[pc]=0;
  while(c.pc<end){
   if(readPCs.has(c.pc))observed.push(c.data[c.profile.system.eear]);
   if(!c.runBlock())c.step();
  }
  assert.deepEqual(observed,Array.from({length:64},(_,a)=>a));
  assert.deepEqual(c.data.subarray(0x1e0,0x220),eeprom);
  assert.equal(c.cyc,2+64*11,'Each EERE SBI consumes two bus cycles plus four stalled cycles');
 }
 same(...cores);
});

test('watchdog expiration aborts an instruction before its bus write or IRQ side effects',()=>{
 const io=pair([sts(0x60)]);
 for(const c of io){c.r[17]=0;c.writeData(0x60,24);c.clock(3);}
 for(const c of io)assert.throws(()=>c.step(),/Watchdog disable window expired/);
 same(...io);assert.equal(io[0].data[0x60],8,'expired protected write cannot disable WDE');
 const irq=pair();
 for(const c of irq){c.i=1;c.pending=true;c.data[0x6f]=1;c.writeData(0x60,24);}
 for(const c of irq)assert.throws(()=>c.interrupt(),/Watchdog disable window expired/);
 same(...irq);assert.equal(irq[0].irqCount,0);
 const block=pair(Array(64).fill(0));
 for(const c of block)c.writeData(0x60,24);
 for(const c of block)assert.throws(()=>c.runBlock(),/Watchdog disable window expired/);
 same(...block);assert.equal(block[0].blockInstructions,0);
});

const catalog=JSON.parse(readFileSync(new URL('../firmware-attiny88.json',import.meta.url)));
for(const entry of catalog.entries)test(entry.id+': native ATtiny88 PWM/IRQ and complete RAM match JS for one second',()=>{
 const rom=parseHex(entry.flashHex,8192),ep=entry.eepromHex?parseHex(entry.eepromHex,64):null;
 const cores=[new Native(rom,ep,{target:'attiny88'}),new JS(rom,ep,{target:'attiny88'})];
 for(let n=0;n<entry.pwmHz;n++){
  assert.equal(cores[0].nextDuty(),cores[1].nextDuty());
  if(n%251===0)same(...cores);
 }
 same(...cores);assert.equal(cores[0].lost,0);assert.equal(cores[0].workLost,0);
});
for(const rate of [22050,48000,96000])for(const entry of catalog.entries.filter(e=>['lumiere-stereo','cancion-del-mariachi-sparse'].includes(e.id)))
 test(entry.id+': ATtiny88 native raw/filtered PCM and control changes match JS at '+rate,()=>{
  const controls={cutoff:9000,volume:.65},a=new NativeRenderer(entry,rate,controls),b=new JSRenderer(entry,rate,controls);
  for(const count of [4096,17,8192]){
   const actual=a.render(count),expected=b.render(count);same(a.core,b.core);
   assert.deepEqual(a.core.rawSamples,b.core.rawSamples);
   let max=0;for(let n=0;n<actual.length;n++)max=Math.max(max,Math.abs(actual[n]-expected[n]));
   assert.ok(max<2e-7,'PCM error '+max);
   for(const c of [a,b])c.setAudioControls({cutoff:4000,volume:.2});
  }
 });
