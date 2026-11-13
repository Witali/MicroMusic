"""Full IRQ playback with runtime LPX headers and independent portable C output.

Generated media, binaries and full reports stay under ignored build storage.
The fixture writer needs no private inputs or third-party Python packages.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from verify_attiny88_player import verify
from test_sram512_profile import fixture


def streams(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    clips=json.loads((REPO/'web-player/audio/lpx-speech/manifest.json').read_text(encoding='utf-8'))['clips']
    clips.append(dict(json.loads((REPO/'web-player/audio/lpx-bread/manifest.json').read_text(encoding='utf-8')),clipId='bread'))
    streams=[(clip['clipId']+'-'+v['id'],REPO/'web-player'/v['stream'])
             for clip in clips for v in clip['variants'] if v['id'] in ('compact','quality')]
    for profile,style,lag,pre,bright,extras in [
        (4,'changing',145,0,0,False),
        (4,'clusters',18,16384,11469,True),
        (6,'changing',145,8192,11469,True),
        (6,'clusters',18,8192,11469,True),
        (6,'changing',18,16383,11468,False),
        (6,'clusters',145,1,1,True),
    ]:
        name=f'p{profile}-{style}-lag{lag}-pre{pre}-bright{bright}'
        blob=bytearray(fixture(profile,12800,lag,style,extras))
        struct.pack_into('<HH',blob,12,pre,bright)
        path=output/(name+'.lpx');path.write_bytes(blob);streams.append((name,path))
    return streams


def run(output,wsl=None):
    output=Path(output).resolve()
    if REPO/'build' not in output.parents:raise ValueError('Use ignored build storage')
    output.mkdir(parents=True,exist_ok=True)
    inputs=streams(output)
    rows=[]
    for name,path in inputs:
        result=verify(path,output/name,wsl=wsl)
        cost=json.loads((output/name/'build.json').read_text())
        assert cost['universal'] and cost['queue']==44
        assert not any(flag.startswith('-DLPX4_FIXED_') for flag in cost['compiler_options'])
        assert result['accepted'],(name,result)
        row={'case':name,**{key:result[key] for key in (
            'samples','flash_bytes','program_excluding_audio_bytes','static_ram_bytes',
            'stack_bytes','stack_margin','underruns','min_queue','decode_mean','decode_max',
            'irq_max','irq_entry_cycles','irq_reti_complete','output_gap_min','output_gap_max','pwm_exact')}}
        row['pwm_sha256']=hashlib.sha256((output/name/'actual.pwm').read_bytes()).hexdigest()
        rows.append(row);print(json.dumps(row),flush=True)
    sources=[ROOT/'src/Lpx4Math.h',ROOT/'src/Lpx4MultiplyAvr.h',ROOT/'src/Lpx4MultiplyC.h',
             ROOT/'src/Lpx4HybridCore.cpp',ROOT/'src/Lpx4HybridCore.h',
             ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp',ROOT/'tools/build_attiny88_player.py',
             ROOT/'tools/verify_attiny88_player.py',Path(__file__)]
    report={'schema':'lpx-attiny88-universal-v1','cpu':'ATtiny88 / AVR25',
            'clock_hz':16000000,'sample_hz':8000,'queue':44,'prefill':33,
            'compiler':cost['compiler'],'parameters':'runtime LPX header',
            'arithmetic':'explicit AVR25 ASM; C remains selectable',
            'physical_board_measured':False,'source_hash_encoding':'text-lf',
            'source_sha256':{p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in sources},
            'cases':rows}
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('--wsl')
    args=parser.parse_args();run(args.output,args.wsl)
