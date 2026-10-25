// Exercise the actual linked CRT/.init3 instructions after bootloader entry.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-reference.js';
const base=new URL('../../ATtiny88/Music/universal/',import.meta.url);
const definitions=readFileSync(new URL('vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h',base),'utf8');
const registers=Object.fromEntries([...definitions.matchAll(/^#define (\w+) _SFR_(IO|MEM)8\((0x[\da-f]+)\)/gmi)]
 .map(([,name,space,value])=>[name,Number(value)+(space==='IO'?32:0)]));
const addr=name=>{assert.ok(Object.hasOwn(registers,name),name+' exists in official DFP');return registers[name];};

test('Micronucleus .init3 restores PRR before gated-register writes, with valid CRT stack and zero register',()=>{
 const meta=JSON.parse(readFileSync(new URL('songs-micronucleus/lumiere-stereo/build-report.json',base)));
 const cpu=new AVRCore(readFileSync(new URL('songs-micronucleus/lumiere-stereo/synth.bin',base)),null,
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
