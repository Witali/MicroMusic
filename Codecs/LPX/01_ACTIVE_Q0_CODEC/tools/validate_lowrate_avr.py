"""Validate every completed low-rate ablation as complete active-IRQ AVR ELF."""
import argparse,json,time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save,file_sha,sha
from benchmark_lowrate import STAGES
from profile_avr import run as profile
from q0_model import decode_pcm16
from standard_metrics import pwm_duties,error_metrics

ROOT=Path(__file__).resolve().parents[1]
SOURCE={'core_sha256':ROOT/'src/Lpx4HybridCore.cpp','core_header_sha256':ROOT/'src/Lpx4HybridCore.h',
 'math_header_sha256':ROOT/'src/Lpx4Math.h','harness_sha256':ROOT.parent/'validation/atmega328p/profile.cpp',
 'runner_sha256':ROOT.parent/'validation/atmega328p/sim_profile.c'}


def run(corpus,results,output,baseline_avr,avr_bin,runner,lib=None,wsl=None,watch=False,stages=None):
    stages=tuple(STAGES if stages is None else stages)
    if not stages or len(stages)!=len(set(stages)):raise ValueError('Expected distinct benchmark stages')
    corpus,results,output=map(Path,(corpus,results,output));output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    old=json.loads(Path(baseline_avr).read_text(encoding='utf-8'))
    source_hashes={k:file_sha(p) for k,p in SOURCE.items()}
    try:report=json.loads((output/'verification.json').read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):report={'cases':[],'images':{},'physical_hardware_measured':False,
        'profile':'ATmega328P 16MHz / 8kHz; ASM enabled; queue512/prefill384/unroll9; v3 mask24',
        'source_sha256':source_hashes,'expected_cases':len(manifest['cases'])}
    if report['source_sha256']!=source_hashes:raise ValueError('AVR source changed since previous measurement')
    if tuple(report.get('stages',STAGES))!=stages and report['cases']:raise ValueError('AVR benchmark stages changed')
    report['stages']=list(stages)
    done={r['id']:r['benchmark_fingerprint'] for r in report['cases']}
    with BatchSession('batch',v3_features=24) as decoder:
        while True:
            for case in manifest['cases']:
                key=case['id'];path=results/key/'complete.json'
                try:data=json.loads(path.read_text(encoding='utf-8'))
                except (FileNotFoundError,json.JSONDecodeError):continue
                if done.get(key)==data['fingerprint']:continue
                ref,rate=sf.read(corpus/key/'reference.wav',dtype='int16')
                if rate!=8000 or ref.shape!=(32000,) or sha(ref.astype('<i2').tobytes())!=case['reference_sha256']:raise ValueError('Reference changed')
                points=[]
                for row in data['rates']:
                    for stage in stages:
                        item=row[stage]
                        if item['status']!='ok':continue
                        blob=Path(item['path']).read_bytes();digest=sha(blob)
                        if digest!=item['stream_sha256'] or len(blob)-20>row['cap_audio_bytes']:raise ValueError('Stream or cap changed')
                        native=decoder.decode_one_s16(blob,32000);pwm=decoder.decode_one(blob,32000)
                        if native is None or sha(native.astype('<i2').tobytes())!=item['pcm16_sha256']:raise AssertionError('Native PCM changed')
                        if not np.array_equal(pwm,pwm_duties(native)):raise AssertionError('Common/native PWM mismatch')
                        m=error_metrics(ref,native)
                        for field in ('error_energy','max_abs_error_pcm16','max_error_sample'):
                            if m[field]!=item['metrics']['aligned_pcm16'][field]:raise AssertionError('Error metric mismatch')
                        if digest not in report['images']:
                            if not np.array_equal(native,decode_pcm16(blob)):raise AssertionError('Independent Q0 model mismatch')
                            measured=old['images'].get(digest)
                            reuse=measured and all(measured.get(k)==v for k,v in source_hashes.items()) and all(measured.get(k)==v for k,v in
                                {'queue_bytes':512,'prefill_samples':384,'dot_unroll':9,'v3_compiled_features':24,'extra_irq_cycles':0}.items())
                            if reuse:measured={**measured,'measurement_origin':'retained byte-identical baseline ELF'}
                            else:
                                measured=profile(Path(item['path']),output/digest,avr_bin,runner,lib,wsl,enable_asm=True,v3_features=24)
                                measured['measurement_origin']='new complete low-rate ELF'
                            report['images'][digest]=measured;save(output/'verification.json',report)
                        measured=report['images'][digest]
                        points.append({'ceiling_bps':row['ceiling_bps'],'stage':stage,'stream_sha256':digest,
                            'native_pcm16_exact':True,'native_pwm_exact':True,'error_metrics_exact':True,
                            'avr_admitted':not measured['underruns'] and measured['flash_bytes']<=32768,
                            'mean_decode_budget_percent':measured['mean_decode_wall_cycles']/20,
                            'underruns':measured['underruns'],'flash_bytes':measured['flash_bytes']})
                record={'id':key,'benchmark_fingerprint':data['fingerprint'],'points':points}
                report['cases']=[c for c in report['cases'] if c['id']!=key]+[record];done[key]=data['fingerprint']
                save(output/'verification.json',report)
                print(key,'AVR complete',len(points),'points,',sum(p['underruns'] for p in points),'underruns;',len(done),'cases;',len(report['images']),'images',flush=True)
            if len(done)==len(manifest['cases']) or not watch or (output/'stop').exists():break
            time.sleep(5)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','results','output','baseline_avr'):ap.add_argument(name,type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl');ap.add_argument('--watch',action='store_true')
    ap.add_argument('--stages',nargs='+',help='Selected benchmark stages; defaults to the original four ablations')
    a=ap.parse_args();run(a.corpus,a.results,a.output,a.baseline_avr,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl,a.watch,a.stages)
