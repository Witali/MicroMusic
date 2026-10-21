import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve, join } from 'node:path';
import { parseArgs } from 'node:util';
import { createHash } from 'node:crypto';
const {values} = parseArgs({options:{emsdk:{type:'string'},clang:{type:'string'}}});
const root=fileURLToPath(new URL('../../',import.meta.url));
const sdk=values.emsdk || process.env.EMSDK;
if(!sdk)throw new Error('Pass --emsdk <directory> or set EMSDK. The SDK is read only.');
const compiler=values.clang || join(resolve(sdk),'upstream','bin',process.platform==='win32'?'clang.exe':'clang');
const sysroot=join(resolve(sdk),'upstream','emscripten','cache','sysroot');
const output=join(root,'web-player','wasm');mkdirSync(output,{recursive:true});
const exports=['layout','field_name','error_message','reset','decode','decode_idle','step','next','block','idle','clock',
 'interrupt','write_io','update_timer','timer_mode','push','pop','push_pc','pop_pc','nzvs','arithmetic',
 'audio_init','audio_controls','render','filter','average'].map(n=>'avr_'+n);
const flags=['--target=wasm32-unknown-unknown','-O3','-std=c11','-ffreestanding','-nostdlib',
 '--sysroot='+sysroot,'-isystem',join(sysroot,'include'),'-L'+join(sysroot,'lib','wasm32-emscripten'),
 '-Wl,--no-entry','-Wl,--export-memory','-Wl,--initial-memory=65536','-Wl,--max-memory=65536','-Wl,-z,stack-size=8192',
 ...exports.map(n=>'-Wl,--export='+n)];
function run(args){const r=spawnSync(compiler,args,{cwd:root,encoding:'utf8'});if(r.error)throw r.error;if(r.status!==0)throw new Error(r.stderr||r.stdout);return r.stdout;}
run([...flags,'web-player/native/avr.c','-lc','-lclang_rt.builtins','-o',join(output,'avr.wasm')]);
const binary=readFileSync(join(output,'avr.wasm')),module=await WebAssembly.compile(binary);
if(WebAssembly.Module.imports(module).length)throw new Error('AVR module must have no host imports');
const hash=b=>createHash('sha256').update(b).digest('hex');
const inputs=['web-player/native/avr.c','web-player/scripts/build-wasm.mjs'];
const manifest={schema:'micromusic-avr-wasm-v1',compilerVersion:run(['--version']).split(/\r?\n/)[0],
 flags:flags.map(f=>f.replaceAll(sysroot,'<emsdk>/upstream/emscripten/cache/sysroot')),
 inputs:Object.fromEntries(inputs.map(p=>[p,hash(readFileSync(join(root,p),'utf8').replaceAll('\r\n','\n'))])),
 artifacts:{'avr.wasm':hash(binary)},bytes:binary.length,memoryPages:1,imports:[]};
writeFileSync(join(output,'build.json'),JSON.stringify(manifest,null,2)+'\n');
console.log('Built import-free AVR C/WASM:',binary.length,'bytes');
