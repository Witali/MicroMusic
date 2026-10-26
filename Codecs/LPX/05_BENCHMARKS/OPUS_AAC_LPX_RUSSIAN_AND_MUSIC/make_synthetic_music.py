"""Generate ORIGINAL 24-second diagnostic music. Not a real instrument recording."""
import numpy as np, soundfile as sf
from pathlib import Path
R=8000; DUR=24
n=R*DUR; t=np.arange(n)/R
rng=np.random.default_rng(250)
y=np.zeros(n)
# repeated 8-bar original tune, approximating a piano, bass and string arrangement
melody=[(69,0.0,0.4),(72,.5,.4),(74,1.0,.4),(76,1.5,.6),(74,2.25,.25),(72,2.75,.3),(69,3.25,.5),
        (67,4.0,.4),(69,4.5,.4),(72,5.0,.4),(74,5.5,.7),(76,6.5,.4),(74,7.0,.4),
        (72,7.5,.3),(69,8.0,.8)]
chords=[(48,52,55,60),(45,48,52,57),(50,53,57,62),(43,47,50,55)]
for bar in range(6):
 start=bar*4.0
 chord=chords[bar%4]
 for pitch in chord:
  f=440*2**((pitch-69)/12)
  idx=np.arange(int(3.75*R)); env=np.exp(-idx/(R*2.5))*(1-np.exp(-idx/(R*.012)))
  tone=(.7*np.sin(2*np.pi*f*idx/R)+.2*np.sin(2*np.pi*f*2*idx/R)+.08*np.sin(2*np.pi*f*3*idx/R))*env
  a=int(start*R);b=min(n,a+len(tone)); y[a:b]+=0.035*tone[:b-a]
 for pitch,offset,length in melody:
  if offset>=4:continue
  f=440*2**((pitch-69)/12)
  a=int((start+offset)*R); sz=int(length*R)
  if a+sz>n:continue
  tt=np.arange(sz)/R
  env=np.sin(np.pi*np.minimum(1,tt/length))**.5
  tone=(.65*np.sin(2*np.pi*f*tt)+.25*np.sin(4*np.pi*f*tt)+.10*np.sin(6*np.pi*f*tt))*env
  y[a:a+sz]+=0.12*tone
 # bass plucks
 for beat in range(4):
  p=chord[0]-12;f=440*2**((p-69)/12)
  a=int((start+beat)*R);sz=R
  tt=np.arange(sz)/R; env=np.exp(-tt*3)
  y[a:a+sz]+=0.08*env*np.sin(2*np.pi*f*tt)
 # brushed hats plus kick, synthetic noise
 for eighth in range(8):
  a=int((start+.5*eighth)*R)
  h=rng.normal(0,1,int(.045*R));h=np.diff(np.r_[0,h]);
  env=np.exp(-np.arange(len(h))/(R*.01))
  y[a:a+len(h)] += .008*h*env
 for beat in [0,2]:
  a=int((start+beat)*R); ts=np.arange(int(.11*R))/R
  kick=np.sin(2*np.pi*(110*ts-85*ts*ts))*np.exp(-ts*30)
  y[a:a+len(ts)]+=.035*kick
# modest master limit without different per-codec postprocessing
y=.9*y/max(1, np.max(abs(y))*1.06)
output=Path(__file__).parent/'sources'/'original_synth_music_24s_8k.wav'
output.parent.mkdir(exist_ok=True)
sf.write(output,y,R,subtype='PCM_16')
print(output,output.stat().st_size)
