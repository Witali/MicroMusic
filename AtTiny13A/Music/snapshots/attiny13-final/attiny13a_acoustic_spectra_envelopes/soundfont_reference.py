#!/usr/bin/env python3
"""Render reference instrument notes from *sample-based* General MIDI SoundFont.

This is a local comparative proxy, NOT raw University of Iowa recordings.
Run: python soundfont_reference.py
"""
import ctypes as C, json, os
from pathlib import Path
import numpy as np
from scipy.io import wavfile
ROOT=Path(__file__).resolve().parent
LIB=C.CDLL('libfluidsynth.so.3')
def proto(name,ret,args):
 f=getattr(LIB,name);f.restype=ret;f.argtypes=args;return f
P=C.c_void_p;I=C.c_int;F=C.c_float;D=C.c_double;S=C.c_char_p
new_settings=proto('new_fluid_settings',P,[])
setting_num=proto('fluid_settings_setnum',I,[P,S,D])
setting_int=proto('fluid_settings_setint',I,[P,S,I])
new_synth=proto('new_fluid_synth',P,[P])
sfload=proto('fluid_synth_sfload',I,[P,S,I])
program=proto('fluid_synth_program_change',I,[P,I,I])
all_sounds_off=proto('fluid_synth_all_sounds_off',I,[P,I])
noteon=proto('fluid_synth_noteon',I,[P,I,I,I])
noteoff=proto('fluid_synth_noteoff',I,[P,I,I])
write=proto('fluid_synth_write_s16',I,[P,I,P,I,I,P,I,I])
delete_synth=proto('delete_fluid_synth',None,[P])
delete_settings=proto('delete_fluid_settings',None,[P])
fs=37500
settings=new_settings();setting_num(settings,b'synth.sample-rate',fs);setting_num(settings,b'synth.gain',0.9)
setting_int(settings,b'synth.reverb.active',0)
setting_int(settings,b'synth.chorus.active',0)
synth=new_synth(settings)
sfpath=os.environ.get('SOUNDFONT_PATH','/usr/share/sounds/sf2/TimGM6mb.sf2').encode();sfid=sfload(synth,sfpath,1)
if sfid<0:raise RuntimeError('Cannot load local TimGM6mb.sf2')
# GM 0-based: Acoustic Grand 0, Nylon Guitar 24, Violin 40
spec={'piano':{'program':0,'notes':[48,62,81]},'guitar':{'program':24,'notes':[43,62,69]},'violin':{'program':40,'notes':[55,62,69,74]}}
def render(block):
 l=(C.c_int16*block)();r=(C.c_int16*block)()
 write(synth,block,C.cast(l,P),0,1,C.cast(r,P),0,1)
 return (np.asarray(l,dtype=np.float32)+np.asarray(r,dtype=np.float32))/(2*32768)
for ins,det in spec.items():
 for note in det['notes']:
  all_sounds_off(synth,0);program(synth,0,det['program']);noteon(synth,0,note,110)
  # attack and first 650ms of note, then release 250ms
  a=render(int(fs*0.65));noteoff(synth,0,note);a=np.r_[a,render(int(fs*0.25))]
  wavfile.write(ROOT/f'reference_{ins}_{note}.wav',fs,np.int16(np.clip(a,-1,1)*32767))
print(json.dumps(spec));delete_synth(synth);delete_settings(settings)
