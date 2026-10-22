#!/usr/bin/env python3
"""Closed-loop LPC-8 retuning on a selected voice recording.
Runs the same cycle-exact math model as the actual AVR decoder. A candidate is
accepted only if intelligibility/spectral fidelity do not regress and no new
large sample discontinuities appear. After acceptance, rebuild and AVR-verify.
"""
from pathlib import Path
import sys,subprocess,shutil,argparse,json
import numpy as np
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P/'tools'))
from model8 import render
from perceptual import Evaluator,load_wav

def metrics(clip,path):
 z=np.load(path)
 samples=render(z['K'],z['P'],z['E'],len(z['P'])*256)
 ev=Evaluator(load_wav(P/clip/'original.wav'),load_wav(P/clip/'lpc2_voice_v2.wav'))
 return ev.metrics(samples)

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--clip',choices=['xtuj-ntt','ne-otv'],required=True)
 ap.add_argument('--budget',type=int,default=1400)
 ap.add_argument('--seed',type=int,default=2026)
 args=ap.parse_args()
 clip=args.clip; fw=P/clip/'firmware';current=fw/'best_parameters.npz'
 out=P/clip/'retune';out.mkdir(exist_ok=True)
 baseline=metrics(clip,current)
 subprocess.run([sys.executable,str(P/'tools/optimize8.py'),'--source',str(P/clip/'original.wav'),
  '--teacher',str(P/clip/'lpc2_voice_v2.wav'),'--seed-params',str(current),
  '--budget',str(args.budget),'--seed',str(args.seed),'--target','balanced',
  '--output-dir',str(out)],check=True,cwd=P)
 trial=out/'optimized_parameters.npz';candidate=metrics(clip,trial)
 def score(m):return 3*m['stoi']-.9*m['mel_original']-.2*m['mel_lpc2']-.001*m['max_step']
 checks=(candidate['clicks_48']<=baseline['clicks_48'] and
         candidate['clicks_60']<=baseline['clicks_60'] and
         candidate['max_step']<=baseline['max_step'] and
         candidate['stoi']>=baseline['stoi']-.003 and
         candidate['mel_original']<=baseline['mel_original']+.003)
 accept=bool(checks and score(candidate)>score(baseline)+1e-5)
 if accept:
  shutil.copy2(current,fw/'parameters_previous.npz')
  shutil.copy2(trial,current)
  subprocess.run([sys.executable,str(P/'rebuild_all.py'),'--clip',clip],cwd=P,check=True)
  import soundfile as sf
  pcm=np.fromfile(fw/'emu_pwm_u8.raw',dtype='u1').astype('int16')-128
  sf.write(P/clip/'attiny13.wav',pcm.astype('float64')/128,7500,subtype='PCM_16')
  state=json.loads((P/clip/'report.json').read_text())
  state.update({'selected':'automatic follow-up: LPC2 Voice v2 closed loop','metrics':candidate,
                'flash_bytes':(fw/'tinylpc.bin').stat().st_size,'voice_bytes':(fw/'voice_tinylpc.bin').stat().st_size})
  (P/clip/'report.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
  subprocess.run([sys.executable,str(P/'make_previews.py')],cwd=P,check=True)
  subprocess.run([sys.executable,str(P/'make_test_page.py')],cwd=P,check=True)
  print('Accepted: better score with safe click/intelligibility guards')
 else: print('Rejected: keeping the previously verified firmware')
 report={'clip':clip,'accepted':accept,'baseline':baseline,'candidate':candidate}
 (out/'selection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
