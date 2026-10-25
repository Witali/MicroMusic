#!/usr/bin/env python3
"""Diagnose transient two-byte SP writes in decoder-only WB measurements.

This supplemental probe does not replace the full corpus/IRQ admission tests.
It samples before/after images and counts SP only after paired byte writes,
also retaining the conservative raw-SP minimum. Register addresses come from
the configured ATmega328P avr/io.h definitions, not a copied device map.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc',required=True);parser.add_argument('--node',default='node')
    parser.add_argument('--frames',type=int,default=8)
    parser.add_argument('--out',type=Path,default=ROOT/'build/subframe-stack-probe')
    args=parser.parse_args()
    if args.frames<1:parser.error('--frames must be positive')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    source=out/'registers.c'
    source.write_text('#include <avr/io.h>\nconst unsigned char probe_io[] __attribute__((section(".probe_io"))) = '
        '{_SFR_IO_ADDR(SPL),_SFR_IO_ADDR(SPH),_SFR_MEM_ADDR(SPL),_SFR_MEM_ADDR(SPH)};\n')
    subprocess.run([args.avr_gcc,'-mmcu=atmega328p','-c',str(source),'-o',str(out/'registers.o')],check=True)
    objcopy=str(Path(args.avr_gcc).with_name('avr-objcopy'+('.exe' if args.avr_gcc.endswith('.exe') else '')))
    subprocess.run([objcopy,'-j','.probe_io','-O','binary',str(out/'registers.o'),str(out/'registers.bin')],check=True)
    addresses=list((out/'registers.bin').read_bytes());assert len(addresses)==4
    text=(ROOT/'tests/verify_wb.mjs').read_text()
    text=text.replace('let minSP=2303,lastChunk=0,output=[],hits=new Map();',
        'let minSP=2303,stableMin=2303,pendingSP=0,spPairs=0,lastChunk=0,output=[],hits=new Map();')
    anchor="avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');"
    observer='''const op=cpu.progMem[cpu.pc];
   const stackOp=(op&0xfe0f)===0x920f || (op&0xfe0f)===0x900f ||
      (op&0xf000)===0xd000 || (op&0xfe0e)===0x940e ||
      [0x9508,0x9518,0x9509,0x9519].includes(op);
   assert.ok(!(pendingSP && stackOp),'Stack access during incomplete SP byte writes');
   let spByte=0;
   if((op&0xf800)===0xb800){const io=((op>>>5)&0x30)|(op&15);spByte=io===SPL_IO?1:io===SPH_IO?2:0;}
   if((op&0xfe0f)===0x9200){const mem=cpu.progMem[cpu.pc+1];spByte=mem===SPL_MEM?1:mem===SPH_MEM?2:0;}
   avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);
   if(spByte){pendingSP|=spByte;if(pendingSP===3){pendingSP=0;spPairs++;}}
   if(!pendingSP)stableMin=Math.min(stableMin,cpu.SP);
   assert.ok(cpu.SP>=end,'SRAM collision');'''
    for key,value in zip(['SPL_IO','SPH_IO','SPL_MEM','SPH_MEM'],addresses):observer=observer.replace(key,str(value))
    assert text.count(anchor)==1;text=text.replace(anchor,observer)
    text=text.replace('peakStack:2303-minSP,freeSram:',
        'peakStack:2303-minSP,completedPairPeakStack:2303-stableMin,spPairs,pendingSP,freeSram:')
    script=out/'verify.mjs';script.write_text(text)
    rows=[]
    for state in ['before','after']:
        for backend in ['asm','c']:
            image=out/(state+'-'+backend);image.mkdir(exist_ok=True)
            original=ROOT/'build'/(('lsp-quarter-wb-' if state=='before' else 'subframe-wb-')+backend)
            for name in ['wb.bin','wb.elf','symbols.txt','backend.json']:shutil.copyfile(original/name,image/name)
            with (image/'simulation.log').open('w') as log:
                subprocess.run([args.node,str(script),'--backend',backend,'--firmware',str(image),
                    '--streams',str(ROOT/'build/wb-corpus/streams'),'--oracle',str(ROOT/'build/wb-corpus/oracle'),
                    '--frames',str(args.frames)],stdout=log,stderr=subprocess.STDOUT,check=True)
            data=json.loads((image/'verification.json').read_text())
            assert all(r['pendingSP']==0 for r in data['streams'])
            rows.append(dict(state=state,backend=backend,binarySha256=data['binarySha256'],frames=data['frames'],
                rawPeakStack=data['peakStack'],completedPairPeakStack=max(r['completedPairPeakStack'] for r in data['streams']),
                completedSpPairs=sum(r['spPairs'] for r in data['streams']),noStackAccessBetweenByteWrites=True))
    include=Path(args.avr_gcc).resolve().parents[1]/'avr/include/avr'
    result=dict(scope='Supplemental sampled WB decoder-only SP diagnostic; no IRQ or physical-board claim',
        compiler=subprocess.check_output([args.avr_gcc,'--version'],text=True).splitlines()[0],
        registerDefinitionHeaders={n:digest(include/n) for n in ['io.h','common.h','iom328p.h']},
        registerAddresses=dict(zip(['splIo','sphIo','splMem','sphMem'],addresses)),
        observerSourceSha256=digest(script),rows=rows,includesInterrupts=False,physicalBoardTested=False)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
