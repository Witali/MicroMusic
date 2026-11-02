"""Build and verify complete ATtiny88 playback against a portable C reference.

Requires AVR-GCC, g++, simavr1.6 development files and libelf. Standard Python
library only. On Windows use --wsl Ubuntu with the existing Linux toolchain.
"""
import argparse
import json
from pathlib import Path
import subprocess
from build_attiny88_player import build,target_path,ROOT,REPO

REFERENCE=r'''
#include <stdio.h>
#include "Lpx4HybridCore.h"
static const unsigned char audio[]={
#include "audio.inc"
};
int main(){
 Lpx4HybridCore d;if(!d.begin(audio,sizeof(audio)))return 1;
 unsigned char p;while(d.next(p))putchar(p);
 return d.error()?2:0;
}
'''

def verify(source,output,*,assembly=True,asm_isr=True,queue=32,repeat=1,wsl=None,
           flash_limit=6656,lpc_segments=2):
    output=Path(output).resolve()
    cost=build(source,output,assembly=assembly,asm_isr=asm_isr,queue=queue,repeat=repeat,wsl=wsl,lpc_segments=lpc_segments,flash_limit=flash_limit)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    path=lambda p:target_path(p,wsl)
    def run(*args):
        r=subprocess.run([*prefix,*args],capture_output=True)
        if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
        return r.stdout
    (output/'reference.cpp').write_text(REFERENCE,encoding='ascii')
    if run('pkg-config','--modversion','simavr').decode().strip()!='1.6':
        raise ValueError('This calibrated interrupt-entry adapter requires simavr1.6')
    run('g++','-O2','-std=c++11',f'-DLPX3_LPC_SEGMENTS={lpc_segments}',
        '-include',path(ROOT/'profiles/Lpx4Sram512.h'),'-I'+path(ROOT/'src'),
        path(output/'reference.cpp'),path(ROOT/'src/Lpx4HybridCore.cpp'),'-o',path(output/'reference'))
    expected=run(path(output/'reference'))*repeat
    (output/'expected.pwm').write_bytes(expected)
    run('gcc','-O2','-std=c11','-I'+path(output),'-I/usr/include/simavr',
        path(ROOT.parent/'validation/attiny88/sim_player.c'),'-lsimavr','-lelf','-o',path(output/'sim_player'))
    log=run(path(output/'sim_player'),path(output/'player.elf'),path(output/'actual.pwm'),path(output/'timing.json'))
    (output/'observer.log').write_bytes(log)
    timing=json.loads((output/'timing.json').read_text())
    actual=(output/'actual.pwm').read_bytes()
    exact=actual==expected
    timing.update(pwm_exact=exact,flash_bytes=cost['flash_bytes'],static_ram_bytes=cost['static_ram_bytes'],
        flash_limit=flash_limit,queue=queue,repeat=repeat,assembly=assembly,asm_isr=asm_isr,
        embedded_audio_bytes=cost['embedded_audio_bytes'],program_excluding_audio_bytes=cost['program_excluding_audio_bytes'],
        physical_board_measured=False)
    timing['accepted']=bool(exact and timing['samples']==timing['ticks']==timing['timer_events']==cost['samples']
        and not timing['underruns'] and timing['error']==0 and timing['eof']==timing['stopped']==1
        and timing['queue_empty'] and timing['timer_stopped'] and timing['stack_margin']>0
        and timing['irq_entry_cycles']==4 and timing['irq_reti_complete']
        and (cost['samples']<2 or (timing['output_gap_min']>=1980 and timing['output_gap_max']<=2020))
        and cost['flash_bytes']<=flash_limit and cost['static_ram_bytes']+timing['stack_bytes']<512)
    (output/'verification.json').write_text(json.dumps(timing,indent=2)+'\n',encoding='utf-8')
    return timing

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--wsl');ap.add_argument('--c',action='store_true');ap.add_argument('--c-isr',action='store_true')
    ap.add_argument('--queue',type=int,choices=(16,32),default=32);ap.add_argument('--repeat',type=int,default=1)
    ap.add_argument('--flash-limit',type=int,default=6656)
    a=ap.parse_args();r=verify(a.input,a.output,wsl=a.wsl,assembly=not a.c,asm_isr=not a.c_isr,
        queue=a.queue,repeat=a.repeat,flash_limit=a.flash_limit)
    print(json.dumps(r));raise SystemExit(0 if r['accepted'] else 1)
