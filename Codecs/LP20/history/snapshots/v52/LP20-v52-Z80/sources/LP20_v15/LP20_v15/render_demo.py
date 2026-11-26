#!/usr/bin/env python3
"""Render the scheduled PWM patterns and measure the same filtered metrics as v13."""
import sys,json,math
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
from build_16k import lut10
import encode as e
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent.parent/'demo'
d=np.load(root/'training.npz');m=json.loads((root/'decoder.json').read_text());y=d['y'];w=lut10(d['ww10'])[y+512];p=m['period'];v,inv=np.unique(w,return_inverse=True);widths=np.array([m['patterns'][str(int(k))] for k in v],dtype=np.int16)[inv].ravel();bw=p//4;g=math.gcd(48000*bw,20000000);z=(np.clip(widths[:,None]-np.arange(4)*bw,0,bw).astype(np.float32)*2/bw-1).ravel();z=e.lp(resample_poly(z,48000*bw//g,20000000//g),7000)/.875*128/127
r=resample_poly(d['target']/127,768,125);q=e.align_metric(e.lp(r,3500),e.lp(z,3500));gain=.98/max(abs(r));e.wav(root/'pwm.wav',z*gain*min(1,.98/(max(abs(z))*gain)));print(json.dumps(q,indent=2))
