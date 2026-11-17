"""Build and verify complete ATtiny88 playback against a portable C reference.

Requires AVR-GCC, g++, simavr1.6 development files and libelf. Standard Python
library only. On Windows use --wsl Ubuntu with the existing Linux toolchain.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from build_attiny88_player import build,target_path,ROOT,REPO
sys.path.insert(0,str(REPO/'tools'))
from pwm_output_level import apply_gain,choose_gain,describe_level

REFERENCE=r'''
#include <stdio.h>
#include "Lpx4HybridCore.h"
static const unsigned char audio[]={
#include "audio.inc"
};
int main(){
#ifdef LPX_REFERENCE_SEGMENTS
 static const unsigned short lengths[]={
#include "segment_lengths.inc"
 };
 unsigned offset=0;
 for(unsigned i=0;i<LPX_REFERENCE_SEGMENTS;i++){
  Lpx4HybridCore d;if(!d.begin(audio+offset,lengths[i]))return 1;
  unsigned char p;while(d.next(p))putchar(p);
  if(d.error())return 2;
  offset+=lengths[i];
 }
 return 0;
#else
 Lpx4HybridCore d;if(!d.begin(audio,sizeof(audio)))return 1;
 unsigned char p;while(d.next(p))putchar(p);
 return d.error()?2:0;
#endif
}
'''

def verify(source,output,*,assembly=True,asm_isr=True,queue=None,repeat=1,wsl=None,
           flash_limit=8192,lpc_segments=2,sparse80=False,mul16_unroll=None,normalize_output=False,universal=True,
           rom_output_gain=False,extra_flags=(),target='attiny88',nano_pwm=False,extended_sample_rates=True):
    output=Path(output).resolve()
    if universal and normalize_output and not rom_output_gain:
        raise ValueError('Universal playback must not specialize gain for a recording')
    if mul16_unroll is None:mul16_unroll=2 if universal else 16
    options=dict(assembly=assembly,asm_isr=asm_isr,queue=queue,repeat=repeat,wsl=wsl,lpc_segments=lpc_segments,
        flash_limit=flash_limit,sparse80=sparse80,mul16_unroll=mul16_unroll,universal=universal,
        rom_output_gain=rom_output_gain,extra_flags=extra_flags,target=target,nano_pwm=nano_pwm,extended_sample_rates=extended_sample_rates)
    cost=build(source,output,**options)
    queue=cost['queue']
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
        *(['-DLPX4_ENABLE_SPARSE80=1'] if sparse80 else []),
        f'-DLPX4_COMPACT_VERSION={cost["compact_version"]}',f'-DLPX4_EXTENDED_SAMPLE_RATES={int(extended_sample_rates)}',
        *([f'-DLPX_REFERENCE_SEGMENTS={len(cost["segment_bytes"])}'] if len(cost['segment_bytes'])>1 else []),
        '-include',path(ROOT/'profiles/Lpx4Sram512.h'),'-I'+path(ROOT/'src'),
        path(output/'reference.cpp'),path(ROOT/'src/Lpx4HybridCore.cpp'),'-o',path(output/'reference'))
    expected=run(path(output/'reference'))*repeat
    gain=choose_gain(expected) if normalize_output else 128
    level=describe_level(expected,gain)
    if rom_output_gain:
        level['implementation']='producer-rom-q7'
    if gain!=128:
        cost=build(source,output,output_gain=gain,**options)
        expected=apply_gain(expected,gain)
    (output/'expected.pwm').write_bytes(expected)
    run('gcc','-O2','-std=c11','-I'+path(output),'-I/usr/include/simavr',
        path(ROOT.parent/'validation/attiny88/sim_player.c'),'-lsimavr','-lelf','-o',path(output/'sim_player'))
    log=run(path(output/'sim_player'),path(output/'player.elf'),path(output/'actual.pwm'),path(output/'timing.json'))
    (output/'observer.log').write_bytes(log)
    timing=json.loads((output/'timing.json').read_text())
    actual=(output/'actual.pwm').read_bytes()
    exact=actual==expected
    period=cost['sample_period_cycles']
    timing.update(sample_hz=cost['sample_hz'],actual_sample_hz=cost['actual_sample_hz'],sample_period_cycles=period,
        sample_clock_policy=cost['sample_clock_policy'],pwm_exact=exact,flash_bytes=cost['flash_bytes'],static_ram_bytes=cost['static_ram_bytes'],
        flash_limit=flash_limit,queue=queue,repeat=repeat,assembly=assembly,asm_isr=asm_isr,
        embedded_audio_bytes=cost['embedded_audio_bytes'],program_excluding_audio_bytes=cost['program_excluding_audio_bytes'],
        physical_board_measured=False,universal=universal,bootloader_application_bytes=cost['bootloader_application_bytes'],
        fits_standard_bootloader=cost['fits_standard_bootloader'],requires_isp=cost['requires_isp'],mul16_unroll=mul16_unroll,outputLevel=level)
    timing['accepted']=bool(exact and timing['samples']==timing['ticks']==timing['timer_events']==cost['samples']
        and not timing['underruns'] and timing['error']==0 and timing['eof']==timing['stopped']==1
        and timing['queue_empty'] and timing['timer_stopped'] and timing['stack_margin']>0
        and timing['irq_entry_cycles']==4 and timing['irq_reti_complete']
        and (cost['samples']<2 or (timing['output_gap_min']>=period-20 and timing['output_gap_max']<=period+20))
        and cost['flash_bytes']<=flash_limit
        and cost['static_ram_bytes']+timing['stack_bytes']<(512 if target=='attiny88' else 2048))
    (output/'verification.json').write_text(json.dumps(timing,indent=2)+'\n',encoding='utf-8')
    return timing

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--wsl');ap.add_argument('--c',action='store_true');ap.add_argument('--c-isr',action='store_true')
    ap.add_argument('--queue',type=int,choices=(16,24,32,44));ap.add_argument('--repeat',type=int,default=1)
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument('--universal',dest='universal',action='store_true')
    mode.add_argument('--fixed-header',dest='universal',action='store_false')
    ap.set_defaults(universal=True)
    ap.add_argument('--flash-limit',type=int,default=8192)
    ap.add_argument('--enable-sparse80',action='store_true')
    ap.add_argument('--mul16-unroll',type=int,choices=(1,2,4,8,16))
    a=ap.parse_args();r=verify(a.input,a.output,wsl=a.wsl,assembly=not a.c,asm_isr=not a.c_isr,
        queue=a.queue,repeat=a.repeat,flash_limit=a.flash_limit,sparse80=a.enable_sparse80,mul16_unroll=a.mul16_unroll,universal=a.universal)
    print(json.dumps(r));raise SystemExit(0 if r['accepted'] else 1)
