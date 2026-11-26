"""Frozen-model tests. Only training data from train_class.py may fit models.
All evaluation clips use the same reference, filter and approximate rate.
External package speech is used locally, not redistributed."""
import study as s
import numpy as np, json, sys, subprocess, os, uuid
from pathlib import Path
from scipy.io.wavfile import read,write
ROOT=s.ROOT

def test_inputs():
 p=ROOT/'corpus/heldout_new.wav'
 if not p.exists():
  tmp=p.with_name(p.stem+'_'+uuid.uuid4().hex+'.wav');subprocess.run(['espeak','-v','ru+f5','-s','157','-w',str(tmp),'Услышав звон ключей, сторож открыл железную дверь. Школьники изучают частоты колебаний. Шестьдесят восемь, тридцать девять, сто сорок пять. Пожалуйста, проверьте, хорошо ли слышны все согласные.'],check=True);os.replace(tmp,p)
 # No segment of dialogue or this new TTS text enters training.
 source='/opt/pyvenv/lib/python3.13/site-packages/pyannote/audio/sample/sample.wav';sr,x=read(source);d=ROOT/'local_test';d.mkdir(exist_ok=True);tmp=d/('dialogue_'+uuid.uuid4().hex+'.wav');write(tmp,sr,x[int(sr*12):]);os.replace(tmp,d/'dialogue_tail.wav');
 return {'user':np.load(ROOT/'results/user_v8.npz')['target'],'ru_v8':np.load(ROOT/'results/ru_v8.npz')['target'],'new_ru':s.load(p),'dialogue_tail':s.load(d/'dialogue_tail.wav')}

def run(name,only=None):
 tests=test_inputs();model=dict(np.load(ROOT/'models'/(name+'_model.npz')))
 for k,t in tests.items():
  if only is not None and k!=only:continue
  d=dict(model,target=t);lam=(40 if k=='user' else (140 if 'ru' in k else 35));idx,y,m=s.encode_trial(d,k+'_'+name,ex=.4,high=.55,mix=.2,lam=lam,beam=1,targetbps=5000.,tries=6,save_output=False)
  valid=m['overflow']==0 and abs(m['kbps']-5)<=.05;m['rate_valid']=bool(valid);m['seconds']=len(t)/s.FS;print('TEST',k,name,m,flush=True)
  if k!='dialogue_tail':s.save(k+'_'+name,d,idx,y,m)
  (ROOT/'logs'/(k+'_'+name+'.json')).write_text(json.dumps(m,indent=2))
if __name__=='__main__':run(*sys.argv[1:])
