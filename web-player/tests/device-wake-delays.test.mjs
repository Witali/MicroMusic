import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,relative,isAbsolute,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_VECTOR as VECTOR} from '../lib/attiny13a-registers.js';
const root=fileURLToPath(new URL('../../',import.meta.url));
const override=process.env.MICROMUSIC_WAKE_SOURCE;
const sourcePath=override?resolve(root,override):resolve(root,'web-player/native/peripherals/device.c');
if(override){const local=relative(resolve(root,'build'),sourcePath);
  assert.ok(local&&!isAbsolute(local)&&local!=='..'&&!local.startsWith('..'+sep),'Wake test override must stay in build/');}
const source=readFileSync(sourcePath,'utf8');
// Isolate the existing internal-clock wake policy after peripheral service.
// This is a digital fixture, not an oracle for unmeasured silicon phases.
const create=compileAnalog('wake-delays',[
  ...['timer0','system_gpio','system_watchdog','system_sleep','nvm','analog_adc','analog_comparator','analog','power_reset']
    .map(n=>`web-player/native/peripherals/${n}.c`),
  'web-player/native/devices/attiny13a/reset_input.c',
],source+`
static uint8_t wake_data[160];
void initialize(unsigned physical,unsigned configured_hz,unsigned source_hz,unsigned divisor,
 unsigned mode,uint64_t now,unsigned startup) {
 board=(device_t){0};board.data=wake_data;board.physical=physical;
 board.config[DEVICE_CFG_OSCILLATOR_HZ]=configured_hz;board.oscillator_hz=source_hz;
 board.config[DEVICE_CFG_WAKE_STARTUP_BASE_HALF]=startup;board.divisor=divisor;
 board.config[DEVICE_CFG_BOD_RECOVERY_NS]=60000;board.base=now;board.half=19;board.phase=1;
 board.deadline.valid=1;board.deadline.base=now;board.deadline.at=now;
 system_sleep_reset(&board.sleep,0);system_sleep_enter(&board.sleep,AT13_MASK_SE|(mode<<AT13_BIT_SM0),0);
}
void request(int kind) {
 if(kind==1)board.watchdog.control=SYSTEM_WDTIE|SYSTEM_WDTIF;
 if(kind==2){board.timer.timsk=AT13_MASK_TOIE0;board.timer.tifr=TIMER0_TOV0;}
}
void change_clock(unsigned source_hz,unsigned divisor) { board.oscillator_hz=source_hz;board.divisor=divisor; }
void bod(unsigned ns) { board.bod_disabled=1;board.config[DEVICE_CFG_BOD_RECOVERY_NS]=ns; }
void fuse_startup(void) { board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE]=1; }
void time_at(uint64_t at) { board.base=at; }
void poll(void) { wake(); }
unsigned pending(void) { return device_pending_irqs(); }
uint64_t observe(unsigned field) {
 switch(field) {
 case 0:return board.sleep.now;case 1:return board.sleep.startup_until;
 case 2:return board.sleep.ready_at;case 3:return board.sleep.wake_at;
 case 4:return board.sleep.wake_sources;case 5:return board.sleep.phase;
 case 6:return board.fault;case 7:return board.detail;case 8:return board.bod_disabled;
 case 9:return board.bod_recovery_until;case 10:return board.deadline.valid;
 case 11:return board.base;case 12:return board.half;case 13:return board.phase;
 default:return 0;
 }
}
`,{fixedMemoryPages:2});
const U64=0xffffffffffffffffn,u=n=>BigInt.asUintN(64,n),ceil=(a,b)=>(a+b-1n)/b;
const WDT=BigInt(1<<VECTOR.WDT),OVF=1<<VECTOR.TIM0_OVF;
const at=(c,n)=>u(c.observe(n)),healthy=c=>assert.equal(at(c,6),0n);

test('empty sleep polls retain the sleep cursor, phase, deadline certificate and absent wake',()=>{
  const c=create();let cases=0;
  for(const physical of [0,1])for(const hz of [1,9000001,9600000,1000000000])for(const div of [1,256])
    for(const mode of [0,1,2])for(const now of [1n,222223n,U64-1n]){
      c.initialize(physical,hz,hz,div,mode,now,0);assert.equal(c.pending(),0);c.poll();healthy(c);
      assert.deepEqual([at(c,0),at(c,1),at(c,2),at(c,3),at(c,4),at(c,5)], [now,U64,U64,0n,0n,1n]);
      assert.deepEqual([at(c,10),at(c,11),at(c,12),at(c,13)],[1n,now,19n,1n]);cases++;
    }
  assert.equal(cases,144);
});

test('the first actual wake after empty polls uses current source rate and divider with exact rounding',()=>{
  const c=create();let cases=0;
  for(const physical of [0,1])for(const hz of [1,9000001,9600000,1000000000])for(const div of [1,256])
    for(const mode of [0,1,2])for(const configuredStartup of [0,17]){
      const now=555557n,rate=2n*BigInt(hz),base=physical?1000000000000n:19200000n,
        startup=ceil(BigInt(configuredStartup)*base,19200000n),fuse=ceil(12n*base,rate),
        expectedStartup=mode===2&&fuse>startup?fuse:startup,extra=ceil(8n*BigInt(div)*base,rate);
      c.initialize(physical,9600000,9600000,1,mode,1n,configuredStartup);c.fuse_startup();
      for(const t of [2n,31n,333333n]){c.time_at(t);c.poll();healthy(c);assert.equal(at(c,5),1n);}
      c.change_clock(hz,div);c.time_at(now);c.request(1);assert.equal(c.pending(),Number(WDT));c.poll();healthy(c);
      assert.deepEqual([at(c,0),at(c,1),at(c,2),at(c,3),at(c,4),at(c,5)],
        [now,now+expectedStartup,now+expectedStartup+extra,now,WDT,expectedStartup?2n:3n]);
      assert.deepEqual([at(c,12),at(c,13)],[19n,1n]);cases++;
    }
  assert.equal(cases,96);
});

test('configured startup overflow remains observable even with no pending wake source',()=>{
  const c=create();c.initialize(1,1,1,256,2,999n,0xffffffff);assert.equal(c.pending(),0);c.poll();
  assert.deepEqual([at(c,6),at(c,7),at(c,5),at(c,0),at(c,10)],[2n,12n,1n,999n,0n]);
});

test('BOD recovery stays dormant during empty polls and joins the first real wake',()=>{
  const c=create();const mode=2; // BOD sleep-disable applies to Power-down.
    c.initialize(1,9000001,9000001,256,mode,123n,0);c.bod(60000);c.poll();healthy(c);
    assert.deepEqual([at(c,8),at(c,9),at(c,5)],[1n,0n,1n]);
    c.time_at(999n);c.request(1);c.poll();healthy(c);
    assert.deepEqual([at(c,8),at(c,9),at(c,1),at(c,2)],[0n,60000999n,60000999n,
      60000999n+ceil(2048n*1000000000000n,18000002n)]);
});

test('non-waking pending sources and reversed cursors retain the original sleep policy',()=>{
  const c=create();for(const mode of [1,2]){
    c.initialize(1,9000001,9000001,1,mode,123n,0);c.request(2);assert.equal(c.pending(),OVF);c.poll();healthy(c);
    assert.deepEqual([at(c,0),at(c,4),at(c,5)],[123n,0n,1n]);
  }
  c.initialize(1,9000001,9000001,1,0,123n,0);c.poll();c.time_at(122n);c.poll();
  assert.deepEqual([at(c,6),at(c,7),at(c,0),at(c,5)],[7n,32n,123n,1n]);
});

test('actual wake deadline overflow fails before changing sleeping state',()=>{
  const c=create();for(const withBod of [0,1]){
    c.initialize(1,9600000,9600000,256,2,U64-1n,0);if(withBod)c.bod(60000);
    c.poll();healthy(c);c.request(1);c.poll();
    assert.deepEqual([at(c,6),at(c,7),at(c,0),at(c,5),at(c,8)],[7n,32n,U64-1n,1n,BigInt(withBod)]);
  }
});
