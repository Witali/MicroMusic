"""Check real AVR emulator's PCM against Numba byte-exact model and collect metrics."""
import json,sys,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from model_keyframes import render
from perceptual import Evaluator,load_wav
for clip in ['xtuj-ntt','ne-otv']:
 p=ROOT/clip; src=ROOT/'datasets'/clip
 z=np.load(p/'trained_parameters.npz')
 actual=np.fromfile(p/'emu_pwm_u8.raw',dtype=np.uint8).astype(np.int16)-128
 model=render(z['K'],z['P'],z['E'],z['mask'],len(actual),4,4)
 mismatch=np.flatnonzero(actual!=model)
 ev=Evaluator(load_wav(src/'original.wav'),load_wav(src/'lpx3_voice.wav'))
 m=ev.metrics(actual)
 rep=json.loads((p/'report.json').read_text());rep['verified_AVR']={'samples':len(actual),'mismatches':len(mismatch),'metrics':m,'flash':len((p/'tinylpc.bin').read_bytes())}
 (p/'report.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2))
 print(clip,'PCM match?',len(mismatch)==0,'count',len(actual),'flash',rep['verified_AVR']['flash'],'STOI',m['stoi'],'mel',m['mel_original'])
