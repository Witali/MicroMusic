import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, existsSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root=fileURLToPath(new URL('../../',import.meta.url));
const repository=spawnSync('git',['rev-parse','--git-common-dir'],{cwd:root,encoding:'utf8'});
assert.equal(repository.status,0,repository.stderr);
const common=resolve(root,repository.stdout.trim());
const mainRoot=dirname(common);
const sdk=process.env.EMSDK || join(mainRoot,'build','toolchains','emscripten-6.0.12');
const compiler=process.env.CLANG || join(sdk,'upstream','bin',process.platform==='win32'?'clang.exe':'clang');
assert.ok(existsSync(compiler),'NVM tests require clang: set EMSDK or CLANG, or install repository toolchains');
const sysroot=join(sdk,'upstream','emscripten','cache','sysroot');
const output=join(root,'build','nvm-tests');mkdirSync(output,{recursive:true});
const binary=join(output,'nvm-tests.wasm');
const cases=[
 'eeprom_windows','eeprom_atomic','eeprom_modes_irq_reset','bit_strobes',
 'flash_command_windows','flash_erase_write','flash_fuses_lpm',
 'eeprom_flash_interlock','flash_reset_faults','clock_domains_timing'
];
const args=['--target=wasm32-unknown-unknown','-O2','-std=c11','-Wall','-Wextra','-Werror',
 '-ffreestanding','-nostdlib','--sysroot='+sysroot,'-isystem',join(sysroot,'include'),
 '-L'+join(sysroot,'lib','wasm32-emscripten'),'-Wl,--no-entry',
 ...cases.map(name=>'-Wl,--export=nvm_test_'+name),
 'web-player/native/peripherals/nvm.c','web-player/native/peripherals/nvm.test.c',
 '-lc','-lclang_rt.builtins','-o',binary];
const result=spawnSync(compiler,args,{cwd:root,encoding:'utf8'});
assert.equal(result.status,0,result.stderr||result.stdout);
const module=await WebAssembly.compile(readFileSync(binary));
test('NVM executes without JavaScript imports',()=>assert.deepEqual(WebAssembly.Module.imports(module),[]));
const instance=await WebAssembly.instantiate(module,{});
for (const name of cases) test('ATtiny13A NVM '+name.replaceAll('_',' '),()=>{
 const line=instance.exports['nvm_test_'+name]();
 assert.equal(line,0,'nvm.test.c assertion failed at line '+line);
});
