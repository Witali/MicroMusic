"""Compare current v9 with frozen v9 ELFs using the same IRQ observer.

Baseline is the ignored output directory of verify_attiny88_v9.py at f7481ef9.
Its loaded Flash bytes, compiler recipe and waveform/timing are rechecked.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from verify_attiny88_universal import ROOT,REPO,streams
from verify_attiny88_player import verify
from build_attiny88_player import target_path
from speech_v9 import repack


def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))


def run(output,baseline,wsl=None):
    output=Path(output).resolve();baseline=Path(baseline).resolve()
    if REPO/'build' not in output.parents:raise ValueError('Use ignored build storage')
    output.mkdir(parents=True,exist_ok=True)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    path=lambda p:target_path(p,wsl)
    def command(*args):
        r=subprocess.run([*prefix,*args],capture_output=True)
        if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
        return r.stdout
    observer=output/'observer';observer.mkdir(exist_ok=True)
    shutil.copyfile(baseline/'bread-quality/v9/hardware.h',observer/'hardware.h')
    command('gcc','-O2','-std=c11','-I'+path(observer),'-I/usr/include/simavr',
            path(ROOT.parent/'validation/attiny88/sim_player.c'),'-lsimavr','-lelf','-o',path(observer/'sim_player'))
    original=read(baseline/'summary.json')
    rows=[]
    fields=['samples','flash_bytes','program_excluding_audio_bytes','embedded_audio_bytes','static_ram_bytes',
            'stack_bytes','stack_margin','underruns','min_queue','decode_mean','decode_active_irq_mean','decode_max',
            'decode_cycles','decode_irq_cycles','decode_cpu_cycles','decode_cpu_mean','decode_active_cpu_mean',
            'decode_cpu_max','irq_max','output_gap_min','output_gap_max']
    for name,source in streams(output):
        encoded,_=repack(source.read_bytes());old=baseline/name/'v9';cost=read(old/'build.json')
        assert cost['universal'] and cost['compact_version']==9 and cost['queue']==44
        assert cost['input_sha256']==sha(encoded)
        assert not any(f.startswith('-DLPX4_FIXED_') for f in cost['compiler_options'])
        out=output/name;out.mkdir(exist_ok=True)
        command('avr-objcopy','-O','binary','-R','.eeprom',path(old/'player.elf'),path(out/'baseline.bin'))
        assert sha((out/'baseline.bin').read_bytes())==cost['image_sha256']
        assert (old/'hardware.h').read_bytes()==(observer/'hardware.h').read_bytes()
        command(path(observer/'sim_player'),path(old/'player.elf'),path(out/'baseline.pwm'),path(out/'baseline.json'))
        before=read(out/'baseline.json');stored=read(old/'timing.json')
        for field,value in stored.items():assert before[field]==value,(name,field)
        expected=next(row for row in original['cases'] if row['case']==name)['pwm_sha256']
        assert sha((out/'baseline.pwm').read_bytes())==expected
        before.update({f:cost[f] for f in ('flash_bytes','program_excluding_audio_bytes','embedded_audio_bytes','static_ram_bytes')})
        media=out/'stream.lpx';media.write_bytes(encoded)
        after=verify(media,out/'current',wsl=wsl)
        assert after['accepted'],(name,after)
        assert sha((out/'current/actual.pwm').read_bytes())==expected
        assert after['embedded_audio_bytes']==before['embedded_audio_bytes']
        assert after['program_excluding_audio_bytes']<before['program_excluding_audio_bytes']
        assert after['decode_cpu_cycles']<=before['decode_cpu_cycles'],name
        assert after['stack_bytes']<=before['stack_bytes'] and after['stack_margin']>=before['stack_margin']
        for row in (before,after):
            assert row['decode_cycles']==row['decode_cpu_cycles']+row['decode_irq_cycles']
            assert row['decode_irq_cycles']%42==0 and row['irq_max']==42 and row['underruns']==0
        row={'case':name,'data_sha256':sha(encoded),'pwm_sha256':expected,'pwm_exact':True,
             'before':{f:before[f] for f in fields},'after':{f:after[f] for f in fields}}
        rows.append(row);print(json.dumps(row),flush=True)
    sources=[*sorted((ROOT/'src').glob('Lpx4*')),ROOT/'src/native_batch_decoder.cpp',ROOT/'tools/batch_decoder.py',
             ROOT/'tools/build_attiny88_player.py',ROOT/'tools/verify_attiny88_player.py',ROOT/'tools/speech_v9.py',
             ROOT/'tests/test_batch_v9.py',ROOT/'tests/test_speech_v9.py',ROOT/'tests/verify_attiny88_universal.py',
             ROOT/'tests/test_sram512_profile.py',ROOT/'profiles/Lpx4Sram512.h',
             REPO/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h',
             ROOT.parent/'validation/attiny88/sim_player.c',ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp',Path(__file__)]
    report={'schema':'lpx-v9-next-admission-v1','baseline_revision':'f7481ef9','cpu':'ATtiny88 / AVR25',
            'clock_hz':16000000,'sample_hz':8000,'queue':44,'parameters':'runtime LPX header',
            'physical_board_measured':False,'source_hash_encoding':'text-lf','cases':rows,
            'source_sha256':{p.relative_to(REPO).as_posix():sha(p.read_bytes().replace(b'\r\n',b'\n')) for p in sources}}
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('baseline',type=Path);parser.add_argument('--wsl')
    args=parser.parse_args();run(args.output,args.baseline,args.wsl)
