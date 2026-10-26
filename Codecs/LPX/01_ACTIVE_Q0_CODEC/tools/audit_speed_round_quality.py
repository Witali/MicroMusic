"""Freshly compare complete PCM16/PWM against the frozen decoder outputs.

Zero differences here refer to the old decoder, not to the original WAV:
the lossy codec's existing distortion is retained, rather than measured as zero.
Run through the usual LPX Python environment with native g++ available.
"""
import argparse,hashlib,json
from pathlib import Path
from batch_decoder import BatchSession,ROOT

def sha(data):return hashlib.sha256(data).hexdigest()

def run(current,baseline,manifest,output):
    current,baseline,manifest,output=map(Path,(current,baseline,manifest,output))
    report=json.loads(current.read_text(encoding='utf-8'))
    original=json.loads(baseline.read_text(encoding='utf-8'))['images']
    points={p['stream_sha256']:p for p in json.loads(manifest.read_text(encoding='utf-8'))}
    assert set(points)==set(original)==set(report['images']) and len(points)==91
    assert report['manifest_sha256']==sha(manifest.read_bytes())
    for name in ('Lpx4HybridCore.cpp','Lpx4HybridCore.h','Lpx4Math.h'):
        assert report['source_sha256'][name]==sha((ROOT/'src'/name).read_bytes())
    rows={}
    with BatchSession('batch',v3_features=24) as decoder:
        for key,p in points.items():
            blob=Path(p['path']).read_bytes();assert sha(blob)==key
            pcm=decoder.decode_one_s16(blob,p['samples']);pwm=decoder.decode_one(blob,p['samples'])
            assert pcm is not None and pwm is not None
            pcm_hash=sha(pcm.astype('<i2').tobytes());pwm_hash=sha(pwm.tobytes())
            assert pcm_hash==p['pcm16_sha256'] and pwm_hash==p['pwm_sha256']
            avr=report['images'][key];old=original[key]
            assert avr['pwm_native_exact'] and avr['pwm_sha256']==old['pwm_sha256']==pwm_hash
            assert avr['done'] and not avr['decoder_error']
            assert avr['played']==avr['produced']==avr['input_samples']==p['samples']
            assert avr['underruns']==0 and avr['underruns']<=old['underruns']
            rows[key]={'samples':p['samples'],'pcm16_sha256':pcm_hash,'pwm_sha256':pwm_hash,
                'pcm16_difference_from_frozen_decoder':0,'pwm_difference_from_frozen_decoder':0,
                'avr_underruns':avr['underruns'],'elf_sha256':avr['elf_sha256']}
    result={'unique_streams':len(rows),'samples':sum(x['samples'] for x in rows.values()),
        'comparison':'Fresh complete native PCM16/PWM SHA256 equality to frozen golden outputs; complete active-IRQ AVR PWM equality to the original speed baseline.',
        'scope':'Differences are relative to the frozen decoder output, not the source WAV. Existing codec distortion is unchanged on these streams.',
        'current_report_sha256':sha(current.read_bytes()),'baseline_report_sha256':sha(baseline.read_bytes()),
        'manifest_sha256':sha(manifest.read_bytes()),'source_sha256':report['source_sha256'],
        'physical_hardware_measured':False,'images':rows}
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f"{len(rows)} streams, {result['samples']} samples: exact PCM16/PWM, zero AVR underruns")
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('current',type=Path);p.add_argument('baseline',type=Path)
    p.add_argument('manifest',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.current,a.baseline,a.manifest,a.output)
