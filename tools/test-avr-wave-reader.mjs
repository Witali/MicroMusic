import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdirSync,readFileSync,existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {AVRCore} from '../web-player/lib/avr-core.js';

const root=fileURLToPath(new URL('../',import.meta.url));
const common=execFileSync('git',['rev-parse','--path-format=absolute','--git-common-dir'],{cwd:root,encoding:'utf8'}).trim();
const suffix=process.platform==='win32'?'.exe':'';
const avrBin=process.argv[2]??path.join(path.dirname(common),'build/toolchains/avr-7.3.0/bin');
const executable=name=>{const file=path.join(avrBin,name+suffix);assert.ok(existsSync(file),file);return file;};
const source=path.join(root,'docs/avr-asm-cookbook/examples/attiny88-wave-reader.c');
const driver=path.join(root,'docs/avr-asm-cookbook/examples/attiny88-wave-reader-driver.S');
const scratch=path.join(root,'build/avr-wave-reader');mkdirSync(scratch,{recursive:true});
const expected=Uint8Array.from({length:64},(_,i)=>i*19&255);
for(const backend of ['c','asm']){
  const elf=path.join(scratch,backend+'.elf'),bin=path.join(scratch,backend+'.bin');
  execFileSync(executable('avr-gcc'),['-mmcu=attiny88','-nostdlib','-Wl,-e,vectors','-Os',`-DMICROMUSIC_WAVE_READ_ASM=${backend==='asm'?1:0}`,driver,source,'-o',elf]);
  execFileSync(executable('avr-objcopy'),['-O','binary','-j','.text',elf,bin]);
  const symbols=Object.fromEntries(execFileSync(executable('avr-nm'),['-n',elf],{encoding:'utf8'}).trim().split(/\r?\n/)
    .map(line=>line.match(/^([a-f\d]+)\s+\w\s+(\S+)$/i)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
  const observed=symbols.observed-0x800000,complete=symbols.complete-0x800000;
  const cpu=new AVRCore(readFileSync(bin),null,{target:'attiny88'});
  while(cpu.data[complete]!==0xa5&&cpu.cyc<100000)cpu.step();
  assert.equal(cpu.data[complete],0xa5,backend+' fixture completed');
  assert.deepEqual(cpu.data.subarray(observed,observed+64),expected,backend+' reads the same Flash bank');
  console.log(`${backend}: 64 Flash bytes match the independent fixture; ${cpu.cyc} model cycles`);
}
