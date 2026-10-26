"""Test Opus/AAC on mono 8k music without redistributing any third-party test audio."""
import json, pathlib, subprocess, sys, hashlib, csv
import numpy as np
import soundfile as sf
from scipy.signal import correlate
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT/'music_results';OUT.mkdir(exist_ok=True)

def shell(*cmd):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if p.returncode:raise RuntimeError(p.stderr.decode()[:800])

def snr(ref,rec):
 cr=correlate(ref-ref.mean(),rec-rec.mean(),method='fft')
 lags=np.arange(-len(rec)+1,len(ref))
 valid=np.abs(lags)<800
 lag=int(lags[valid][np.argmax(cr[valid])]);a=ref; b=rec
 if lag>0:a=a[lag:]
 if lag<0:b=b[-lag:]
 n=min(len(a),len(b));a=a[:n];b=b[:n]
 return round(float(10*np.log10(np.sum(a*a)/max(np.sum((a-b)**2),1e-20))),2),lag

def run(path,name):
 if not path.exists():return []
 inputwav=OUT/f'{name}_reference8k.wav'
 shell('ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(path),'-af','aresample=8000','-ar','8000','-ac','1','-c:a','pcm_s16le',str(inputwav))
 ref,sr=sf.read(inputwav)
 rows=[]
 for codec in ['opus','aac']:
  for rate in [16,24,32,40,48]:
   ext='.opus' if codec=='opus' else '.m4a'; out=OUT/f'{name}_{codec}_{rate}{ext}';dec=OUT/f'{name}_{codec}_{rate}.wav'
   cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(inputwav),'-ac','1','-ar','8000', '-c:a','libopus' if codec=='opus' else 'aac','-b:a',f'{rate}k']
   if codec=='opus':cmd+=['-application','audio','-vbr','on']
   shell(*cmd,str(out))
   shell('ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(out),'-ac','1','-ar','8000','-c:a','pcm_s16le',str(dec))
   audio,s=sf.read(dec)
   S,lag=snr(ref,audio)
   rows.append({'sample':name,'codec':codec.upper(),'target_kbps':rate,'bytes':out.stat().st_size,'effective_kbps':round(out.stat().st_size*8/(len(ref)/sr)/1000,2),'ser_db':S,'lag':lag,'duration_s':round(len(ref)/sr,2)})
 return rows

def main():
 # Additional local sample from Gradio's installation used for private benchmarking; its reuse terms were not verified.
 from importlib.util import find_spec
 paths=[(ROOT/'sources'/'original_synth_music_24s_8k.wav','synthetic_polyphony_24s')]
 sax=pathlib.Path('/opt/pyvenv/lib/python3.13/site-packages/gradio/media_assets/audio/sax.wav')
 if sax.exists():paths.append((sax,'local_sax_16s'))
 allrows=[]
 for p,n in paths:allrows+=run(p,n)
 (ROOT/'music_results.json').write_text(json.dumps(allrows,ensure_ascii=False,indent=2))
 with (ROOT/'music_results.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['sample','codec','target_kbps','bytes','effective_kbps','ser_db','lag','duration_s']);w.writeheader();w.writerows(allrows)
 for r in allrows:print(r['sample'],r['codec'],r['target_kbps'],r['bytes'],r['effective_kbps'],r['ser_db'])

if __name__=='__main__':main()
