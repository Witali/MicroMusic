"""Matched v5/v9 full IRQ playback, compressed size and independent C output."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from verify_attiny88_universal import ROOT,REPO,streams
from verify_attiny88_player import verify
from speech_v9 import repack


def run(output,wsl=None):
    output=Path(output).resolve()
    if REPO/'build' not in output.parents:raise ValueError('Use ignored build storage')
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name,source in streams(output):
        blob=source.read_bytes();encoded,stats=repack(blob)
        assert len(encoded)<len(blob),name
        path=output/(name+'-v9.lpx');path.write_bytes(encoded)
        before=verify(source,output/name/'v5',wsl=wsl)
        after=verify(path,output/name/'v9',wsl=wsl)
        assert before['accepted'] and after['accepted'],(name,before,after)
        assert (output/name/'v5/actual.pwm').read_bytes()==(output/name/'v9/actual.pwm').read_bytes(),name
        assert after['program_excluding_audio_bytes']<before['program_excluding_audio_bytes'],name
        assert after['decode_active_irq_mean']<=before['decode_active_irq_mean'],(name,before['decode_active_irq_mean'],after['decode_active_irq_mean'])
        assert before['irq_max']==after['irq_max']==42
        fields=['samples','flash_bytes','program_excluding_audio_bytes','embedded_audio_bytes',
                'static_ram_bytes','stack_bytes','stack_margin','underruns','min_queue',
                'decode_mean','decode_active_irq_mean','decode_max','irq_max','output_gap_min','output_gap_max']
        row={'case':name,'repack':stats,'before':{f:before[f] for f in fields},
             'after':{f:after[f] for f in fields},'pwm_exact':True,
             'pwm_sha256':hashlib.sha256((output/name/'v9/actual.pwm').read_bytes()).hexdigest()}
        rows.append(row);print(json.dumps(row),flush=True)
    paths=[ROOT/'src/Lpx4HybridCore.cpp',ROOT/'src/Lpx4HybridCore.h',ROOT/'src/Lpx4Math.h',
           ROOT/'src/Lpx4MultiplyAvr.h',ROOT/'src/Lpx4MultiplyC.h',ROOT/'tools/speech_v9.py',
           ROOT/'tools/build_attiny88_player.py',ROOT/'tools/verify_attiny88_player.py',
           ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp',ROOT/'profiles/Lpx4Sram512.h',
           ROOT.parent/'validation/attiny88/sim_player.c',ROOT/'tests/test_sram512_profile.py',
           ROOT/'tests/test_speech_v9.py',Path(__file__),ROOT/'tests/verify_attiny88_universal.py']
    report={'schema':'lpx-v9-attiny88-admission-v1','cpu':'ATtiny88 / AVR25','clock_hz':16000000,
        'sample_hz':8000,'queue':44,'parameters':'runtime LPX header','source_hash_encoding':'text-lf',
        'physical_board_measured':False,'cases':rows,
        'source_sha256':{p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in paths}}
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('--wsl')
    args=parser.parse_args();run(args.output,args.wsl)
