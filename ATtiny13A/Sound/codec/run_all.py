#!/usr/bin/env python3
"""MicroMusic: one-command assembly, cycle-accurate verification, STOI report and test page.

Uses frozen optimized frames in samples/*/trained.npz by default. No training is
silently run: supply --optimize to do an additional closed-loop search, then
save and verify new frames. Reproducibility of the *released* HEX is guaranteed
by the included frames; newly randomized searches may find different optima.

To prepare source MP3, first run convert_audio.py. The canonical reference WAVs
in references/*/original.wav are the exact signals used for reported scores.
"""
import argparse, json, subprocess, csv, hashlib
from pathlib import Path
import soundfile as sf
import numpy as np
from quality import Compare
ROOT=Path(__file__).resolve().parent
NAMES=['chego','otvechaesh','vinni']

def run(cmd):
    print('+',' '.join(map(str,cmd)),flush=True)
    subprocess.run(cmd,check=True,cwd=ROOT)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--optimize',action='store_true',help='Run additional coordinate search; modifies trained.npz')
    p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--skip-browser',action='store_true')
    args=p.parse_args()
    if args.optimize:
        for name in NAMES:run(['python','refine_hq.py','--voice',name,'--seconds',str(args.seconds)])
    run(['python','build_hq.py'])
    run(['node','verify.js'])
    manifest=json.loads((ROOT/'manifest.json').read_text())
    verification=json.loads((ROOT/'verification.json').read_text())
    rows=[]
    for name in NAMES:
        ref,sr=sf.read(ROOT/'references'/name/'original.wav');assert sr==7500
        y=np.frombuffer((ROOT/'samples'/name/'avr_pcm.raw').read_bytes(),dtype=np.uint8)
        stoi,spectral,clicks=Compare(ref).scores(y)
        row={'phrase':name,'stoi':round(stoi,7),'spectral_error':round(spectral,5),
             'clicks_48':int(clicks),'flash_bytes':manifest[name]['flash_bytes'],
             'code_bytes':manifest[name]['code_bytes'],
             'speech_bytes':manifest[name]['speech_bytes'],
             'pcm_samples':len(y),'avr_differences':verification[name]['differences'],
             'timer_misses':verification[name]['missedTimer'],
             'late_audio':verification[name]['lateAudio'],
             'flash_sha256':manifest[name]['sha256']}
        rows.append(row)
        assert row['flash_bytes']<=1024 and row['avr_differences']==0
        assert not row['timer_misses'] and not row['late_audio']
        sf.write(ROOT/'samples'/name/'avr_preview.wav',(y.astype('float64')-128)/128,sr,subtype='PCM_16')
        print(name,'STOI',row['stoi'],'Flash',row['flash_bytes'],'B',flush=True)
    (ROOT/'report.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False))
    with (ROOT/'report.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    if not args.skip_browser:run(['python','make_player.py'])
    print('Reports: report.json / report.csv; HEX and WAV under samples/<phrase>/',flush=True)
if __name__=='__main__':main()
