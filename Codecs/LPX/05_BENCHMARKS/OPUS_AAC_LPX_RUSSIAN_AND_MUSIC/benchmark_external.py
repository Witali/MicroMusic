"""Encode all downloaded open audio samples at 8 kHz and compare Opus/AAC.
Download them with prepare_open_samples.py first; no LPX figures until a
complete raw-WAV→LPX encoder is validated for unseen speakers and music.
"""
import argparse,csv,importlib.util,json,pathlib,subprocess
import numpy as np
import soundfile as sf
from scipy.signal import correlate
from pystoi import stoi
ROOT=pathlib.Path(__file__).resolve().parent

def cmd(*args):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE, text=True)
 if p.returncode:raise RuntimeError(p.stderr)

def calc(ref,arr,speech):
 x=ref-ref.mean();y=arr-arr.mean()
 cor=correlate(x,y,mode='full',method='fft'); lags=np.arange(-len(arr)+1,len(ref));sel=np.abs(lags)<1024
 lag=int(lags[sel][np.argmax(cor[sel])]); a=ref[max(0,lag):]; b=arr[max(0,-lag):]
 n=min(len(a),len(b));a=a[:n];b=b[:n]
 ser=10*np.log10(np.sum(a*a)/max(np.sum((a-b)**2),1e-25))
 r={'ser_db':round(float(ser),3),'lag':lag}
 if speech and n>=3000:
  r['stoi']=round(float(stoi(a,b,8000,extended=False)),5)
 return r

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inputs',type=pathlib.Path,default=ROOT/'external_samples');args=ap.parse_args()
 sources=json.loads((ROOT/'OPEN_SAMPLES.json').read_text())
 out=ROOT/'external_encoded';out.mkdir(exist_ok=True)
 rows=[]
 for entry in sources:
  sample=args.inputs/(entry['id']+'_8k_mono.wav')
  if not sample.exists():print('SKIP missing',entry['id']);continue
  ref,sr=sf.read(sample,dtype='float64');assert sr==8000
  for codec in ['opus','aac']:
   for kbps in [12,16,24,32,40,48]:
    fn=out/(entry['id']+f'_{codec}_{kbps}'+('.opus' if codec=='opus' else '.m4a'))
    raw=out/(entry['id']+f'_{codec}_{kbps}.wav')
    cmdlist=['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-y','-i',str(sample),'-c:a','libopus' if codec=='opus' else 'aac','-b:a',f'{kbps}k','-ar','8000','-ac','1']
    if codec=='opus':cmdlist+=['-application','audio','-vbr','on']
    try:
     cmd(*(cmdlist+[str(fn)]));cmd('ffmpeg','-hide_banner','-nostdin','-loglevel','error','-y','-i',str(fn),'-ar','8000','-ac','1',str(raw))
     rec,sr=sf.read(raw,dtype='float64')
     r={'id':entry['id'],'category':entry['category'],'codec':codec,'target_kbps':kbps,'bytes':fn.stat().st_size,'actual_kbps':round(fn.stat().st_size*8/(len(ref)/8000)/1000,2)}
     r.update(calc(ref,rec,entry['category'] in ('ru_speech','en_speech')))
     rows.append(r)
    except Exception as exc:print('ERROR',entry['id'],codec,kbps,exc)
 (ROOT/'external_results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 with (ROOT/'external_results.csv').open('w',newline='') as f:
  fields=['id','category','codec','target_kbps','bytes','actual_kbps','ser_db','stoi','lag'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 print('Measured',len(rows),'variants from',len(set(r['id'] for r in rows)),'sources')
if __name__=='__main__':main()
