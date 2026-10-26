// Exercise the actual linked CRT/.init3 instructions after bootloader entry.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {AVRCore} from '../lib/avr-reference.js';
import {decodeAVR} from '../lib/avr-transpiler.js';
const base=new URL('../../ATtiny88/Music/universal/',import.meta.url);
const images=process.env.UM88_STARTUP_IMAGE_ROOT?
 pathToFileURL(path.resolve(process.env.UM88_STARTUP_IMAGE_ROOT)+path.sep):new URL('songs-micronucleus/',base);
const image=(name,file)=>new URL(name+'/'+file,images);
const definitions=readFileSync(new URL('vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h',base),'utf8');
const registers=Object.fromEntries([...definitions.matchAll(/^#define (\w+) _SFR_(IO|MEM)8\((0x[\da-f]+)\)/gmi)]
 .map(([,name,space,value])=>[name,Number(value)+(space==='IO'?32:0)]));
const addr=name=>{assert.ok(Object.hasOwn(registers,name),name+' exists in official DFP');return registers[name];};
const bit=name=>{
 const match=definitions.match(new RegExp('^#define\\s+'+name+'\\s+(\\d+)\\s*$','m'));
 assert.ok(match,name+' exists in official DFP');return 1<<Number(match[1]);
};
const leftCompare=new Set([addr('OCR1AL'),addr('OCR1AH')]);
const comLeft=bit('COM1A0')|bit('COM1A1'),ddrLeft=bit('DDB1');

// Decode the executed instruction independently of the interpreter's write
// callbacks. Capture attempted writes even if the stored value is unchanged.
function decodedWrite(cpu){
 const pc=cpu.pc*2,rom=cpu.rom;
 const instruction=decodeAVR(rom[pc]|rom[pc+1]<<8,rom[pc+2]|rom[pc+3]<<8);
 let address,value=cpu.r[instruction.d];
 if(instruction.name==='STS')address=instruction.k;
 else if(instruction.name==='OUT')address=32+instruction.k;
 else if(instruction.name==='ST'){
  const pointer=cpu.r[instruction.s]|cpu.r[instruction.s+1]<<8;
  const displacement=instruction.k<0?-1:instruction.k>=2?instruction.k-2:0;
  address=(pointer+displacement)&cpu.pointerMask;
 }else if(instruction.name==='SBI'||instruction.name==='CBI'){
  address=32+instruction.d;
  value=instruction.name==='SBI'?cpu.data[address]|1<<instruction.k:cpu.data[address]&~(1<<instruction.k);
 }else return null;
 return {pc,address,value:value&255,instruction:instruction.name,inIRQ:cpu.inIRQ};
}
const forbidLeftCompare=write=>{
 if(write)assert.ok(!leftCompare.has(write.address),
  `Mono must never write OCR1A: ${write.instruction} at byte PC 0x${write.pc.toString(16)}`);
};

test('write tracing rejects same-value OCR1A stores through absolute and indirect addressing',()=>{
 const cases=[['STS low',0x9300,addr('OCR1AL')],['STS high',0x9300,addr('OCR1AH')],
  ['ST X',0x930c,null,26,0],['ST X+',0x930d,null,26,0],['ST -X',0x930e,null,26,1],
  ['ST Y+',0x9309,null,28,0],['ST -Y',0x930a,null,28,1],
  ['ST Z+',0x9301,null,30,0],['ST -Z',0x9302,null,30,1],
  ['STD Y+7',0x830f,null,28,-7],['STD Z+7',0x8307,null,30,-7]];
 for(const [label,opcode,absolute,pointer,offset]of cases){
  const target=absolute??addr('OCR1AH'),binary=Uint8Array.of(opcode&255,opcode>>8,target&255,target>>8);
  const cpu=new AVRCore(binary,null,{target:'attiny88',fastIdle:false,fastBlocks:false});
  cpu.data[addr('OCR1AL')]=0x5b;cpu.data[addr('OCR1AH')]=0x5a;cpu.timerTemp=0x5a;
  cpu.r[16]=cpu.data[target];
  if(pointer!==undefined){const at=target+offset;cpu.r[pointer]=at&255;cpu.r[pointer+1]=at>>8;}
  const write=decodedWrite(cpu);
  assert.equal(write.address,target,label);assert.equal(write.value,cpu.data[target],label+' stores the same value');
  assert.throws(()=>forbidLeftCompare(write),/must never write OCR1A/,label);
  cpu.step();assert.equal(cpu.data[addr('OCR1AL')],0x5b,label);assert.equal(cpu.data[addr('OCR1AH')],0x5a,label);
 }
});

test('write tracing recognizes OUT and permits shared Timer1 control cleanup',()=>{
 const io=addr('DDRB')-32,out=0xb900|((io&48)<<5)|(io&15);
 for(const [opcode,address]of [[out,addr('DDRB')],[0x9300,addr('TCCR1A')]]){
  const cpu=new AVRCore(Uint8Array.of(opcode&255,opcode>>8,address&255,address>>8),null,
   {target:'attiny88',fastIdle:false,fastBlocks:false});
  if(address===addr('TCCR1A'))cpu.data[address]=comLeft;
  cpu.r[16]=0;const write=decodedWrite(cpu);
  assert.equal(write.address,address);assert.doesNotThrow(()=>forbidLeftCompare(write));
  cpu.step();assert.equal(cpu.data[address],0);
 }
});

test('Micronucleus .init3 restores PRR before gated-register writes, with valid CRT stack and zero register',()=>{
 const meta=JSON.parse(readFileSync(image('lumiere-stereo','build-report.json')));
 const cpu=new AVRCore(readFileSync(image('lumiere-stereo','synth.bin')),null,
  {target:'attiny88',cpuHz:16000000,fastIdle:false,fastBlocks:false});
 cpu.sp=0x17f;cpu.r[1]=0x83;
 cpu.data[addr('MCUSR')]=8;cpu.data[addr('WDTCSR')]=0x2b;cpu.data[addr('PRR')]=255;
 cpu.data[addr('TCCR1A')]=0x21;cpu.data[addr('TCCR1B')]=9;
 for(const name of ['EIMSK','PCICR','TIMSK0','TIMSK1'])cpu.data[addr(name)]=255;
 const writes=[],original=cpu.writeIO.bind(cpu);
 cpu.writeIO=(io,value)=>{writes.push({address:io+32,value});return original(io,value);};
 let entered=false;
 while(cpu.pc!==meta.labels.main/2){
  if(cpu.pc===meta.labels.um_board_reset/2){
   entered=true;assert.equal(cpu.sp,767,'CRT initializes SP before naked .init3');
   assert.equal(cpu.r[1],0,'CRT initializes GCC zero register before .init3');
  }
  assert.ok(cpu.cyc<20000,'Startup reaches main');cpu.step();
 }
 assert.ok(entered);
 const restore=writes.findIndex(w=>w.address===addr('PRR')&&w.value===0);
 assert.ok(restore>=0,'Power reduction restored');
 for(const name of ['TIMSK0','TIMSK1','TCCR0A','TCCR1A','TCCR1B','ADCSRA','SPCR','TWCR']){
  const cleanup=writes.findIndex(w=>w.address===addr(name));
  assert.ok(cleanup>restore,name+' cleanup follows PRR restoration');
  assert.equal(cpu.data[addr(name)],0,name+' disabled before BSS/main');
 }
 for(const name of ['EIMSK','PCICR','MCUSR','WDTCSR','CLKPR','GTCCR'])assert.equal(cpu.data[addr(name)],0,name);
 assert.ok(cpu.watchdogResets>0);assert.equal(cpu.irqCount,0);
 assert.ok(cpu.eeprom.every(value=>value===255));
});

for(const [name,channels]of [['greensleeves',1],['lumiere-stereo',2]]){
 test(`fixed ${channels}-channel startup connects only selected PWM outputs`,()=>{
  const meta=JSON.parse(readFileSync(image(name,'build-report.json')));
  assert.equal(meta.configuredChannels,channels);
  const cpu=new AVRCore(readFileSync(image(name,'synth.bin')),null,
   {target:'attiny88',cpuHz:meta.cpuHz,fastIdle:false,fastBlocks:false});
  cpu.data[addr('OCR1AL')]=0x5b;cpu.data[addr('OCR1AH')]=0x5a;
  cpu.data[addr('MCUSR')]=8;cpu.data[addr('WDTCSR')]=0x2b;cpu.data[addr('PRR')]=255;
  const writes=[];let enteredMain=false,controlCalls=0;
  while(cpu.irqCount<1024){
   assert.ok(cpu.cyc<2000000,'Fixed-channel startup and active control reach PWM');
   if(cpu.pc===meta.labels.main/2)enteredMain=true;
   if(!cpu.inIRQ&&cpu.pc===meta.labels.um_tick/2)controlCalls++;
   const write=decodedWrite(cpu);
   if(channels===1)forbidLeftCompare(write);
   if(write)writes.push({...write,inMain:enteredMain});
   cpu.step();
   if(channels===1){
    assert.equal(cpu.data[addr('TCCR1A')]&comLeft,0,'COM1A stays disconnected after every instruction');
    assert.equal(cpu.data[addr('DDRB')]&ddrLeft,0,'PB1 stays an input after every instruction');
   }
  }
  assert.ok(enteredMain);assert.ok(controlCalls>0,'Runtime tracing covers a musical control update');
  assert.equal(cpu.data[addr('TCCR1A')],channels===1?0x21:0xa1);
  assert.equal(cpu.data[addr('DDRB')]&6,channels===1?4:6);
  if(channels===1){
   assert.equal(cpu.data[addr('OCR1AL')],0x5b,'Inactive left compare low is untouched');
   assert.equal(cpu.data[addr('OCR1AH')],0x5a,'Inactive left compare high is untouched');
   assert.ok(!writes.some(w=>leftCompare.has(w.address)),'Mono startup/IRQ omit every left compare write');
   assert.ok(writes.some(w=>w.address===addr('TCCR1A')),'Shared Timer1 cleanup is observed and allowed');
  }else assert.ok(writes.some(w=>w.address===addr('OCR1AL')),'Stereo enables left compare updates');
  assert.ok(writes.some(w=>w.address===addr('OCR1BL')&&w.inMain&&!w.inIRQ),'Main initializes selected mono/right compare');
  assert.ok(writes.some(w=>w.address===addr('OCR1BL')&&w.inIRQ),'Active IRQs update selected mono/right compare');
  assert.equal(cpu.lost,0);assert.equal(cpu.data[addr('WDTCSR')],0);
 });
}
