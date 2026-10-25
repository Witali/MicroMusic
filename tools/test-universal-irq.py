"""Assemble/execute UM88 IRQ drivers at every legal byte capacity and channel count.

The standalone fixtures test the actual production ASM or C ISR, not a rewritten
model. No scores or retained firmware are changed. Requires GNU AVR and Node.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'ATtiny88/Music/universal'
spec=importlib.util.spec_from_file_location('irq_test_builder',ROOT/'tools/build-universal-music.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def digest(path):
    return hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin')
    parser.add_argument('--node')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/universal/irq-driver')
    parser.add_argument('--report',type=Path)
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--reuse',action='store_true',help='Reuse fixtures only when all compiled source hashes still match')
    args=parser.parse_args();tools=builder.legacy.toolchain(args.avr_bin)
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    report=(args.report or output/'verification.json').resolve()
    vendor_header=SOURCE/'vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h'
    vector_match=re.search(r'^\s*#define\s+TIMER1_OVF_vect_num\s+(\d+)\b',
                           vendor_header.read_text(encoding='utf-8'),re.M)
    assert vector_match,'Timer1 overflow vector must come from the pinned device header'
    vector_name='__vector_'+vector_match[1]
    sources=[SOURCE/name for name in ('irq-avr.S','irq-scratch.h','audio-buffer.h','audio-channels.h',
        'platform.c','engine.h','clock.h','rational-clocks.h','storage.h',
        'vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h')]
    hashes={str(file.relative_to(ROOT)).replace('\\','/'):digest(file) for file in sources}
    manifest_file=output/'manifest.json'
    if args.reuse:
        manifest=json.loads(manifest_file.read_text(encoding='utf-8'))
        assert manifest['sourceTextLfSha256']==hashes,'Rebuild fixtures after a source change'
    else:
        stub=output/'storage.S'
        stub.write_text('''.section .bss,"aw",@nobits
.global um_read,um_write,um_underruns
um_read: .skip 1
um_write: .skip 1
um_underruns: .skip 1
.section .noinit,"aw",@nobits
.balign 256
.global um_ring
um_ring: .skip 192
''',encoding='utf-8',newline='\n')
        fixtures=[]
        for driver in ('stack','gpior','compiler'):
            for capacity in range(8,193,4):
                for channels in (1,2):
                    work=output/driver/f'{capacity}-{channels}';work.mkdir(parents=True,exist_ok=True)
                    elf=work/'irq.elf';binary=work/'irq.bin'
                    defines=['-DUM_REQUESTED_CPU_HZ=8000000UL',f'-DUM_REQUESTED_BUFFER_FRAMES={capacity}',
                        f'-DUM_REQUESTED_OUTPUT_CHANNELS={channels}',f'-DUM_ENABLE_AVR_ASM={int(driver!="compiler")}',
                        f'-DUM_REQUESTED_IRQ_GPIOR_SCRATCH={int(driver!="stack")}']
                    command=[tools['avr-gcc'],'-mmcu=attiny88','-nostartfiles','-nostdlib',
                        '-I'+str(SOURCE/'vendor/ATtiny_DFP/3.4.278/include'),*defines]
                    if driver=='compiler':
                        # Discard main and its engine references; retain the actual C ISR
                        # and only the storage it references. Requesting GPIOR must not
                        # make the selectable compiler ISR claim those registers.
                        command+=['-Os','-ffunction-sections','-fdata-sections',
                            '-Wl,--gc-sections,-e,'+vector_name,SOURCE/'platform.c']
                    else:command+=[SOURCE/'irq-avr.S',stub]
                    builder.legacy.run(*command,'-o',elf)
                    builder.legacy.run(tools['avr-objcopy'],'-O','binary','-j','.text',elf,binary)
                    symbols=builder.legacy.run(tools['avr-nm'],'-n',elf)
                    labels={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-fA-F]+)\s+([tTbBdDnN])\s+(\S+)$',symbols,re.M)}
                    assert labels['um_ring']&255==0,'FIFO remains page aligned'
                    meta=dict(irqScratch=driver,requestedIrqScratch='gpior' if driver!='stack' else 'stack',
                        cpuHz=8000000,pwmBufferBytes=capacity,configuredChannels=channels,labels=labels,
                        irqBytes=binary.stat().st_size,irqSha256=hashlib.sha256(binary.read_bytes()).hexdigest())
                    metadata=work/'irq.json';metadata.write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
                    fixtures.append(dict(metadata=str(metadata),binary=str(binary)))
            print(driver+': all 47 capacities and both channel counts assembled',flush=True)
        manifest=dict(schema='micromusic-um88-irq-fixtures',version=1,sourceTextLfSha256=hashes,
            toolchainVersion=builder.legacy.run(tools['avr-gcc'],'--version').splitlines()[0],
            cpu='ATtiny88/AVR25',hardwareTested=False,fixtures=fixtures)
        manifest_file.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    if not args.build_only:
        node=args.node or shutil.which('node')
        if not node:
            candidates=sorted(Path(tools['avr-gcc']).resolve().parents[2].glob('node-*/node.exe'))
            if candidates:node=str(candidates[-1])
        if not node:raise RuntimeError('Node not found; supply --node')
        subprocess.run([str(node),str(ROOT/'tools/test-universal-irq.mjs'),
            '--manifest='+str(manifest_file),'--report='+str(report)],cwd=ROOT,check=True)


if __name__=='__main__':main()
