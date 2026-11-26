"""Recreate listening WAVs from integer decoder output, no clipping.
Common gain follows normalized reference; if reconstructed peak would exceed
98%, reduce gain slightly (linear gain only, not a limiter on output).
"""
from experiment import *
import hashlib

def previews(npz,folder):
 d=np.load(npz);t,y=d['target'],d['y'];e.FS=FS;e.PERIOD=128;e.PULSES=20;e.LEVELS=77
 ref=resample_poly(t/127,768,125);g=.98/max(abs(ref));ref*=g;pcm=resample_poly(y/127,768,125)*g;pwm=e.render(y)/(2*38/128)*g*128/127
 out={}
 for name,x in [('reference',ref),('pcm',pcm),('pwm',pwm)]:
  adj=min(1.,.98/max(abs(x)));x*=adj;e.wav(folder/(name+'.wav'),x);out[name]=dict(peak=float(max(abs(x))),rms_dbfs=float(20*np.log10(np.sqrt(np.mean(x*x)))),gain_reduction_db=float(20*np.log10(adj)))
 m=e.align_metric(e.lp(ref,3500),e.lp(pwm,3500));out['metrics']=m;return out
if __name__=='__main__':
 folder=Path(sys.argv[2]);folder.mkdir(parents=True,exist_ok=True);print(previews(sys.argv[1],folder))
