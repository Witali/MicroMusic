"""Assemble and audit the actual unrolled Alicia music scaling recipe.

This verifies a bounded arithmetic snippet, not whole-player timing or size.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(command,cwd):
    result = subprocess.run(list(map(str,command)),cwd=cwd,text=True,capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'ATtiny13A/Music/variants/alicia/synth.S')
    p.add_argument('--output',type=Path,default=ROOT/'build/avr-music-scale')
    p.add_argument('--avr-bin',type=Path,required=True)
    p.add_argument('--node',required=True)
    p.add_argument('--retain',type=Path)
    a = p.parse_args()
    source = a.source.read_text(encoding='utf-8')
    if source.count('\n.L25c:') != 1:
        raise ValueError('Music scaler label changed; review the extraction')
    section = source.split('\n.L25c:',1)[1].split('\nvoice_silent:',1)[0]
    if not section.rstrip().endswith('ret'):
        raise ValueError('Music scaler return changed; review the extraction')
    output = a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    (output/'recipe.S').write_text('.section .text\n.global recipe\nrecipe:'+section+'\n',encoding='ascii',newline='\n')
    run([a.avr_bin/'avr-gcc','-mmcu=attiny13','-nostdlib','-nostartfiles',
         '-Wl,-Ttext=0,-e,recipe','recipe.S','-o','recipe.elf'],output)
    run([a.avr_bin/'avr-objcopy','-O','binary','recipe.elf','recipe.bin'],output)
    verification = '''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from REFERENCE;
import {AVRCore as Wasm} from WASM;
const bytes=readFileSync(IMAGE);
const engines=[new Reference(bytes),new Wasm(bytes),new Wasm(bytes,undefined,{fastIdle:false,fastBlocks:false})];
let checked=0,minimum=Infinity,maximum=0;
function execute(cpu,wave,gain,flags){
 cpu.pc=0;cpu.sp=0x9f;cpu.sreg=flags;cpu.r[17]=wave&255;cpu.r[25]=gain;
 cpu.pushPC(511);const start=cpu.cyc;
 let steps=0;while(cpu.pc!==511&&steps++<64)cpu.step();
 assert.equal(cpu.pc,511,'Routine did not return');
 assert.equal(cpu.sp,0x9f,'Unbalanced return stack');
 assert.equal(cpu.r[25],gain,'Gain input changed');
 const cycles=cpu.cyc-start;minimum=Math.min(minimum,cycles);maximum=Math.max(maximum,cycles);
 return (cpu.r[17]+128&255)-128;
}
for(const cpu of engines)for(let wave=-8;wave<=7;wave++)for(let gain=0;gain<=15;gain++)for(const flags of [0,0x35,0xff]){
 assert.equal(execute(cpu,wave,gain,flags),Math.floor(wave*gain/4)||0,JSON.stringify({wave,gain,flags}));checked++;
}
assert.equal(checked,2304);
for(const cpu of engines){
 const actual=execute(cpu,100,15,0);
 assert.equal(actual,-9);assert.notEqual(actual,Math.floor(100*15/4));
}
console.log(JSON.stringify({engines:['reference','wasm','wasm-unoptimized'],in_domain_cases:checked,
 outside_domain_counterexamples:engines.length,min_body_cycles_including_ret:minimum,
 max_body_cycles_including_ret:maximum,rcall_cycles:3,standalone_abi:{input_wave:'r17',
 input_gain:'r25',output:'r17',clobbers:['r0','r17','SREG']},pass:true}));
'''
    for key,value in (('REFERENCE',(ROOT/'web-player/lib/avr-reference.js').as_uri()),
                      ('WASM',(ROOT/'web-player/lib/avr-core.js').as_uri()),('IMAGE',str(output/'recipe.bin'))):
        verification = verification.replace(key,json.dumps(value))
    (output/'verify.mjs').write_text(verification,encoding='utf-8',newline='\n')
    checked = json.loads(run([a.node,output/'verify.mjs'],ROOT).stdout)
    binary = (output/'recipe.bin').read_bytes()
    report = dict(schema='avr-unrolled-music-scale-v1',source=a.source.resolve().relative_to(ROOT).as_posix(),
        source_sha256_normalized_lf=sha(source.encode()),extracted_section_sha256=sha(section.encode()),
        binary_sha256=sha(binary),code_bytes_including_ret=len(binary),words_including_ret=len(binary)//2,
        exact_integer_function='floor(wave*gain/4), wave=-8..7, gain=0..15',verification=checked,
        limits='No complete-player/ISR timing claim; 8-bit product is unsafe for unrestricted speech samples',
        probe_source_sha256_normalized_lf=sha(Path(__file__).read_text(encoding='utf-8').encode()))
    data = json.dumps(report,indent=2)+'\n'
    (output/'report.json').write_text(data,encoding='utf-8',newline='\n')
    if a.retain:
        a.retain.parent.mkdir(parents=True,exist_ok=True)
        a.retain.write_text(data,encoding='utf-8',newline='\n')
    print(data)


if __name__ == '__main__': main()
