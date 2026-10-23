import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../',import.meta.url));
const sdk=[process.env.EMSDK,join(root,'build/toolchains/emscripten-6.0.12'),resolve(root,'../../build/toolchains/emscripten-6.0.12')].find(p=>p&&existsSync(join(p,'upstream/bin/clang.exe')));
if(!sdk)throw Error('Set EMSDK to the read-only Emscripten SDK');
const out=join(root,'build/nvm-voltage-test/nvm.wasm');mkdirSync(dirname(out),{recursive:true});
const fixture=join(dirname(out),'fixture.c');
writeFileSync(fixture,`#include "nvm.h"
static attiny13a_nvm_t n;static uint8_t flash[1024],ee_data[64];
void init(void){for(int i=0;i<1024;i++)flash[i]=255;for(int i=0;i<64;i++)ee_data[i]=255;
 nvm_timing_t t={10,10,10,10,10};nvm_init(&n,flash,ee_data,&t,0x7a,0xef,0xff);}
void start_ee(void){nvm_write_io(&n,NVM_EEARL,4,255,0,0);nvm_write_io(&n,NVM_EEDR,42,255,0,0);
 nvm_write_io(&n,NVM_EECR,4,4,0,0);nvm_write_io(&n,NVM_EECR,2,2,1,0);}
void start_flash(void){nvm_write_io(&n,NVM_SPMCSR,1,255,0,0);nvm_spm(&n,0,0x1234,0,0);
 nvm_write_io(&n,NVM_SPMCSR,5,255,1,0);nvm_spm(&n,0,0,1,0);}
void uncertain(int mask){nvm_voltage_uncertain(&n,(uint32_t)mask);}
void advance(void){nvm_advance(&n,100,100);}
void reset(void){nvm_reset(&n,101,101);}
int read(void){return nvm_read_io(&n,NVM_EECR,102,102);}
void write(void){nvm_write_io(&n,NVM_EECR,0,255,103,103);}
int spm(void){return nvm_spm(&n,0,0,104,104);}
int ee(void){return ee_data[4];}int rom(void){return flash[0];}
int busy(void){return n.eeprom_busy|(n.flash_busy<<1);}int faults(void){return n.faults;}
int generation(void){return (int)n.flash_generation;}int dirty(void){return n.flash_dirty_pages;}
uint64_t next(void){return nvm_next_event_ns(&n);}
`);
const exports=['init','start_ee','start_flash','uncertain','advance','reset','read','write','spm','ee','rom','busy','faults','generation','dirty','next'];
const sysroot=join(sdk,'upstream/emscripten/cache/sysroot');
const built=spawnSync(join(sdk,'upstream/bin/clang.exe'),['--target=wasm32-unknown-unknown','-O3','-std=c11','-ffreestanding','-nostdlib',
 '-Wall','-Wextra','-Werror','--sysroot='+sysroot,'-isystem',join(sysroot,'include'),'-L',join(sysroot,'lib/wasm32-emscripten'),
 '-I',join(root,'web-player/native/peripherals'),'-Wl,--no-entry',...exports.map(n=>'-Wl,--export='+n),
 join(root,'web-player/native/peripherals/nvm.c'),fixture,'-lc','-o',out],{encoding:'utf8'});
if(built.error||built.status!==0)throw built.error||Error(built.stderr);
const mod=await WebAssembly.compile(readFileSync(out)),n=(await WebAssembly.instantiate(mod)).exports;
test('uncertain EEPROM never commits through advance, read, write or reset',()=>{
 n.init();n.start_ee();n.uncertain(128);n.advance();n.reset();n.read();n.write();
 assert.equal(n.ee(),255);assert.equal(n.busy(),1);assert.equal(n.faults(),128);assert.equal(n.next(),-1n);
});
test('uncertain Flash preserves bytes, pending state, generation and dirty pages',()=>{
 n.init();n.start_flash();n.uncertain(256);n.advance();n.reset();n.read();n.write();assert.equal(n.spm(),-1);
 assert.equal(n.rom(),255);assert.ok(n.busy());assert.equal(n.faults(),256);assert.equal(n.generation(),0);assert.equal(n.dirty(),0);
});
test('normal reset preserves and completes adequate-voltage programming',()=>{
 n.init();n.start_ee();n.reset();assert.equal(n.ee(),42);assert.equal(n.busy(),0);
 n.init();n.start_flash();n.reset();assert.equal(n.rom(),0x34);assert.equal(n.generation(),1);
});
test('inactive memories do not acquire uncertainty; init clears a previous guard',()=>{
 n.init();n.uncertain(384);assert.equal(n.faults(),0);n.start_ee();n.uncertain(128);n.init();assert.equal(n.faults(),0);
 assert.deepEqual(WebAssembly.Module.imports(mod),[]);
});
