import {spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync,readdirSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const repo=fileURLToPath(new URL('../',import.meta.url));
const rootArgument=process.argv.indexOf('--root');
if(rootArgument<0||!process.argv[rootArgument+1])throw new Error('Pass --root <toolchain directory>');
const tools=resolve(process.argv[rootArgument+1]);
const node=join(tools,'node-22.22.3/node.exe'),python=join(tools,'python-3.13.3/python.exe');
const clang=join(tools,'emscripten-6.0.12/upstream/bin/clang.exe');
const avr=join(tools,'avr-7.3.0/bin');
const output=join(repo,'build/toolchains/verification');mkdirSync(output,{recursive:true});
function run(command,args){
  const r=spawnSync(command,args,{cwd:repo,encoding:'utf8'});
  if(r.error)throw r.error;if(r.status!==0)throw new Error(`${command}: ${r.stderr||r.stdout}`);return r.stdout;
}
for(const [command,args]of [[node,['--version']],[python,['--version']],[clang,['--version']],
 [join(avr,'avr-gcc.exe'),['--version']],[join(avr,'avr-as.exe'),['--version']]])console.log(run(command,args).split(/\r?\n/)[0]);
const source=join(output,'wasm-smoke.c'),binary=join(output,'wasm-smoke.wasm');
writeFileSync(source,'int add(int x,int y){return x+y;}\n');
run(clang,['--target=wasm32-unknown-unknown','-O2','-nostdlib','-Wl,--no-entry','-Wl,--export=add',source,'-o',binary]);
const {instance}=await WebAssembly.instantiate(readFileSync(binary));assert.equal(instance.exports.add(17,25),42);
console.log('C compiler/linker/WASM runtime: verified');
const variants=join(repo,'ATtiny13A/Music/variants');
for(const folder of readdirSync(variants,{withFileTypes:true}).filter(e=>e.isDirectory())){
  const dir=join(variants,folder.name),elf=join(output,folder.name+'.elf'),bin=join(output,folder.name+'.bin');
  // GNU aligns .text to a word with zero. The retained assembler pads erased
  // Flash with FF instead. Locate the source end before normalizing that byte.
  const wrapper=join(output,folder.name+'.S');
  writeFileSync(wrapper,`.include "${join(dir,'synth.S').replaceAll('\\','/')}"\n.global micromusic_image_end\nmicromusic_image_end:\n`);
  run(join(avr,'avr-gcc.exe'),['-mmcu=attiny13a','-nostdlib','-x','assembler',`-Wa,-I,${dir}`,
    '-Wl,-e,vectors','-Wl,--section-start=.text=0',wrapper,'-o',elf]);
  run(join(avr,'avr-objcopy.exe'),['-O','binary','-j','.text',elf,bin]);
  const symbol=run(join(avr,'avr-nm.exe'),['-n',elf]).match(/^([0-9a-f]+)\s+\w\s+micromusic_image_end$/m);
  assert.ok(symbol,'Source end symbol');const size=parseInt(symbol[1],16);
  const assembled=readFileSync(bin);assert.equal(assembled.length,size+(size%2));
  if(size%2)assembled[size]=255;
  assert.deepEqual(assembled,readFileSync(join(dir,'synth.bin')),folder.name+' GNU AVR image');
  console.log(folder.name+': GNU AVR assembly matches retained firmware');
}
console.log(run(python,[join(repo,'tools/assemble-avr.py'),'--verify']).trim());
console.log(run(python,[join(repo,'web-player/scripts/build_catalog.py'),'--check']).trim());
