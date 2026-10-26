import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync,spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

const before=execFileSync('git',['show','f0627629:web-player/native/peripherals/device.c'],{encoding:'utf8'});
const oldMirror=before.match(/static void mirror\(void\) \{[\s\S]*?\n\}/)[0].replace('mirror(void)','reference_mirror(void)');
const create=compileAnalog('io-owners',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm','analog_adc','analog_comparator','analog','power_reset',
].map(n=>'web-player/native/peripherals/'+n+'.c'),`
#include "device.c"
${oldMirror}
static uint8_t actual[160],expected[160];
const char *owner(unsigned io){
 switch(io){
#define AT13_IO_PUBLISH(owner,name,value) case AT13_IO_##name: return #owner;
#define AT13_IO_LOCAL(owner,name) AT13_IO_PUBLISH(owner,name,0)
#include "../devices/attiny13a/io_registers.inc"
#undef AT13_IO_LOCAL
#undef AT13_IO_PUBLISH
 default:return "RESERVED";
 }
}
uint64_t published(void){
 return UINT64_C(0)
#define AT13_IO_PUBLISH(owner,name,value) | (UINT64_C(1)<<AT13_IO_##name)
#define AT13_IO_LOCAL(owner,name)
#include "../devices/attiny13a/io_registers.inc"
#undef AT13_IO_LOCAL
#undef AT13_IO_PUBLISH
 ;
}
int timer_route(unsigned io){return timer_register((uint8_t)io);}
int same_publication(uint32_t seed){
 /* Publication alone must work for arbitrary controller byte values. Do not
  * clock this synthetic state: its other pointers/timestamps are not a device
  * configuration. Both publishers receive the same controlled data pointer. */
 uint8_t *state=(uint8_t *)&board;
 for(unsigned i=0;i<sizeof(board);i++){seed=seed*1664525u+1013904223u;state[i]=(uint8_t)(seed>>24);}
 for(unsigned i=0;i<sizeof(actual);i++)actual[i]=expected[i]=(uint8_t)(seed+i*73u);
 board.data=actual;mirror();board.data=expected;reference_mirror();
 board.data=actual;
 for(unsigned i=0;i<sizeof(actual);i++)if(actual[i]!=expected[i])return (int)i+1;
 return 0;
}
`);
const expected={
  ADC:['ADCSRB','ADCL','ADCH','ADCSRA','ADMUX'],COMPARATOR:['ACSR'],
  GPIO:['DIDR0','PCMSK','PINB','DDRB','PORTB','MCUCR','GIFR','GIMSK'],WATCHDOG:['WDTCR','MCUSR'],
  NVM:['EECR','EEDR','EEARL','SPMCSR'],BOARD:['PRR','CLKPR','BODCR'],
  TIMER0:['GTCCR','TCCR0A','TCCR0B','TCNT0','OCR0A','OCR0B','TIFR0','TIMSK0'],
  CLOCK:['OSCCAL'],CPU:['SPL','SREG'],DEBUG:['DWDR'],
};
const ownerByAddress=new Map(Object.entries(expected).flatMap(([owner,names])=>names.map(name=>[IO[name],owner])));
test('device I/O bindings are reproducible against the generated manufacturer register map',()=>{
  const result=spawnSync(process.execPath,[fileURLToPath(new URL('../scripts/generate-attiny13a-io-bindings.mjs',import.meta.url)),'--check'],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
});
test('all 64 I/O addresses have the intended single owner, including vendor aliases and reserved bytes',()=>{
  const c=create(),memory=new Uint8Array(c.memory.buffer),string=p=>{let end=p;while(memory[end])end++;return new TextDecoder().decode(memory.subarray(p,end));};
  assert.equal(ownerByAddress.size,35);assert.deepEqual([...ownerByAddress.keys()].sort((a,b)=>a-b),[...new Set(Object.values(IO))].sort((a,b)=>a-b));
  for(let io=0;io<64;io++)assert.equal(string(c.owner(io)),ownerByAddress.get(io)??'RESERVED','I/O '+io);
  assert.equal(string(c.owner(IO.ADC)),string(c.owner(IO.ADCL)));assert.equal(IO.ADCW,IO.ADCL);assert.equal(IO.EEAR,IO.EEARL);
  const local=new Set(['OSCCAL','SPL','SREG','DWDR'].map(name=>IO[name]));
  const mask=[...ownerByAddress.keys()].filter(io=>!local.has(io)).reduce((n,io)=>n|(1n<<BigInt(io)),0n);
  assert.equal(BigInt.asUintN(64,c.published()),mask);
});
test('generated Timer0 routing selects exactly its eight controller registers and excludes board-owned PRR',()=>{
  const c=create(),timer=new Set(expected.TIMER0.map(name=>IO[name]));
  for(let io=0;io<64;io++)assert.equal(!!c.timer_route(io),timer.has(io),'I/O '+io);
  assert.equal(c.timer_route(IO.PRR),0);
});
test('catalog publication matches the original board publisher for arbitrary fields and every data-space byte',()=>{
  const c=create();for(let seed=0;seed<256;seed++)assert.equal(c.same_publication(seed),0,'seed '+seed);
});
