import json,sys,subprocess,re,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path('Codecs/LPX/01_ACTIVE_Q0_CODEC/tools').resolve()))
from adaptive_speech_voice import encode
from batch_decoder import BatchSession
from wav_lpc import load_wav
import speech_v9
cases=[('tone',np.rint(6000*np.sin(np.arange(641)*.14)+1000*np.sin(np.arange(641)*.31)).astype(np.int16),4,4),
       ('tone',np.rint(6000*np.sin(np.arange(641)*.14)+1000*np.sin(np.arange(641)*.31)).astype(np.int16),6,4),
       ('voice',load_wav('web-player/audio/originals/chego.wav')[0],4,4),
       ('voice',load_wav('web-player/audio/originals/chego.wav')[0],6,4)]
rows=[]
with BatchSession('batch',speech=True,speech_compact=True) as decoder:
 for name,pcm,profile,calls in cases:
  start=time.perf_counter();selected,decoded,report,_=encode(pcm,profile,decoder,level_policy='preserve',max_refinement_calls=calls)
  pythonSeconds=time.perf_counter()-start;expected=speech_v9.repack(selected)[0]
  start=time.perf_counter();native=subprocess.run(['build/lpx-native-encode',str(profile),'8000','adaptive',str(calls)],input=pcm.astype('<i2').tobytes(),capture_output=True,check=True)
  actual=[json.loads(re.sub(r'\bnan\b','null',line)) for line in native.stderr.decode().splitlines()]
  row=dict(name=name,profile=profile,samples=len(pcm),equal=native.stdout==expected,python_seconds=pythonSeconds,native_seconds=time.perf_counter()-start,native=actual,reference=dict(selected=report['selected_id'],candidates=len(report['candidates']),stages=[s['operator'] for s in report['stages']],selected_metrics=report['candidates'][report['selected_id']]))
  rows.append(row);Path('build/adaptive-comparison.json').write_text(json.dumps(rows,indent=2));print(json.dumps({k:v for k,v in row.items() if k!='reference'}),flush=True)
  if native.stdout!=expected:
   Path(f'build/{name}-p{profile}-reference.lpx').write_bytes(expected);Path(f'build/{name}-p{profile}-native.lpx').write_bytes(native.stdout)
   Path(f'build/{name}-p{profile}-reference.json').write_text(json.dumps(report,indent=2))
