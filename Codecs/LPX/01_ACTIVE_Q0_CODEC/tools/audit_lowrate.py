"""Check retained low-rate caps, PCM/error records, source hashes and AVR mapping."""
import argparse,json,math
from pathlib import Path
import numpy as np
import soundfile as sf
from benchmark_standards import file_sha,sha,save
from benchmark_lowrate import STAGES,CONFIG,revision
from standard_metrics import error_metrics,pwm_pcm16
from validate_lowrate_avr import SOURCE


def run(measurements,avr,corpus,baseline_root,output):
    report=json.loads(Path(measurements).read_text(encoding='utf-8'));validation=json.loads(Path(avr).read_text(encoding='utf-8'))
    corpus,baseline_root=Path(corpus),Path(baseline_root)
    if report['revision']!=revision() or report['config']!=CONFIG:raise ValueError('Mixed/future benchmark code or configuration')
    assert len(report['cases'])==27 and len(validation['cases'])==27
    expected={c['id'] for c in json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))['cases']}
    assert expected=={c['id'] for c in report['cases']}=={c['id'] for c in validation['cases']}
    counts={'cases':27,'selected_points':0,'metric_records':0,'unique_streams':0};digests=set();failures=[]
    for c in report['cases']:
        ref,rate=sf.read(corpus/c['id']/'reference.wav',dtype='int16')
        assert rate==8000 and ref.shape==(32000,) and sha(ref.astype('<i2').tobytes())==c['reference_sha256']
        validated=next(v for v in validation['cases'] if v['id']==c['id'])
        assert validated['benchmark_fingerprint']==c['fingerprint']
        for row in c['rates']:
            assert row['cap_audio_bytes']==row['ceiling_bps']//2
            for stage in STAGES:
                r=row[stage]
                if r['status']!='ok':assert r['status']=='no_fit';continue
                path=Path(r['path']);raw=path.read_bytes();pcm,sr=sf.read(path.with_suffix('.wav'),dtype='int16')
                assert sha(raw)==r['stream_sha256'] and len(raw)==r['file_bytes'] and len(raw)-20==r['audio_packet_bytes']<=row['cap_audio_bytes']
                assert sr==8000 and pcm.shape==(32000,) and sha(pcm.astype('<i2').tobytes())==r['pcm16_sha256']
                assert r['native_model_pcm_exact'] and r['native_pwm_exact']
                for phase,signal in [('aligned_pcm16',pcm),('aligned_pwm8',pwm_pcm16(pcm))]:
                    m=error_metrics(ref,signal);stored=r['metrics'][phase]
                    for field,value in m.items():
                        if field!='stoi':assert value==stored[field],(c['id'],stage,phase,field)
                    assert stored['samples']==32000 and 0<=stored['max_abs_error_pcm16']<=65535
                    counts['metric_records']+=1
                old=row['baseline'];m=r['metrics']['aligned_pcm16']
                if stage!='perceptual' and old['status']=='ok':
                    before=old['metrics']['aligned_pcm16'];assert m['error_energy']<=before['error_energy']
                    if before['stoi'] is not None:assert m['stoi']>=before['stoi']-1e-12
                if stage=='perceptual':
                    before=row['joint']['metrics']['aligned_pcm16']
                    assert r['file_bytes']==row['joint']['file_bytes']
                    assert m['error_energy']<=before['error_energy']*10**.3+1e-9
                    assert m['max_abs_error_pcm16']<=max(before['max_abs_error_pcm16']*1.1,before['max_abs_error_pcm16']+256)
                    if before['stoi'] is not None:assert m['stoi']>=before['stoi']-1e-12
                point=next(p for p in validated['points'] if p['stage']==stage and p['ceiling_bps']==row['ceiling_bps'])
                assert point['stream_sha256']==r['stream_sha256'] and point['native_pcm16_exact'] and point['native_pwm_exact'] and point['error_metrics_exact']
                if not point['avr_admitted']:failures.append({'case':c['id'],'stage':stage,'ceiling_bps':row['ceiling_bps'],'underruns':point['underruns']})
                counts['selected_points']+=1;digests.add(r['stream_sha256'])
    assert digests==set(validation['images'])
    for digest,p in validation['images'].items():
        assert p['input_sha256']==digest and p['produced']==p['played']==p['decode_calls']==32000
        assert p['timer_ticks']==32000+p['underruns'] and p['pwm_native_exact']
        for field,path in SOURCE.items():assert p[field]==file_sha(path)
        parent=(Path(avr).parent/digest) if p['measurement_origin'].startswith('new') else baseline_root/'build/lpx-standards/avr'/digest
        for field,suffix in [('elf_sha256','elf'),('hex_sha256','hex')]:assert file_sha(parent/('profile.'+suffix))==p[field]
    # Stronger than matching only three headers: every tracked decoder source
    # and lookup file must still equal the previous experiment's checkout.
    source=Path(__file__).resolve().parents[1]/'src'
    source_hashes={}
    for path in source.iterdir():
        if path.is_file():
            previous=baseline_root/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src'/path.name
            assert file_sha(path)==file_sha(previous);source_hashes[path.name]=file_sha(path)
    counts['unique_streams']=len(digests)
    result={'status':'passed','counts':counts,'non_admitted_points':failures,
        'decoder_source_sha256':source_hashes,'checks':[
        'All 27 full-reference cases, both exact audio/file caps and every stage present.',
        'Every selected stream/WAV hash, sample count and PCM16/PWM error record agrees.',
        'Waveform rollback preserves baseline SSE/STOI; perceptual guards preserve STOI and codeword file lengths.',
        'Every successful point maps to its full active-IRQ AVR image; source and ELF/HEX hashes agree.',
        'Every decoder source/table is byte-identical to the preceding standard-codec experiment.'
        ]}
    save(output,result);return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('measurements','avr','corpus','baseline_root','output'):ap.add_argument(name,type=Path)
    a=ap.parse_args();print(json.dumps(run(a.measurements,a.avr,a.corpus,a.baseline_root,a.output),ensure_ascii=False,indent=2))
