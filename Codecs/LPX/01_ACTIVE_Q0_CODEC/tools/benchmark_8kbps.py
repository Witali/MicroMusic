"""Bounded 8 kbit/s listening trial, using the unchanged Q0 decoder."""
import argparse,json,time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save,sha,file_sha
from benchmark_multiseed import JointCache,revision as parent_revision
from budget_search import search_budget
from standard_metrics import compare,pwm_duties
from q0_model import decode_pcm16

ROOT=Path(__file__).resolve().parents[1]
CONFIG={'audio_bps':8000,'max_file_bytes':4020,'reference_samples':32000,
    'seed_stages':['existing_cli_8','enhanced_12','enhanced_16'],
    'lambdas':[.003,.01,.03,.1,.3,1.,3.],'refinement_trials':8,'beam':4,'compact_features':24,
    'scope':'Three previously heard examples, not full-corpus admission or equal quality to 12/16.',
    'selection':'Full SSE and speech STOI no worse than the feasible existing CLI8 result; then SSE/bytes/hash.'}


def run(corpus,baseline,output,report_path,ids=None):
    corpus,baseline,output,report_path=map(Path,(corpus,baseline,output,report_path))
    manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    previous_path=ROOT.parent/'research/q0-multiseed-2026-10-25/measurements.json'
    previous=json.loads(previous_path.read_text(encoding='utf-8'))
    revision=sha((parent_revision()+file_sha(__file__)+file_sha(ROOT/'tools/encode_lowrate.py')+repr(CONFIG)).encode())
    report={'config':CONFIG,'revision':revision,'previous_measurements_sha256':file_sha(previous_path),
        'corpus_sha256':file_sha(corpus/'corpus.json'),'cases':[],'decoder_modified':False,'physical_hardware_measured':False}
    with BatchSession('batch',v3_features=24) as decoder:
        for case in manifest['cases']:
            name=case['id']
            if ids is not None and name not in ids:continue
            folder=output/name;folder.mkdir(parents=True,exist_ok=True)
            ref,rate=sf.read(corpus/name/'reference.wav',dtype='int16')
            if rate!=8000 or ref.shape!=(32000,) or sha(ref.astype('<i2').tobytes())!=case['reference_sha256']:raise ValueError('Reference changed')
            old=next(c for c in previous['cases'] if c['id']==name)
            if old['reference_sha256']!=case['reference_sha256']:raise ValueError('Previous reference differs')
            seeds=[];seed_info=[];comparisons={};start=time.perf_counter()
            def score(blob,path,selection):
                pcm=decoder.decode_one_s16(blob,32000)
                if pcm is None or not np.array_equal(pcm,decode_pcm16(blob)):raise AssertionError('Independent model mismatch')
                if not np.array_equal(decoder.decode_one(blob,32000),pwm_duties(pcm)):raise AssertionError('Native PWM mismatch')
                metrics,_=compare(ref,pcm,case['kind']=='speech',known_delay=0)
                return {'status':'ok','path':str(path),'file_bytes':len(blob),'audio_packet_bytes':len(blob)-20,
                    'stream_sha256':sha(blob),'pcm16_sha256':sha(pcm.astype('<i2').tobytes()),
                    'native_model_pcm_exact':True,'native_pwm_exact':True,'metrics':metrics,'selection':selection},pcm
            baseline_path=baseline/name/'audio.l4hy';baseline_item={'status':'no_fit'}
            if baseline_path.exists():
                blob=baseline_path.read_bytes()
                if len(blob)>CONFIG['max_file_bytes']:raise ValueError('Existing CLI8 exceeded the file cap')
                baseline_item,pcm=score(blob,baseline_path,{'source':'existing_cli_8'})
                wav,sr=sf.read(baseline_path.with_name('decoded.wav'),dtype='int16')
                if sr!=8000 or not np.array_equal(wav,pcm):raise AssertionError('Existing CLI8 WAV changed')
                seeds.append(blob);seed_info.append({'stage':'existing_cli_8','stream_sha256':sha(blob),'path':str(baseline_path)})
            for rate in (12000,16000):
                item=next(r for r in old['rates'] if r['ceiling_bps']==rate)['enhanced'];path=Path(item['path']);blob=path.read_bytes()
                if sha(blob)!=item['stream_sha256']:raise ValueError('Previous seed changed')
                check,_=score(blob,path,{'source':'previous_enhanced','ceiling_bps':rate})
                if check['pcm16_sha256']!=item['pcm16_sha256']:raise AssertionError('Previous native PCM changed')
                comparisons[str(rate)]=check;seeds.append(blob)
                seed_info.append({'stage':'enhanced_'+str(rate//1000),'stream_sha256':sha(blob),'path':str(path)})
            fingerprint=sha((revision+case['reference_sha256']+repr(seed_info)).encode())
            cache=JointCache(folder/'candidates',ref,revision)
            blob,pcm,search=search_budget(seeds,ref,decoder,CONFIG['max_file_bytes'],case['kind'],
                lambdas=CONFIG['lambdas'],refinement_trials=CONFIG['refinement_trials'],encoder=cache,
                encoder_options={'beam':CONFIG['beam']})
            selected={'status':'no_fit'}
            if blob is not None:
                path=folder/'8000-enhanced.l4hy';selected,check=score(blob,path,search['selected'])
                if len(blob)>4020 or not np.array_equal(check,pcm):raise AssertionError('Selection changed')
                if baseline_item['status']=='ok':
                    a=baseline_item['metrics']['aligned_pcm16'];b=selected['metrics']['aligned_pcm16']
                    if b['error_energy']>a['error_energy'] or a['stoi'] is not None and b['stoi']<a['stoi']-1e-12:raise AssertionError('CLI8 rollback guard failed')
                path.write_bytes(blob);sf.write(path.with_suffix('.wav'),pcm,8000,subtype='PCM_16')
                verified,sr=sf.read(path.with_suffix('.wav'),dtype='int16')
                if sr!=8000 or not np.array_equal(verified,pcm):raise AssertionError('Written WAV changed')
            row={**case,'fingerprint':fingerprint,'seed_info':seed_info,'comparisons':comparisons,
                'rates':[{'ceiling_bps':8000,'cap_audio_bytes':4000,'baseline':baseline_item,'enhanced':selected}],
                'search':search,'seconds':time.perf_counter()-start,
                'cache':{'new_evaluations':cache.evaluations,'verified_hits':cache.hits}}
            save(folder/'complete.json',row);report['cases'].append(row);save(report_path,report)
            m=selected.get('metrics',{}).get('aligned_pcm16',{})
            print(name,selected['status'],selected.get('file_bytes'),'bytes',m.get('ser_db'),'SER',m.get('stoi'),'STOI',flush=True)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','baseline','output','report'):ap.add_argument(name,type=Path)
    ap.add_argument('--ids',nargs='+');a=ap.parse_args();run(a.corpus,a.baseline,a.output,a.report,a.ids)
