import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRMusicTargetCore as Core,TARGET_PROFILES} from './avr-music-target-core.mjs';

const out=(a,d=17)=>0xb800|(d<<4)|(a&15)|((a&48)<<5);
const input=(a,d=17)=>0xb000|(d<<4)|(a&15)|((a&48)<<5);
const sts=(a,d=17)=>[0x9200|(d<<4),a];
const lds=(a,d=17)=>[0x9000|(d<<4),a];
const ldi=(d,k)=>0xe000|((d-16)<<4)|(k&15)|((k&240)<<4);
const rom=words=>Uint8Array.from(words.flat().flatMap(w=>[w&255,w>>8]));
const make=(...words)=>new Core(rom(words),null,{fastIdle:false,fastBlocks:false});
const write=(c,a,v)=>c.writeIO(a-32,v);
const start=(c,divisor=1)=>{write(c,0x80,0x21);write(c,0x81,8|divisor);};
const word=(c,a)=>c.data[a]|c.data[a+1]<<8;

test('ATtiny88 memory geometry, image limits and target selection',()=>{
 const c=make(0);assert.equal(c.profile,TARGET_PROFILES.tiny88);
 assert.equal(c.rom.length,8192);assert.equal(c.eeprom.length,64);
 assert.equal(c.data.length,0x300);assert.equal(c.sram.length,512);
 assert.equal(c.sp,0x2ff);assert.equal(c.cpuHz,8000000);
 assert.equal(new Core(rom([0]),null,{target:'attiny88'}).target,'tiny88');
 assert.throws(()=>new Core(new Uint8Array(8193)),/Flash/);
 assert.throws(()=>new Core(rom([0]),new Uint8Array(65)),/EEPROM/);
 assert.throws(()=>new Core(rom([0]),null,{target:'unknown'}),/Unsupported/);
});

test('postincrement and predecrement use complete 16-bit pointers',()=>{
 const c=make(0x900d|(17<<4),0x920d|(18<<4),0x900e|(19<<4));
 c.r[26]=255;c.r[27]=1;c.data[0x1ff]=0x81;c.r[18]=0x53;
 c.step();assert.equal(c.r[17],0x81);assert.equal(word(c,26),0x200);
 c.step();assert.equal(c.data[0x200],0x53);assert.equal(word(c,26),0x201);
 c.step();assert.equal(c.r[19],0x53);assert.equal(word(c,26),0x200);
 assert.equal(c.cyc,6);
});

test('displaced Y access preserves its pointer across a page boundary',()=>{
 // LDD r17,Y+63: q5→bit13, q4..3→bits11..10, q2..0→bits2..0.
 const q=63,w=0x8008|(17<<4)|(q&7)|((q&24)<<7)|((q&32)<<8);
 const c=make(w);c.r[28]=0xf0;c.r[29]=1;c.data[0x22f]=0x9b;c.step();
 assert.equal(c.r[17],0x9b);assert.equal(word(c,28),0x1f0);
});

test('batched SRAM accesses match single stepping with pointer carry',()=>{
 const bytes=rom([0x900d|(17<<4),0x920d|(18<<4),0x900d|(19<<4),out(0x1e)]);
 const a=new Core(bytes,null,{fastIdle:false}),b=new Core(bytes,null,{fastIdle:false});
 for(const c of[a,b]){c.r[26]=255;c.r[27]=1;c.r[18]=73;c.data[0x1ff]=129;c.data[0x201]=17;}
 assert.equal(a.runBlock(),true);while(b.cyc<a.cyc)b.step();
 assert.deepEqual(a.data,b.data);assert.equal(a.pc,b.pc);assert.equal(a.cyc,6);
});

test('stack and mapped SPH/SPL preserve 12-bit Flash return addresses',()=>{
 const c=make(out(0x3e,17),out(0x3d,18));c.r[17]=2;c.r[18]=0xe0;
 c.step();c.step();assert.equal(c.sp,0x2e0);
 c.pushPC(0xabc);assert.equal(c.sp,0x2de);
 assert.deepEqual(Array.from(c.data.subarray(0x2df,0x2e1)),[0x0a,0xbc]);
 assert.equal(c.popPC(),0xabc);assert.equal(c.sp,0x2e0);
 c.sp=0x100;c.push(1);assert.throws(()=>c.push(2),/Stack overflow/);
});

test('Flash fetch, LPM and PC wrap work beyond the former 1 KB limit',()=>{
 const bytes=new Uint8Array(8192);bytes[4096]=ldi(17,0xa5)&255;bytes[4097]=ldi(17,0xa5)>>8;
 const c=new Core(bytes,null,{fastIdle:false});c.pc=2048;c.step();assert.equal(c.r[17],0xa5);
 c.pc=4095;c.step();assert.equal(c.pc,0);
 const l=make(0x9005|(17<<4));l.rom[0x1fff]=0x3c;l.r[30]=255;l.r[31]=31;l.step();
 assert.equal(l.r[17],0x3c);assert.equal(word(l,30),0x2000);
});

test('STS/LDS reach extended Timer1 mask and clock prescaler at their final cycle',()=>{
 const c=make(sts(0x61,17),sts(0x61,18),sts(0x6f,19),lds(0x6f,20));
 c.r[17]=128;c.r[18]=0;c.r[19]=1;c.step();assert.equal(c.clkprUntil,6);
 c.step();assert.equal(c.data[0x61],0);c.step();assert.equal(c.data[0x6f],1);
 c.step();assert.equal(c.r[20],1);assert.equal(c.cyc,8);
 assert.throws(()=>write(c,0x6f,2),/non-overflow/);
});

test('reset clears MCUSR and disables the watchdog within its protected four cycles',()=>{
 const c=make(0x94f8,ldi(17,0),out(0x34),ldi(16,24),sts(0x60,16),sts(0x60,17));
 c.data[0x54]=8;
 for(let n=0;n<5;n++)c.step();
 assert.equal(c.data[0x54],0);assert.equal(c.data[0x60],24);assert.equal(c.wdtUntil,c.cyc+4);
 c.step();assert.equal(c.data[0x60],0);assert.equal(c.wdtUntil,0);assert.equal(c.cyc,8);
 c.clock(1000000);assert.equal(c.data[0x60],0);
});

test('watchdog unlock expires; persistent watchdog and interrupt modes fail closed',()=>{
 const c=make(0);write(c,0x60,24);c.clock(3);assert.equal(c.data[0x60],24);
 assert.throws(()=>c.clock(1),/disable window expired/);
 assert.equal(c.data[0x60]&16,0);assert.equal(c.data[0x60]&8,8);
 assert.throws(()=>write(c,0x60,0),/Enabled watchdog/);
 for(const value of[8,9,16,32,64,128])assert.throws(()=>write(make(0),0x60,value),/watchdog/);
 const forced=make(0);forced.data[0x54]=8;write(forced,0x60,24);
 assert.throws(()=>write(forced,0x60,0),/Enabled watchdog/,'WDRF must be cleared before disabling WDE');
});

test('WDR is one cycle and startup preserves an inherited watchdog prescaler while unlocking',()=>{
 for(const prescaler of[0,1,7,0x20,0x21]){
  const c=make(0x94f8,0x95a8,ldi(17,0),out(0x34),lds(0x60,16),
   0x6000|((16-16)<<4)|(24&15)|((24&240)<<4),sts(0x60,16),sts(0x60,17));
  c.data[0x54]=8;c.data[0x60]=8|prescaler;
  c.step();c.step();assert.equal(c.watchdogResetAt,2);assert.equal(c.watchdogResets,1);
  for(let n=0;n<5;n++)c.step();
  assert.equal(c.data[0x60],24|prescaler);assert.equal(c.wdtUntil,c.cyc+4);
  c.step();assert.equal(c.data[0x60],0);assert.equal(c.wdtUntil,0);
 }
 const wrong=make(0);wrong.data[0x60]=3;
 assert.throws(()=>write(wrong,0x60,24),/watchdog/,'unlock cannot change WDP before resetting the counter');
});

for(const[source,divisor]of[[1,1],[2,8],[3,64],[4,256],[5,1024]]){
 test(`Timer1 fast PWM TOP=255, /${divisor}: exact first and repeated TOV edges`,()=>{
  const c=make(0);start(c,source);assert.equal(c.timerMode(),5);
  assert.equal(c.overflowAt,255*divisor);c.clock(255*divisor-1);assert.equal(c.pending,false);
  c.clock(1);assert.equal(c.pending,true);assert.equal(c.timerCounter(),255);
  assert.equal(c.overflowAt,511*divisor);assert.equal(c.data[0x36]&1,1);
  write(c,0x36,0);assert.equal(c.pending,true);write(c,0x36,1);assert.equal(c.pending,false);
  c.clock(256*divisor);assert.equal(c.pending,true);assert.equal(c.lost,0);
  c.clock(2*256*divisor);assert.equal(c.lost,2);
 });
}

test('normal Timer1 counts sixteen bits and shares TEMP between high-byte writes',()=>{
 const c=make(0);write(c,0x85,0x12);write(c,0x84,0xfe);
 assert.equal(c.timerCounter(),0x12fe);write(c,0x81,1);c.clock(2);assert.equal(c.timerCounter(),0x1300);
 const low=c.readData(0x84);assert.equal(low,0);c.clock(256);
 assert.equal(c.readData(0x85),0x13,'high read uses the low-read latch');
 write(c,0x89,0);write(c,0x88,0x81);write(c,0x8a,0x79);
 assert.equal(word(c,0x88),0x81);assert.equal(word(c,0x8a),0x79);
 assert.equal(c.timerTemp,0,'low OCR writes retain shared high-byte TEMP');
});

test('Timer1 high-byte writes stay buffered until the following low byte',()=>{
 const c=make(0);write(c,0x89,0x25);assert.equal(word(c,0x88),0);
 write(c,0x8a,0x71);assert.equal(word(c,0x8a),0x2571,'shared TEMP also applies to the other channel');
 assert.equal(word(c,0x88),0);write(c,0x88,0x19);assert.equal(word(c,0x88),0x2519);
 write(c,0x85,0xff);write(c,0x84,0xfe);write(c,0x81,1);
 c.clock(1);assert.equal(c.pending,false);c.clock(1);assert.equal(c.pending,true);
 assert.equal(c.timerCounter(),0);assert.equal(c.overflowAt,65538);
});

test('GTCCR reset/hold, power reduction and stop/restart preserve timer phase',()=>{
 const c=make(0);c.clock(3);write(c,0x43,1);start(c,2);
 c.clock(7);assert.equal(c.timerCounter(),0);c.clock(1);assert.equal(c.timerCounter(),1);
 write(c,0x43,0x81);c.clock(100);assert.equal(c.timerCounter(),1);assert.equal(c.timer,false);
 write(c,0x43,0);c.clock(8);assert.equal(c.timerCounter(),2);
 write(c,0x64,8);c.clock(100);assert.equal(c.timerCounter(),2);
 write(c,0x64,0);c.clock(8);assert.equal(c.timerCounter(),3);
});

test('overflow dispatches word 11, pushes real SRAM and advances Timer1 in IRQ entry',()=>{
 const c=make(0);start(c);write(c,0x6f,1);c.clock(254);c.i=1;c.step();
 assert.equal(c.pc,11);assert.equal(c.irqCount,1);assert.equal(c.cyc,259);
 assert.equal(c.sp,0x2fd);assert.equal(c.timerCounter(),3);assert.equal(c.pending,false);
 assert.deepEqual(Array.from(c.data.subarray(0x2fe)),[0,1]);
});

test('SEI delays dispatch until the next instruction and RETI restores the two-byte PC',()=>{
 const bytes=new Uint8Array(80);bytes.set(rom([0x9478,0]));bytes.set(rom([0x9518]),22);
 const c=new Core(bytes,null,{fastIdle:false,fastBlocks:false});write(c,0x6f,1);c.pending=true;
 c.step();assert.equal(c.pc,1);assert.equal(c.irqCount,0);
 c.step();assert.equal(c.pc,11);assert.equal(c.sp,0x2fd);
 c.step();assert.equal(c.pc,2);assert.equal(c.sp,0x2ff);assert.equal(c.i,1);
 assert.equal(c.maxIRQ,8);
});

test('EEPROM read stalls four cycles while Timer1 continues and EERE self-clears',()=>{
 const c=make(out(0x1f));c.eeprom[63]=0xa5;write(c,0x41,255);c.r[17]=1;start(c);c.clock(252);
 c.step();assert.equal(c.cyc,257);assert.equal(c.timerCounter(),1);
 assert.equal(c.data[0x40],0xa5);assert.equal(c.data[0x3f]&1,0);assert.equal(c.data[0x41],63);
 assert.equal(c.pending,true);assert.throws(()=>write(c,0x3f,2),/programming/);
});

test('SBI, STS and indirect EEPROM reads use the same stall and side effects',()=>{
 for(const words of[[0x9a00|(0x1f<<3)],sts(0x3f),[0x9201|(17<<4)]]){
  const c=make(words);c.eeprom[17]=0x8d;write(c,0x41,17);c.r[17]=1;c.r[30]=0x3f;
  start(c);c.step();assert.equal(c.cyc,6);assert.equal(c.timerCounter(),6);
  assert.equal(c.data[0x40],0x8d);assert.equal(c.data[0x3f]&1,0);
 }
});

test('actual OCR1A/B registers form stereo pairs; unrelated scratch writes produce no audio',()=>{
 const c=make(sts(0x88,18),sts(0x8a,17),out(0x1e,19));start(c);
 c.r[18]=61;c.r[17]=193;c.r[19]=7;
 assert.equal(c.nextStereoDuty(),61|(193<<8));assert.equal(c.leftWrites,1);assert.equal(c.writes,1);
 assert.equal(c.cyc,4);c.step();assert.equal(c.writes,1);assert.equal(c.data[0x3e],7);
 assert.equal(word(c,0x88),61);assert.equal(word(c,0x8a),193);
});

test('ported Timer1 ISR preserves SREG and YH across wrap in 18 mono / 22 stereo cycles',()=>{
 for(const stereo of[false,true]){
  const bytes=new Uint8Array(96);bytes.set(rom([0xcfff]));bytes.set(rom([0xc004]),22);
  const body=[...(stereo?sts(0x88,18):[]),...sts(0x8a,8),ldi(29,1),0x9009|(18<<4),
   ...(stereo?[0x9009|(8<<4)]:[]),ldi(29,0),0xfc00|(28<<4)|4,ldi(28,128),0x9518];
  bytes.set(rom(body),32);
  for(const pointer of[128,stereo?142:143])for(const flags of[0,1,2,31,63,127]){
   const c=new Core(bytes,null,{fastIdle:false});
   c.r[28]=pointer;c.r[29]=0;c.data.set([23,37],0x100+pointer);c.r[18]=51;c.r[8]=93;
   c.sreg=flags;write(c,0x6f,1);start(c);c.i=1;c.pending=true;c.interrupt();
   while(c.inIRQ)c.step();
   assert.equal(c.maxIRQ,stereo?22:18);assert.equal(c.sreg,flags|128);
   assert.equal(c.sp,0x2ff);assert.equal(c.r[29],0);
   assert.equal(c.r[28],pointer===128?128+(stereo?2:1):128);
  }
 }
});

test('unsupported timer modes, external clocks and CPU divisions fail explicitly',()=>{
 for(const mode of[1,2,3,4,6,7,8,9,10,11,12,13,14,15]){
  const c=make(0);write(c,0x80,mode&3);
  assert.throws(()=>write(c,0x81,1|((mode&12)<<1)),/WGM/);
 }
 for(const source of[6,7])assert.throws(()=>start(make(0),source),/External/);
 const c=make(0);write(c,0x61,128);assert.throws(()=>write(c,0x61,1),/division/);
});
