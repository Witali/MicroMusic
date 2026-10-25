#!/usr/bin/env python3
"""Reproducible host experiment, NOT a firmware implementation.
Uses original archived R2 Numba research simulator; retain R2 unmodified.
"""
from pathlib import Path
import sys, csv
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'Codec2_Tiny13_Quality_R2'
sys.path.insert(0,str(BASE/'tests'))
import numpy as np, soundfile as sf
from quality_sweep import prepared, decode, metric
from codec2_test_common import fields
OUTPUT=ROOT/'results'; OUTPUT.mkdir(exist_ok=True)
streams=[('english','speech.c2zx','english_codec2_reference.wav'),('russian','codec2_3200_8byte_frames.bin','russian_codec2_reference.wav')]
variants={
 'R2_model_3':(3,5,2,2,4,1,0,0,0),
 'four_res_equal':(4,5,2,2,4,1,0,0,0),
 'four_res_weighted':(4,5,2,2,4,1,1,0,0),
 'five_res_equal':(5,5,2,2,4,1,0,0,0),
 'five_res_weighted':(5,5,2,2,4,1,1,0,0),
 'five_res_low_weight':(5,5,2,2,4,1,2,0,0),
}
table=np.array([min(62,int(np.floor((64*np.sin(np.pi*100*i/8000))+0.5))) for i in range(36)],dtype=np.int16)
rows=[]
for language,frame_file,reference in streams:
    frames=(BASE/'tests'/frame_file).read_bytes()
    assert len(frames)%8==0
    param=[fields(frames[i:i+8]) for i in range(0,len(frames),8)]
    assert all(len(q[4])==10 for q in param)
    original,_=sf.read(BASE/'audio'/reference)
    states=prepared(frame_file)
    for name,config in variants.items():
        output,overflows=decode(states,*config,table)
        quality=metric(original,output)
        rows.append(dict(language=language,variant=name,stoi=quality[0],spectral_log_error_db=quality[1],spectral_cosine=quality[2],rms=quality[3],wrapped_states=overflows,frames=len(param),samples=len(output)))
        print(language,name,quality,'wraps',overflows,flush=True)
with open(OUTPUT/'comparison.csv','w',newline='') as out:
    w=csv.DictWriter(out,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print('Saved',OUTPUT/'comparison.csv')
