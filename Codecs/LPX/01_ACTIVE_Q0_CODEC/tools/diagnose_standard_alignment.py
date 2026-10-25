#!/usr/bin/env python3
"""Exploratory delay sensitivity; never replaces full-reference primary metrics.

Fit only a fractional time shift by correlation, without gain fitting. The
guard is common to every codec. Also verify any raw-PCM timestamp warning
against a fresh decode with explicitly monotonic output timestamps.
"""
import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from benchmark_standards import save,sha
from summarize_standards import AGG_CODECS,cbr_under


def run(report_path,corpus,results,output):
    report=json.loads(Path(report_path).read_text(encoding='utf-8'))
    result={'method':'Exploratory correlation fit at 1/16 sample over +/-8 samples around integer alignment; '
            'Kaiser8.6 polyphase interpolation; 160-sample guard on each edge; no gain fit. '
            'Primary full-reference SER/max-error records are unchanged.',
            'guard_samples_per_edge':160,'cases':[]}
    for case in report['cases']:
        if case['group'] not in ('clean','acoustic_music'):continue
        name=case['id'];ref=sf.read(Path(corpus)/name/'reference.wav',dtype='int16')[0].astype(float)
        row=next(r for r in case['rates'] if r['ceiling_bps']==24000);items={}
        row={**row,'speex_cbr_under':cbr_under(case,row['cap_audio_bytes'])}
        for codec in AGG_CODECS:
            item=row[codec]
            if item['status']!='ok':continue
            warnings='';timestamp_check=None
            if codec=='LPX':
                y=sf.read(Path(results)/name/'24000/decoded.wav',dtype='int16')[0]
                if sha(y.astype('<i2').tobytes())!=item['pcm16_sha256']:raise AssertionError('LPX PCM changed')
            else:
                cmd=['ffmpeg','-nostdin','-v','error','-i',item['path'],'-ac','1','-ar','8000','-f','s16le','pipe:1']
                decoded=subprocess.run(cmd,check=True,capture_output=True)
                y=np.frombuffer(decoded.stdout,dtype='<i2');warnings=decoded.stderr.decode(errors='replace')
                lag=item['metrics']['delay_samples'];aligned=y[lag:lag+len(ref)]
                if sha(aligned.astype('<i2').tobytes())!=item['aligned_pcm16_sha256']:raise AssertionError('Standard PCM changed')
                if 'non monotonically increasing dts' in warnings:
                    clean_cmd=['ffmpeg','-nostdin','-v','error','-i',item['path'],'-ac','1',
                        '-af','aresample=8000,asetpts=N/SR/TB','-ar','8000','-f','s16le','pipe:1']
                    clean=subprocess.run(clean_cmd,check=True,capture_output=True)
                    timestamp_check={'raw_sha256':sha(decoded.stdout),'monotonic_sha256':sha(clean.stdout),
                        'pcm_exact':decoded.stdout==clean.stdout,'command':clean_cmd,
                        'monotonic_warnings':clean.stderr.decode(errors='replace')}
                    if not timestamp_check['pcm_exact']:raise AssertionError('Timestamp normalization changed PCM')
            y=y.astype(float);lag=item['metrics']['delay_samples'];guard=160;x=ref[guard:-guard]
            up=resample_poly(y,16,1,window=('kaiser',8.6));indices=(np.arange(guard,len(ref)-guard)+lag)*16
            offsets=np.arange(-128,129)
            scores=[np.dot(x,up[indices+offset]) for offset in offsets]
            offset=int(offsets[np.argmax(scores)])
            def ser(z):
                power=float(np.dot(x,x));error=float(np.dot(x-z,x-z))
                return 10*np.log10(power/error) if power and error else None
            baseline=ser(y[guard+lag:len(ref)-guard+lag]);fitted=ser(up[indices+offset])
            items[codec]={'integer_delay_samples':lag,'extra_shift_samples':offset/16,
                'guarded_integer_ser_db':baseline,'guarded_fractional_ser_db':fitted,
                'ser_change_db':fitted-baseline if fitted is not None and baseline is not None else None,
                'redecoded_aligned_pcm_exact':True,'decoder_warnings':warnings,
                'timestamp_normalization_check':timestamp_check}
        result['cases'].append({'id':name,'codecs':items})
        save(output,result);print(name,'alignment diagnostic complete',flush=True)
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('report','corpus','results','output'):ap.add_argument(name,type=Path)
    a=ap.parse_args();run(a.report,a.corpus,a.results,a.output)
