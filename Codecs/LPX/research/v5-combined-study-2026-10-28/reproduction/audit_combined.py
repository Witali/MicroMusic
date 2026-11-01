"""Independently remeasure final combined-study chains and admission flags."""
import argparse,collections,hashlib,json,math
from pathlib import Path
import time
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_speech_flash import source_hashes
from select_speech_budget import quality_source_fingerprint
import speech_compact as compact
from speech_objective import SpeechObjective
from standard_metrics import error_metrics,pwm_duties,pwm_pcm16
ROOT=Path.cwd();ACTIVE=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC';sha=lambda b:hashlib.sha256(b).hexdigest()
def canonical(j):return json.dumps(j,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def met(ref,pcm):
 result={'pcm16':error_metrics(ref,pcm,True),'pwm8':error_metrics(ref,pwm_pcm16(pcm),True)}
 for value in result.values():
  if value['stoi'] is not None and not np.isfinite(value['stoi']):value['stoi']=None
 return result
def floors(new,old):
 return all(new[d]['error_energy']<=old[d]['error_energy'] and (old[d]['stoi'] is None or new[d]['stoi'] is not None and new[d]['stoi']>=old[d]['stoi']-1e-12) for d in ('pcm16','pwm8'))
def main(study):
 study=Path(study).resolve();assert study.is_relative_to((ROOT/'build').resolve());begin=time.perf_counter();workers=[json.loads((study/'workers'/(mode+'-shard-'+str(shard)+'.json')).read_text()) for mode in ('sse','perceptual') for shard in (0,1)]
 assert all(w['status']=='complete' and len(w['records'])==49 for w in workers)
 epoch=workers[0]['source'];native=workers[0]['native'];assert all(w['source']==epoch and w['native']==native and w['settings']==workers[0]['settings'] for w in workers)
 assert source_hashes(ACTIVE/'src')==epoch['decoder']
 assert {p.name:sha(p.read_bytes()) for p in (ACTIVE/'tools').glob('*.py')}==epoch['tools']
 repro=ROOT/'Codecs/LPX/research/v5-combined-study-2026-10-28';assert sha((repro/'reproduction/run_combined.py').read_bytes())==epoch['runner'] and sha((repro/'reproduction/test_protocol.py').read_bytes())==epoch['protocol_tests'] and sha((repro/'PROTOCOL.md').read_bytes())==epoch['protocol']
 inputs=workers[0]['input_files_sha256'];docs=[]
 for path,digest in inputs.items():
  data=Path(path).read_bytes();assert sha(data)==digest;docs.append(json.loads(data))
 manifest=next(d for d in docs if d.get('schema')=='lpx-v5-encoder-quality-study-v1');old={r['id']:r for d in docs if d.get('schema')=='lpx-v5-encoder-quality-run-v1' for r in d['records']};base={r['id']:r for r in manifest['records']};assert len(base)==len(old)==98 and quality_source_fingerprint()==manifest['quality_source_fingerprint']
 for mode in ('sse','perceptual'):
  ids=[r['id'] for w in workers if w['mode']==mode for r in w['records']];assert len(ids)==len(set(ids))==98 and set(ids)==set(base)
 for name,digest in native['libraries'].items():assert sha((study/'native'/name).read_bytes())==digest
 rows=[];verified=set();model_cache=collections.OrderedDict();counters=collections.Counter()
 with BatchSession('batch',prebuilt=study/'native/common.so') as common,BatchSession('batch',prebuilt=study/'native/v5-only.so') as only:
  def decode(blob):
   key=sha(blob)
   if key not in model_cache:
    pcm=compact.decode_model(blob);n=len(pcm);pwm=pwm_duties(pcm)
    if key not in verified:
     for receiver in (common,only):
      assert np.array_equal(receiver.decode_one_s16(blob,n),pcm) and np.array_equal(receiver.decode_one(blob,n),pwm);counters['fresh_native_output_domain_comparisons']+=2
     verified.add(key);counters['fresh_native_unique_samples']+=n
    model_cache[key]=pcm
    if len(model_cache)>128:model_cache.popitem(last=False)
   else:model_cache.move_to_end(key)
   return model_cache[key]
  def load(segments,geometry):
   assert len(segments)==len(geometry);blobs=[]
   for segment,g in zip(segments,geometry):
    blob=Path(segment['path']).read_bytes();assert sha(blob)==segment['stream_sha256'] and len(blob)==segment['file_bytes'] and compact.unpack(blob)[:2]==g;blobs.append(blob)
   return tuple(blobs),np.concatenate([decode(b) for b in blobs])
  for worker in workers:
   for record in worker['records']:
    original=base[record['id']];refdata=Path(original['reference']['path']).read_bytes();assert sha(refdata)==original['reference']['file_sha256'];reference,rate=sf.read(original['reference']['path'],dtype='int16');assert rate==8000 and reference.ndim==1 and len(reference)==original['samples'] and sha(reference.astype('<i2').tobytes())==original['reference']['pcm16_sha256']
    geometry=[(s['samples'],original['profile']) for s in original['segments']];assert sum(n for n,_ in geometry)==len(reference)
    original_blobs,original_pcm=load(original['segments'],geometry);original_metrics=met(reference,original_pcm);assert original_metrics==original['baseline_metrics'] and sha(original_pcm.astype('<i2').tobytes())==original['baseline_pcm16_sha256'] and sha(pwm_duties(original_pcm).tobytes())==original['baseline_pwm_sha256']
    old_budgets={b['percent']:b for b in old[record['id']]['budgets']};old_pools=[{b} for b in original_blobs];old_chains=[]
    assert len(record['budgets'])==3 and {b['percent'] for b in record['budgets']}=={100,95,90}
    for b in old_budgets.values():
     for name in ('selected','tradeoff'):
      if b[name] is not None:
       chain,control_pcm=load(b[name]['segments'],geometry);assert met(reference,control_pcm)==b[name]['metrics'] and sum(map(len,chain))==b[name]['stream_bytes'];old_chains.append(chain);counters['fresh_old_control_metric_sets']+=1
       for i,blob in enumerate(chain):old_pools[i].add(blob)
    seed,_=load(old_budgets[100]['selected']['segments'],geometry);objective=SpeechObjective.from_chain(reference,seed,mode=worker['mode']);assert objective.describe()==record['objective']
    for budget in record['budgets']:
     percent=budget['percent'];cap=original['baseline_bytes']*percent//100;assert cap==budget['cap']==old_budgets[percent]['cap']
     accepted=old_budgets[percent]['selected'];tradeoff=old_budgets[percent]['tradeoff']
     assert budget['accepted_control_present']==(accepted is not None) and budget['tradeoff_control_present']==(tradeoff is not None)
     if accepted is not None:assert floors(accepted['metrics'],original_metrics) and budget['accepted_control_metrics']==accepted['metrics']
     for role in ('selected','tradeoff'):
      entry=budget[role]
      if entry is None:continue
      blobs,pcm=load(entry['segments'],geometry);metrics=met(reference,pcm);size=sum(map(len,blobs));assert len(pcm)==len(reference) and size==entry['stream_bytes']<=cap and metrics==entry['metrics'] and objective(pcm)==entry['objective']
      original_ok=floors(metrics,original_metrics);accepted_ok=None if accepted is None else floors(metrics,accepted['metrics']);tradeoff_ok=None if tradeoff is None else floors(metrics,tradeoff['metrics']);auto=original_ok and accepted_ok is not False
      assert entry['original_floors_passed']==original_ok and entry['accepted_control_floors_passed']==accepted_ok and entry['tradeoff_control_floors_passed']==tradeoff_ok and entry['automatic_floors_passed']==auto
      if role=='selected':assert auto
      rows.append({'mode':worker['mode'],'id':record['id'],'profile':record['profile'],'split':record['split'],'percent':percent,'role':role,'samples':len(reference),'stream_bytes':size,'original_floors_passed':original_ok,'accepted_control_floors_passed':accepted_ok,'automatic_floors_passed':auto,'new_segments':sum(blob not in old_pools[i] for i,blob in enumerate(blobs)),'whole_chain_preexisting':any(blobs==chain for chain in [original_blobs,*old_chains]),'metrics':metrics});counters['fresh_whole_chain_metric_and_objective_sets']+=1
     if accepted is not None:assert budget['selected'] is not None
    old_min=[min(map(len,pool)) for pool in old_pools]
    for segment in range(len(geometry)):
     expected_caps={max(22,min(65535,original['baseline_bytes']*percent//100-(sum(old_min)-old_min[segment]))) for percent in (100,95,90)}
     actual=[s['generation_cap'] for s in record['searches'] if s['segment']==segment];assert len(actual)==len(expected_caps) and set(actual)==expected_caps
    for search in record['searches']:
     assert search['report']['full_synthesis_evaluations']<=128 and search['report']['allocation_evaluations']<=64 and search['capacity_statistics']['evaluations']==search['report']['allocation_evaluations']
    counters['profile_mode_groups']+=1
    if counters['profile_mode_groups']%10==0:print(json.dumps({'phase':'independent-audit','profile_mode_groups':counters['profile_mode_groups'],'total':196}),flush=True)
 assert counters['profile_mode_groups']==196 and source_hashes(ACTIVE/'src')==epoch['decoder']
 for path,digest in inputs.items():assert sha(Path(path).read_bytes())==digest
 report={'schema':'lpx-v5-combined-independent-audit-v1','status':'complete','source':epoch,'settings':workers[0]['settings'],'counters':dict(counters),'unique_native_streams':len(verified),'rows':rows,'elapsed_seconds':time.perf_counter()-begin,'auditor_source_sha256':sha(Path(__file__).read_bytes()),'all_original_and_accepted_control_gates_exact':True,'all_complete_caps_exact':True,'all_whole_reference_metrics_objectives_and_native_model_pwm_exact':True}
 (study/'audit-anonymous.json').write_bytes((json.dumps(report,indent=2,allow_nan=False)+'\n').encode());print(json.dumps({'status':'complete','counters':dict(counters),'elapsed_seconds':report['elapsed_seconds']}),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True);main(parser.parse_args().study)