#!/usr/bin/env python3
"""Validate completed LPX comparison cases as full active-IRQ AVR firmware."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from batch_decoder import BatchSession
from benchmark_standards import save,sha,cached_json
from profile_avr import run as profile
from standard_metrics import error_metrics,pwm_duties,ogg_accounting
from wav_lpc import load_wav


def run(corpus,results,output,avr_bin,runner,lib=None,wsl=None,watch=False):
    corpus,results,output=Path(corpus),Path(results),Path(output)
    output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    report=cached_json(output/'verification.json') or {'cases':[],'images':{},'ogg_independent_checks':{},
        'profile':'ATmega328P 16MHz / 8kHz; ASM opt-in; queue512/prefill384/unroll9; v3 feature mask24',
        'physical_hardware_measured':False,'expected_cases':len(manifest['cases'])}
    done={c['id'] for c in report['cases']}
    with BatchSession('batch',v3_features=124) as decoder:
        while True:
            for case in manifest['cases']:
                key=case['id']
                if key in done:continue
                data=cached_json(results/key/'complete.json')
                if not data:continue
                ref=load_wav(corpus/key/'reference.wav')[0]
                if sha(ref.astype('<i2').tobytes())!=data['reference_sha256']:raise ValueError('Reference mismatch')
                rows=[]
                for row in data['rates']:
                    item=row['LPX']
                    if item['status']!='ok':continue
                    path=Path(item['path']);blob=path.read_bytes();digest=sha(blob)
                    if digest!=item['stream_sha256']:raise ValueError('LPX stream changed')
                    pcm=decoder.decode_one_s16(blob,len(ref));pwm=decoder.decode_one(blob,len(ref))
                    if pcm is None or sha(pcm.astype('<i2').tobytes())!=item['pcm16_sha256']:raise AssertionError('Native PCM mismatch')
                    if not np.array_equal(pwm_duties(pcm),pwm):raise AssertionError('PWM mismatch')
                    met=error_metrics(ref,pcm)
                    for field in ('error_energy','max_abs_error_pcm16','max_error_sample'):
                        if met[field]!=item['metrics']['aligned_pcm16'][field]:raise AssertionError('Metric mismatch: '+field)
                    if digest not in report['images']:
                        measured=profile(path,output/digest,avr_bin,runner,lib,wsl,enable_asm=True,v3_features=24)
                        measured['decode_budget_percent']=measured['mean_decode_wall_cycles']/20
                        report['images'][digest]=measured
                    measured=report['images'][digest]
                    rows.append({'ceiling_bps':row['ceiling_bps'],'stream_sha256':digest,
                        'native_pcm16_exact':True,'native_pwm_exact':True,'error_metrics_exact':True,
                        'avr_admitted':measured['underruns']==0 and measured['flash_bytes']<=32768,
                        'mean_decode_budget_percent':measured['mean_decode_wall_cycles']/20,
                        'underruns':measured['underruns'],'flash_bytes':measured['flash_bytes']})
                # Independent demuxer check of raw Ogg audio-packet byte sums.
                for codec in ('opus_audio','opus_voip','vorbis','speex_abr'):
                    if codec in report['ogg_independent_checks']:continue
                    encoded=next((r[codec] for r in data['rates'] if r[codec]['status']=='ok'),None)
                    if encoded is None:continue
                    path=Path(encoded['path']);raw=ogg_accounting(path.read_bytes())
                    cmd=['ffprobe','-v','error','-select_streams','a:0','-show_packets',
                         '-show_entries','packet=size','-of','json',str(path)]
                    packets=json.loads(subprocess.check_output(cmd,text=True))['packets']
                    total=sum(int(p['size']) for p in packets)
                    if total!=raw['audio_packet_bytes']:raise AssertionError('Ogg/ffprobe packet accounting mismatch')
                    report['ogg_independent_checks'][codec]={'stream_sha256':sha(path.read_bytes()),
                        'ogg_audio_bytes':raw['audio_packet_bytes'],'ffprobe_audio_bytes':total,'exact':True,'command':cmd}
                report['cases'].append({'id':key,'rates':rows});done.add(key)
                save(output/'verification.json',report)
                print(key,'AVR points',len(rows),'underruns',sum(r['underruns'] for r in rows),
                      'complete cases',len(done),flush=True)
            if len(done)==len(manifest['cases']) or not watch or (output/'stop').exists():break
            time.sleep(5)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','results','output'):ap.add_argument(name,type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl');ap.add_argument('--watch',action='store_true')
    a=ap.parse_args();run(a.corpus,a.results,a.output,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl,a.watch)
