#!/usr/bin/env python3
"""Compare original LPX3 Float32 with actual L3AV UInt8 decode against same mono WAV.

Example:
  node tools/decode_original_lpx3.js voice_3bit.lpx3 old.f32
  build/decode_host voice.l3av new.pcm8
  python tests/evaluate_quality.py original.wav old.f32 new.pcm8
"""
from pathlib import Path
import argparse,json,wave
import numpy as np
from pystoi import stoi
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source_wav',type=Path);p.add_argument('old_lpx3_pcm_f32',type=Path)
p.add_argument('new_l3av_pcm8',type=Path);p.add_argument('--json',type=Path)
a=p.parse_args()
with wave.open(str(a.source_wav)) as w:
 if w.getframerate()!=8000 or w.getnchannels()!=1 or w.getsampwidth()!=2:
  p.error('reference must be 8kHz mono signed PCM16 WAV')
 ref=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768.
old=np.frombuffer(a.old_lpx3_pcm_f32.read_bytes(),dtype='<f4').astype(float)
new=(np.frombuffer(a.new_l3av_pcm8.read_bytes(),dtype=np.uint8).astype(float)-128)/127.
if not(len(ref)==len(old)==len(new)):p.error('reference and both decodes must be sample-aligned')
o=float(stoi(ref,old,8000));n=float(stoi(ref,new,8000))
report={'old_stoi':o,'new_stoi':n,'delta':n-o,'rms_against_old':float(np.sqrt(np.mean((old-new)**2))),'samples':len(ref)}
print(json.dumps(report,indent=2))
if a.json:a.json.write_text(json.dumps(report,indent=2)+'\n')
