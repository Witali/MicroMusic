#!/usr/bin/env python3
"""Create three aligned listening comparisons: original, Xiph WB, compact WB."""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import wave
ROOT=Path(__file__).resolve().parents[1]
EXE='decode.exe' if sys.platform=='win32' else 'decode'
def samples_from_le(data):
    samples=array.array('h',data)
    if sys.byteorder!='little':samples.byteswap()
    return samples
def read_pcm(path):return samples_from_le(path.read_bytes())
def write_wave(path,samples):
    samples=array.array('h',samples)
    if sys.byteorder!='little':samples.byteswap()
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(samples.tobytes())
def delay(original,decoded):
    def score(lag,stride):
        n=min(len(original),len(decoded)-lag);a=b=c=0
        for i in range(0,n,stride):
            x,y=original[i],decoded[i+lag];a+=x*y;b+=x*x;c+=y*y
        return a/math.sqrt(b*c) if b*c else 0
    coarse=max(range(0,769,4),key=lambda lag:score(lag,8))
    return max(range(max(0,coarse-4),coarse+5),key=lambda lag:score(lag,1))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips',type=Path,default=ROOT/'build/real-speech/clips')
    p.add_argument('--out',type=Path,default=ROOT/'build/wb-listening')
    p.add_argument('--full-reference',type=Path,default=ROOT/'build/rates-reference'/EXE)
    p.add_argument('--compact-reference',type=Path,default=ROOT/'build/wb-reference'/EXE)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True);rows=[]
    selected=['ru_pushkin_a','en_letter_a','ru_slutskaya_a']
    for name in selected:
        clip=args.clips/name/'16000';packet=clip/'encoded.spxraw'
        for label,exe in [('full',args.full_reference),('compact',args.compact_reference)]:
            subprocess.run([str(exe),'1','25',str(packet),str(args.out/(name+'-'+label+'.pcm'))],check=True)
        with wave.open(str(clip/'input.wav'),'rb') as f:
            assert f.getparams()[:3]==(1,2,16000);original=samples_from_le(f.readframes(f.getnframes()))
        full=read_pcm(args.out/(name+'-full.pcm'));compact=read_pcm(args.out/(name+'-compact.pcm'))
        full_delay=delay(original,full);compact_delay=full_delay-24
        assert compact_delay>=0
        n=min(len(original),len(full)-full_delay,len(compact)-compact_delay)
        a,b=full[full_delay:full_delay+n],compact[compact_delay:compact_delay+n]
        error=sum((x-y)**2 for x,y in zip(a,b));energy=sum(x*x for x in a)
        for label,pcm in [('original',original[:n]),('full',a),('compact',b)]:write_wave(args.out/(name+'-'+label+'.wav'),pcm)
        rows.append(dict(clip=name,samples=n,fullDelaySamples=full_delay,compactDelaySamples=compact_delay,
            snrCompactVsFullDb=10*math.log10(energy/error),peakCompact=max(map(abs,b)),
            clippedCompact=sum(abs(v)==32767 for v in b),packetSha256=hashlib.sha256(packet.read_bytes()).hexdigest()))
    report=dict(sampleRate=16000,bitrate=9800,filter='normalized 16-tap Q7 QMF',
        comparison='Waveform SNR versus full 64-tap Xiph synthesis; not a perceptual quality score',
        physicalBoardRecorded=False,streams=rows)
    (args.out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    html='''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Speex WB — сравнение</title>
<style>body{font:17px system-ui;max-width:1000px;margin:40px auto;padding:0 20px;background:#f4f6f8;color:#15252c}table{width:100%;border-collapse:collapse}th,td{padding:16px;text-align:left;border-bottom:1px solid #ccd5d9}audio{width:260px}small{color:#456}</style>
<h1>Speex WB: 16 кГц · 9,8 кбит/с</h1><p>Записи выровнены по задержке, усиление не менялось. AVR-профиль использует компактный фильтр синтеза. Звук получен программным декодированием; физическая плата не записывалась.</p><table><tr><th>Образец</th><th>Оригинал</th><th>Полный Speex WB</th><th>Компактный AVR WB</th></tr>'''
    for name in selected:
        html+='<tr><th>'+name+'</th>'+''.join('<td><audio controls preload="none" src="'+name+'-'+label+'.wav"></audio></td>' for label in ['original','full','compact'])+'</tr>'
    (args.out/'index.html').write_text(html+'</table></html>',encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
