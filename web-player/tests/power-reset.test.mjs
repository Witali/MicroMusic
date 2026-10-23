import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../../',import.meta.url));
const sdk=[process.env.EMSDK,join(root,'build/toolchains/emscripten-6.0.12'),
  resolve(root,'../../build/toolchains/emscripten-6.0.12')].find(p=>p&&existsSync(join(p,'upstream/bin/clang.exe')));
if(!sdk)throw Error('Set EMSDK to the read-only Emscripten SDK for power reset tests');
const output=join(root,'build/power-reset-test/power.wasm');mkdirSync(dirname(output),{recursive:true});
const wrapper=join(dirname(output),'fixture.c');
writeFileSync(wrapper,`#include "power_reset.h"
static power_reset_t p;
static power_reset_profile_t profile;
static power_reset_event_t last;
int init(int code,int uv,uint64_t at,uint64_t filter,uint64_t timeout,uint64_t recovery) {
 power_reset_typical_profile(&profile,filter,timeout,recovery);
 return power_reset_init(&p,&profile,(uint8_t)((0xff&~6)|(code<<1)),at,uv);
}
int custom(int activate,int release,int center,int hysteresis) {
 profile.por_assert_uv=activate;profile.por_release_uv=release;
 profile.bod_center_uv[1]=center;profile.bod_hysteresis_uv=hysteresis;
 return power_reset_init(&p,&profile,0xfb,0,5000000);
}
int vcc(uint64_t at,int uv){return power_reset_set_vcc(&p,at,uv);}
int inputs(uint64_t at,int uv,int mask){return power_reset_set_inputs(&p,at,uv,(uint8_t)mask);}
int advance(uint64_t at){return power_reset_advance(&p,at);}
int sources(uint64_t at,int mask){return power_reset_set_other_sources(&p,at,mask);}
int sleep(uint64_t at,int mode,int bods){return power_reset_sleep(&p,at,mode,bods);}
int wake(uint64_t at){return power_reset_wake(&p,at);}
int blocked(void){return power_reset_execution_blocked(&p);}
int held(void){return p.held;}
int enabled(void){return power_reset_bod_enabled(&p);}
int fault(void){return p.fault;}
int uncertain(void){return power_reset_eeprom_voltage_uncertain(&p);}
int voltage(void){return p.vcc_uv;}
int other(void){return p.other_sources;}
uint64_t next(void){return power_reset_next_deadline(&p);}
uint64_t now(void){return p.now;}
int pop(void){return power_reset_pop_event(&p,&last);}
uint64_t event_at(void){return last.at;}
uint64_t event_deadline(void){return last.deadline;}
int kind(void){return last.kind;}
int active(void){return last.sources;}
int cause(void){return last.causes;}
int flag_set(void){return last.flags_set;}
int flag_clear(void){return last.flags_clear;}
`);
const names=['init','custom','vcc','inputs','advance','sources','sleep','wake','blocked','held','enabled','fault',
  'uncertain','voltage','other','next','now','pop','event_at','event_deadline','kind','active','cause','flag_set','flag_clear'];
const sysroot=join(sdk,'upstream/emscripten/cache/sysroot');
const compiled=spawnSync(join(sdk,'upstream/bin/clang.exe'),['--target=wasm32-unknown-unknown','-O3','-std=c11',
  '-ffreestanding','-nostdlib','-Wall','-Wextra','-Werror','--sysroot='+sysroot,'-isystem',join(sysroot,'include'),
  '-I',join(root,'web-player/native/peripherals'),'-Wl,--no-entry',...names.map(n=>'-Wl,--export='+n),
  join(root,'web-player/native/peripherals/power_reset.c'),wrapper,'-o',output],{encoding:'utf8'});
if(compiled.error||compiled.status!==0)throw compiled.error||Error(compiled.stderr);
const module=await WebAssembly.compile(readFileSync(output)),p=(await WebAssembly.instantiate(module)).exports;
const NEVER=(1n<<64n)-1n,ASSERT=1,HOLD=2,RELEASE=3,OFF=4,RECOVER=5,READY=6;
const next=()=>BigInt.asUintN(64,p.next()); // JS exposes raw WASM i64 as signed.
const init=(code=3,uv=5000000,{at=0,filter=2000,timeout=10000,recovery=60000}={})=>assert.equal(p.init(code,uv,BigInt(at),BigInt(filter),BigInt(timeout),BigInt(recovery)),1);
const vcc=(at,uv)=>assert.equal(p.vcc(BigInt(at),uv),1);
const advance=at=>assert.equal(p.advance(BigInt(at)),1);
const sources=(at,mask)=>assert.equal(p.sources(BigInt(at),mask),1);
const inputs=(at,uv,mask)=>assert.equal(p.inputs(BigInt(at),uv,mask),1);
function drain(){const events=[];while(p.pop())events.push({at:p.event_at(),deadline:p.event_deadline(),kind:p.kind(),sources:p.active(),causes:p.cause(),set:p.flag_set(),clear:p.flag_clear()});return events;}
const kinds=()=>drain().map(e=>[e.kind,e.at,e.sources,e.set,e.clear]);

test('power reset module compiles with warnings as errors and has no WASM imports',()=>{
  assert.deepEqual(WebAssembly.Module.imports(module),[]);
});

test('cold POR holds asynchronously until its release threshold plus explicit tTOUT',()=>{
  init(3,0);assert.equal(p.held(),1);assert.equal(p.blocked(),1);assert.equal(next(),NEVER);
  assert.deepEqual(kinds(),[[ASSERT,0n,1,1,14]]);
  vcc(50,1350000);assert.equal(next(),NEVER);assert.deepEqual(drain(),[]);
  vcc(100,1400000);assert.equal(p.held(),1);assert.equal(next(),10100n);
  assert.deepEqual(kinds(),[[HOLD,100n,0,0,0]]);
  advance(10099);assert.equal(p.held(),1);advance(10100);assert.equal(p.blocked(),0);
  assert.deepEqual(kinds(),[[RELEASE,10100n,0,0,0]]);
});

test('initial high VCC does not invent a POR without an earlier VPOA crossing',()=>{
  init();assert.equal(p.held(),0);assert.deepEqual(drain(),[]);
  vcc(10,1300000);assert.equal(p.held(),0); // Equality is an explicit digital convention.
  vcc(11,1299999);assert.equal(p.held(),1);
  assert.deepEqual(kinds(),[[ASSERT,11n,1,1,14]]);
});

test('a new supply failure cancels and restarts the full reset release delay',()=>{
  init(3,0);drain();vcc(10,5000000);drain();advance(10000);assert.equal(p.held(),1);
  vcc(10001,0);assert.equal(next(),NEVER);
  vcc(10002,5000000);assert.equal(next(),20002n);advance(20001);assert.equal(p.held(),1);
  advance(20002);assert.equal(p.held(),0);
});

test('all BODLEVEL fuse codes select their own threshold and 11 disables BOD',()=>{
  for(const [code,fall] of [[0,4275000],[1,2675000],[2,1775000]]){
    init(code);vcc(10,fall);assert.equal(next(),NEVER);
    vcc(11,fall-1);assert.equal(next(),2011n);advance(2010);assert.equal(p.held(),0);
    advance(2011);assert.equal(p.held(),1);assert.deepEqual(kinds(),[[ASSERT,2011n,4,4,0]]);
  }
  init(3);vcc(10,1500000);advance(100000);assert.equal(p.held(),0);assert.equal(p.enabled(),0);
  vcc(100001,0);assert.equal(p.held(),1);assert.equal(drain()[0].set,1);
});

test('unqualified short dips and hysteresis-band returns cancel continuous-low filtering',()=>{
  init(1);vcc(100,2600000);advance(2099);vcc(2099,2700000);
  assert.equal(next(),NEVER);advance(1000000);assert.equal(p.held(),0);assert.deepEqual(drain(),[]);
  vcc(1000010,2600000);advance(1002010);assert.equal(p.held(),1);
});

test('qualified BOD persists through the hysteresis band and releases only above VBOT+',()=>{
  init(1);vcc(10,2600000);advance(2010);drain();
  vcc(2020,2700000);assert.equal(p.held(),1);assert.equal(next(),NEVER);
  vcc(2030,2725000);assert.equal(next(),NEVER);
  vcc(2040,2725001);assert.equal(next(),12040n);assert.equal(p.held(),1);
  advance(12040);assert.equal(p.held(),0);assert.deepEqual(kinds(),[[HOLD,2040n,0,0,0],[RELEASE,12040n,0,0,0]]);
});

test('a dip ending exactly at the filter deadline is qualified before that timestamped input',()=>{
  init(1);vcc(0,2600000);vcc(2000,5000000);
  assert.deepEqual(kinds(),[[ASSERT,2000n,4,4,0],[HOLD,2000n,0,0,0]]);
  assert.equal(next(),12000n);advance(12000);assert.equal(p.held(),0);
});

test('BODS only disables an enabled BOD in Power-down after owner authorization',()=>{
  for(const [mode,authorized] of [[0,1],[1,1],[2,0]]){
    init(1);assert.equal(p.sleep(0n,mode,authorized),1);assert.equal(p.enabled(),1);
    vcc(10,2600000);advance(2010);assert.equal(p.held(),1);
  }
  init(1);assert.equal(p.sleep(0n,2,1),1);assert.equal(p.enabled(),0);
  vcc(10,2000000);advance(1000000);assert.equal(p.held(),0);assert.deepEqual(kinds(),[[OFF,0n,0,0,0]]);
  init(3);assert.equal(p.sleep(0n,2,1),1);assert.equal(p.wake(10n),1);
  assert.equal(p.blocked(),0);assert.deepEqual(drain(),[]);
});

test('safe wake restores BOD and gates execution for explicit recovery without generating reset flags',()=>{
  init(1);assert.equal(p.sleep(10n,2,1),1);drain();assert.equal(p.wake(100n),1);
  assert.equal(p.enabled(),1);assert.equal(p.held(),0);assert.equal(p.blocked(),1);assert.equal(next(),60100n);
  assert.deepEqual(kinds(),[[RECOVER,100n,0,0,0]]);
  advance(60099);assert.equal(p.blocked(),1);advance(60100);assert.equal(p.blocked(),0);
  assert.deepEqual(kinds(),[[READY,60100n,0,0,0]]);
});

test('low-VCC wake qualifies a BOD reset before CPU recovery completes',()=>{
  init(1);assert.equal(p.sleep(0n,2,1),1);vcc(1,2000000);drain();assert.equal(p.wake(100n),1);
  assert.equal(next(),2100n);advance(2100);assert.equal(p.held(),1);assert.equal(p.blocked(),1);
  assert.equal(next(),NEVER);assert.deepEqual(kinds(),[[RECOVER,100n,0,0,0],[ASSERT,2100n,4,4,0]]);
  vcc(5000,5000000);advance(15000);assert.equal(p.blocked(),0);
});

test('POR remains active in BOD-disabled sleep and cancels the sleep-only disable',()=>{
  init(1);assert.equal(p.sleep(0n,2,1),1);drain();vcc(10,0);
  assert.equal(p.enabled(),1);assert.equal(p.held(),1);assert.deepEqual(kinds(),[[ASSERT,10n,1,1,14]]);
  vcc(20,5000000);advance(10020);assert.equal(p.blocked(),0);
});

test('external/WDT aggregation starts tTOUT only after every source is inactive',()=>{
  init();sources(10,2);sources(20,10);sources(30,8);assert.equal(next(),NEVER);
  sources(40,0);assert.equal(next(),10040n);advance(10039);assert.equal(p.held(),1);
  advance(10040);assert.equal(p.held(),0);
  assert.deepEqual(kinds(),[[ASSERT,10n,2,2,0],[HOLD,20n,10,8,0],[HOLD,30n,8,0,0],
    [HOLD,40n,0,0,0],[RELEASE,10040n,0,0,0]]);
});

test('atomic POR to EXTRF handoff stays held with zero timeout and retains combined causes',()=>{
  init(3,0,{timeout:0});assert.deepEqual(kinds(),[[ASSERT,0n,1,1,14]]);
  inputs(10,5000000,2);
  assert.equal(p.held(),1);assert.equal(next(),NEVER);assert.equal(p.other(),2);
  const handoff=drain();
  assert.deepEqual(handoff.map(e=>[e.kind,e.at,e.sources,e.set,e.clear]),[[HOLD,10n,2,2,0]]);
  assert.equal(handoff[0].causes,3);
  inputs(20,5000000,0);assert.equal(p.held(),0);
  const released=drain();assert.deepEqual(released.map(e=>e.kind),[HOLD,RELEASE]);
  assert.equal(released[1].at,20n);assert.equal(released[1].causes,3);
});

test('atomic EXTRF to POR handoff stays held and POR flag clearing wins without another assertion',()=>{
  init(3,5000000,{timeout:0});sources(1,2);assert.deepEqual(kinds(),[[ASSERT,1n,2,2,0]]);
  inputs(10,0,0);
  assert.equal(p.held(),1);assert.equal(next(),NEVER);assert.equal(p.other(),0);
  assert.deepEqual(drain().map(e=>[e.kind,e.at,e.sources,e.causes,e.set,e.clear]),[[HOLD,10n,1,1,1,14]]);
  inputs(20,5000000,0);assert.equal(p.held(),0);
  const released=drain();assert.deepEqual(released.map(e=>e.kind),[HOLD,RELEASE]);
  assert.equal(released[1].causes,1);
});

test('atomic supply/source updates combine newly added causes in one aggregate event',()=>{
  init(3,5000000,{timeout:0});inputs(10,0,10);
  assert.equal(p.held(),1);assert.equal(p.voltage(),0);assert.equal(p.other(),10);
  assert.deepEqual(kinds(),[[ASSERT,10n,11,11,14]]);
  inputs(20,5000000,10);assert.equal(p.held(),1);
  assert.deepEqual(kinds(),[[HOLD,20n,10,0,0]]);
  inputs(30,5000000,0);const events=drain();
  assert.deepEqual(events.map(e=>e.kind),[HOLD,RELEASE]);assert.equal(events[1].causes,11);
});

test('atomic inputs process existing due deadlines before the same-time replacement',()=>{
  init(1,5000000,{filter:20,timeout:0});vcc(10,2600000);assert.equal(next(),30n);
  inputs(30,5000000,2);
  const events=drain();assert.deepEqual(events.map(e=>[e.kind,e.at,e.sources,e.set]),[
    [ASSERT,30n,4,4],[HOLD,30n,2,2],
  ]);
  assert.equal(events[1].causes,6);assert.equal(p.held(),1);assert.equal(next(),NEVER);
});

test('invalid atomic input pairs cannot advance time, replace either input or consume a pending event',()=>{
  for(const [uv,mask] of [[-1,2],[5000000,4],[-1,4]]){
    init(1,5000000,{filter:20,timeout:0});vcc(10,2600000);assert.equal(next(),30n);
    assert.equal(p.inputs(30n,uv,mask),0);assert.equal(p.fault(),3);
    assert.equal(p.now(),10n);assert.equal(p.voltage(),2600000);assert.equal(p.other(),0);
    assert.equal(next(),30n);assert.equal(p.held(),0);assert.deepEqual(drain(),[]);
  }
});

test('POR clears previous reset reasons through event metadata, while new reasons accumulate',()=>{
  init(1);sources(0,8);vcc(1,0);
  const events=drain();assert.equal(events[1].set,1);assert.equal(events[1].clear,14);
  assert.equal(events[1].causes,1);assert.equal(events[1].sources,9);
  sources(2,0);vcc(3,1500000);advance(2003);
  assert.equal(drain().at(-1).set,4);assert.equal(p.held(),1);
});

test('profiles support explicit thresholds and odd-microvolt hysteresis rounding',()=>{
  init(1);assert.equal(p.custom(1000000,1200000,3000000,50001),1);
  vcc(0,2975000);assert.equal(next(),NEVER);vcc(1,2974999);advance(2001);assert.equal(p.held(),1);
  vcc(2002,3025001);assert.equal(next(),NEVER);vcc(2003,3025002);assert.equal(next(),12003n);
  assert.equal(p.custom(1300000,1000000,3000000,50000),0);assert.equal(p.fault(),1);
});

test('zero-duration fixture parameters retain same-timestamp assertion and release events',()=>{
  init(1,5000000,{filter:0,timeout:0,recovery:0});vcc(10,2600000);assert.equal(p.held(),1);
  vcc(11,5000000);assert.equal(p.held(),0);
  assert.deepEqual(kinds(),[[ASSERT,10n,4,4,0],[HOLD,11n,0,0,0],[RELEASE,11n,0,0,0]]);
});

test('stable spans advance in bounded work and preserve events across arbitrary partitions',()=>{
  function scenario(partition){
    init(1);vcc(100,2600000);if(partition){advance(1000);advance(2099);}advance(2100);
    vcc(4000,5000000);if(partition){advance(5000);advance(13999);}advance(1000000000000000n);
    return drain();
  }
  assert.deepEqual(scenario(true),scenario(false));assert.equal(p.now(),1000000000000000n);
  assert.equal(next(),NEVER);assert.equal(p.blocked(),0);
});

test('EEPROM low-voltage erratum is exposed as uncertainty without inventing data corruption',()=>{
  init();assert.equal(p.uncertain(),0);vcc(1,1900000);assert.equal(p.uncertain(),0);
  vcc(2,1899999);assert.equal(p.uncertain(),1);assert.equal(p.held(),0);assert.deepEqual(drain(),[]);
});

test('the event ring wraps without reordering or losing already-drained source changes',()=>{
  init();
  for(let batch=0;batch<8;batch++){
    for(let n=0;n<16;n++)sources(batch*16+n,n%2?8:2);
    const events=drain();assert.equal(events.length,16);
    for(let n=0;n<16;n++){
      assert.equal(events[n].at,BigInt(batch*16+n));assert.equal(events[n].sources,n%2?8:2);
    }
  }
  assert.equal(p.fault(),0);assert.equal(p.held(),1);
});

test('bad input/time, deadline overflow and event-buffer overflow fail explicitly and block execution',()=>{
  init();advance(10);assert.equal(p.advance(9n),0);assert.equal(p.fault(),2);assert.equal(p.blocked(),1);
  init();assert.equal(p.vcc(0n,-1),0);assert.equal(p.fault(),3);
  init();assert.equal(p.sources(0n,4),0);assert.equal(p.fault(),3);
  init(3,0,{at:NEVER-5n,timeout:10});assert.equal(p.vcc(NEVER-4n,5000000),0);
  assert.equal(p.fault(),4);assert.equal(p.blocked(),1);
  init();for(let n=0;n<33&&!p.fault();n++)p.sources(BigInt(n),n%2?8:2);
  assert.equal(p.fault(),5);assert.equal(p.blocked(),1);assert.equal(drain().length,32);
});
