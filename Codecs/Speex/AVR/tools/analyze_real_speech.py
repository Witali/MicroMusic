#!/usr/bin/env python3
"""Create aligned listening files and objective speech comparisons.

Requires the pinned NumPy/SciPy/pystoi versions in requirements-quality.txt.
Run the full player, AVR capture and native-rate comparisons first. No gain
normalization is applied. STOI is an estimate, not a listening test or MOS.
"""
import argparse
import html
import json
from pathlib import Path
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
DEPS=ROOT/'build/analysis-deps'
if DEPS.exists(): sys.path.insert(0,str(DEPS))
import numpy as np
from scipy.signal import correlate, correlation_lags
from pystoi import stoi

OUT=ROOT/'build/real-speech'

def read_wav(path):
    with wave.open(str(path),'rb') as w:
        assert w.getnchannels()==1 and w.getsampwidth()==2
        rate=w.getframerate()
        return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float64),rate

def write_wav(path,data,rate):
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(np.asarray(data,dtype='<i2').tobytes())

def compare(clean,decoded,rate):
    c=correlate(decoded,clean,method='fft')
    lags=correlation_lags(len(decoded),len(clean))
    valid=(lags>=0)&(lags<=round(.06*rate))
    lag=int(lags[valid][np.argmax(c[valid])])
    size=min(len(clean),len(decoded)-lag)
    x=clean[:size]; y=decoded[lag:lag+size]
    error=np.sum((x-y)**2)
    return {'delaySamples':lag,'delayMs':round(lag/rate*1000,3),'comparedSamples':size,
            'stoi':round(float(stoi(x/32768,y/32768,rate)),4),
            'waveformSnrDb':round(float(10*np.log10(np.sum(x*x)/max(error,1))),3),
            'correlation':round(float(np.corrcoef(x,y)[0,1]),4),
            'rmsInputDbfs':round(float(20*np.log10(max(np.sqrt(np.mean(x*x)),1e-12)/32768)),3)},y

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rates',action='store_true',help='Include completed PC WB/UWB experiments')
    args=parser.parse_args()
    manifest=json.loads((OUT/'corpus.json').read_text(encoding='utf-8'))
    rows=[]; cards=[]
    for clip in manifest['clips']:
        folder=OUT/'clips'/clip['id']
        clean,rate=read_wav(folder/'input.wav')
        raw=np.fromfile(OUT/'avr'/(clip['id']+'.pcm'),dtype='<i2').astype(np.float64)
        pwm=(np.fromfile(OUT/'player'/(clip['id']+'.u8'),dtype='u1').astype(np.float64)-128)*256
        assert np.array_equal(((raw.astype(np.int32)>>8)^128).astype('u1'),
                              np.fromfile(OUT/'player'/(clip['id']+'.u8'),dtype='u1'))
        row={'clip':clip['id'],'language':clip['language'],'condition':clip['condition']}
        for label,decoded in [('avrS16',raw),('avrPwm8',pwm)]:
            row[label],aligned=compare(clean,decoded,rate)
            write_wav(folder/('decoded-s16.wav' if label=='avrS16' else 'decoded-pwm.wav'),aligned,rate)
        if args.rates and clip['condition']=='natural':
            for rate in (16000,32000):
                native_clean,_=read_wav(folder/str(rate)/'input.wav')
                decoded,_=read_wav(folder/str(rate)/'decoded.wav')
                row[str(rate)],aligned=compare(native_clean,decoded,rate)
                write_wav(folder/str(rate)/'aligned.wav',aligned,rate)
        rows.append(row)
        src=next(s for s in manifest['sources'] if s['id']==clip['source'])
        card=f'<section><h2>{html.escape(clip["id"])}</h2><p>{html.escape(clip["speaker"])} · {html.escape(clip["condition"])} · <a href="{src["page"]}">source/credits</a> · {html.escape(src["license"])}</p>'
        files=[('Original excerpt','original.wav'),('8-kHz encoder input','input.wav'),
               ('AVR decoded s16','decoded-s16.wav'),('AVR PWM 8-bit','decoded-pwm.wav')]
        if args.rates and clip['condition']=='natural': files += [('16 kHz — PC experiment','16000/aligned.wav'),('32 kHz — PC experiment','32000/aligned.wav')]
        for label,name in files:
            card+=f'<label>{label}<audio controls preload="none" src="clips/{clip["id"]}/{name}"></audio></label>'
        cards.append(card+'</section>')
    player=json.loads((OUT/'player/player-all.json').read_text())
    avr=json.loads((OUT/'avr/avr-verification.json').read_text())
    summary={'clips':len(rows),'speakers':len(manifest['sources']),'seconds':sum(c['seconds'] for c in manifest['clips']),
             'frames':player['frames'],'samples':player['samples'],'underruns':sum(r['underruns'] for r in player['streams']),
             'minQueuedSamplesBeforeOutput':min(r['minQueuedSamplesBeforeOutput'] for r in player['streams']),
             'maxBlockReadyGapCycles':max(r['maxBlockReadyGapCycles'] for r in player['streams']),
             'maxDecoderFrameCycles':avr['maxCycles'],'freeSramAtPeak':player['freeSramAtPeak'],
             'timerIntervalMinCycles':min(r['timerIntervalMinCycles'] for r in player['streams']),
             'timerIntervalMaxCycles':max(r['timerIntervalMaxCycles'] for r in player['streams']),
             'physicalBoardTested':False}
    groups={}
    for condition in ('natural','quiet_minus24dB','white_noise_15dB'):
        selected=[r for r in rows if r['condition']==condition]
        groups[condition]={}
        for label in ('avrS16','avrPwm8'):
            values=[r[label]['stoi'] for r in selected]
            groups[condition][label]={'stoiMean':round(float(np.mean(values)),4),'stoiMin':min(values),'stoiMax':max(values)}
    report={'method':'Cross-correlation delay alignment (0..60ms), no gain normalization; compare each native-rate input with decoded result. STOI is an intelligibility estimate, not MOS; waveform SNR is descriptive for a speech vocoder. PWM files are captured digital duties, without analog reconstruction/hardware noise.',
            'summary':summary,'groups':groups,'clips':rows}
    (OUT/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Speex speech comparison</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;background:#eef2f6;color:#142237}section{background:white;border-radius:12px;padding:20px;margin:20px 0}label{display:inline-flex;flex-direction:column;margin:8px}audio{width:310px}p{line-height:1.5}</style><h1>Speex: 20 real speech excerpts</h1><p>8 kHz: AVR machine-code simulation, including timers and PWM interrupts. 16/32 kHz: PC memory experiment, not AVR playback. All clips are delay aligned; no level normalization. Digital PWM capture excludes the analog circuit. See <a href="ATTRIBUTION.md">full source credits</a> and <a href="comparison.json">measurements</a>.</p>'+''.join(cards),encoding='utf-8')
    print(json.dumps({'summary':summary,'groups':groups},indent=2))

if __name__=='__main__': main()
