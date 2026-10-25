#!/usr/bin/env python3
"""Offline cross-recording selection of ONE compile-time PWM gain for LPX4 AVR.

This changes no compressed-file bits or memory state, but requires rebuilding
all AVR sketches using the chosen LPX4_PWM_GAIN. Evaluate on held-out speakers.
"""
from __future__ import annotations
import argparse,json,subprocess,tempfile,sys,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tools'))
from auto_search_lambda import read_truth,evaluate

def run(manifest,output,min_stoi_drop=.001,max_snr_drop=.1):
    clips=json.loads(manifest.read_text(encoding='utf-8'))
    assert len(clips)>=2,'multiple voices recommended for shared gain'
    reference={}
    with tempfile.TemporaryDirectory() as d:
        work=Path(d);result=[]
        for gain in range(124,137):
            exe=work/f'decode_gain{gain}'
            subprocess.run(['g++','-O3','-std=c++11','-DLPX4_PWM_ROUND=1',f'-DLPX4_PWM_GAIN={gain}',
               '-I'+str(R/'src'),str(R/'src/Lpx4HybridCore.cpp'),str(R/'tests/decode_host.cpp'),'-o',str(exe)],
               check=True,capture_output=True)
            out=[]
            for item in clips:
                wav=read_truth(Path(item['truth']));blob=Path(item['stream']).read_bytes()
                q=evaluate(str(item['id']),blob,exe,wav,work)
                out.append({'id':item['id'],'stoi':q.stoi,'pcm_snr_db':q.pcm_snr_db})
                if gain==130:reference[item['id']]={'stoi':q.stoi,'pcm_snr_db':q.pcm_snr_db}
            result.append({'gain':gain,'samples':out})
        for r in result:
            r['min_stoi']=min(x['stoi'] for x in r['samples'])
            r['min_snr']=min(x['pcm_snr_db'] for x in r['samples'])
            r['mean_snr']=sum(x['pcm_snr_db'] for x in r['samples'])/len(clips)
            r['accepted']=all(x['stoi']>=reference[x['id']]['stoi']-min_stoi_drop and
                                x['pcm_snr_db']>=reference[x['id']]['pcm_snr_db']-max_snr_drop for x in r['samples'])
        candidates=[v for v in result if v['accepted']]
        best=max(candidates,key=lambda r:(r['mean_snr'],r['min_stoi']))
        info={'shared_gain':best['gain'],'gain_baseline':130,'policy':{'max_stoi_loss_per_record':min_stoi_drop,
              'max_pcm_snr_loss_db_per_record':max_snr_drop},'results':result,'source_count':len(clips),
              'warning':'Tune on training voices, evaluate on held-out voices; 16-MHz AVR cycle budget still unverified.'}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        config=output.with_suffix('.h')
        config.write_text(f'// Compile-time calibration; apply consistently to all Arduino builds.\n'
              f'#define LPX4_PWM_GAIN {best["gain"]}\n#define LPX4_PWM_ROUND 1\n',encoding='utf-8')
        print(json.dumps({'selected_gain':best['gain'],'mean_snr':best['mean_snr'],
                          'ref_gain':130,'report':str(output)},ensure_ascii=False))
        return info
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('manifest',type=Path);a.add_argument('--report',type=Path,required=True)
    a.add_argument('--max-stoi-loss',type=float,default=.001)
    a.add_argument('--max-snr-loss',type=float,default=.1)
    v=a.parse_args();run(v.manifest,v.report,v.max_stoi_loss,v.max_snr_loss)
