"""Fresh integrated decoder checks against historical selected-chain outputs."""
import argparse,collections,hashlib,json,sys,tempfile,time
from importlib.metadata import version
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_speech_flash import source_hashes,canonical
import speech_compact as compact
from standard_metrics import error_metrics,pwm_duties,pwm_pcm16
from select_speech_budget import evaluation_fingerprint,quality_source_fingerprint
ROOT=Path.cwd();WORK=ROOT/'build/decode-simplify'
def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def key(hashes):return sha(json.dumps(hashes,separators=(',',':')).encode())
def main(baseline):
 start=time.perf_counter();source=source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src');fingerprint=sha(canonical(source));quality=quality_source_fingerprint()
 selected_path=baseline/'selection/results.json';cost_path=baseline/'firmware/all-costs.json';selected_bytes=selected_path.read_bytes();cost_bytes=cost_path.read_bytes();selected=json.loads(selected_bytes);costs=json.loads(cost_bytes)
 assert selected['status']=='complete' and selected['costs_sha256']==sha(cost_bytes) and costs['complete']
 assert selected['quality_source_fingerprint']==quality
 assert selected['source_fingerprint']!=fingerprint,'Expected an intentionally changed decoder source'
 references={};chains={};requests={};counts=collections.Counter();old_source=selected['source_fingerprint']
 for group in costs['groups']:
  reference=group['reference'];references[group['id']]=reference
  for entry in group['entries']:
   blobs=[Path(segment['path']).read_bytes() for segment in entry['segments']];hashes=[sha(blob) for blob in blobs];chain=entry['key']
   assert key(hashes)==chain and hashes==[segment['stream_sha256'] for segment in entry['segments']]
   assert [len(blob) for blob in blobs]==[segment['file_bytes'] for segment in entry['segments']]
   fields=[compact.unpack(blob) for blob in blobs];lengths=[field[0] for field in fields]
   assert lengths==[segment['samples'] for segment in entry['segments']] and all(field[1]==group['profile'] for field in fields)
   assert [segment['index'] for segment in entry['segments']]==list(range(len(blobs))) and [segment['start'] for segment in entry['segments']]==list(np.cumsum([0]+lengths[:-1]))
   assert costs['costs'][chain]['stream_sha256']==hashes and costs['costs'][chain]['source_fingerprint']==old_source
   chains[chain]=blobs;counts['current_entry_stream_file_checks']+=len(blobs)
 for group in [*selected['profiles'],*selected['across_profiles']]:
  byid={row['id']:row for row in group['evaluated']};baseline_id=group.get('baseline_id','p4-baseline')
  for row in group['evaluated']:
   assert row['evaluation_fingerprint']==evaluation_fingerprint(row) and row['decoder_source_fingerprint']==old_source and row['quality_source_fingerprint']==quality
   assert row['reference_pcm16_sha256']==references[group['id']]['pcm16_sha256'] and key(row['stream_sha256']) in chains
   counts['historical_evaluation_bindings_checked']+=1
  identifiers={baseline_id,*[group[name][field] for name in ('review','metric_proxy') for field in ('no_growth_id','selected_id')]}
  for identifier in identifiers:
   row=byid[identifier];chain=key(row['stream_sha256']);request=(group['id'],chain)
   if request in requests:
    prior=requests[request]
    for field in ('metrics','output_pcm16_sha256','output_pwm_sha256','samples','segment_samples','profiles','reference_pcm16_sha256'):assert row[field]==prior[field]
   requests[request]=row
 assert len(requests)==204 and len(selected['profiles'])==98 and len(selected['across_profiles'])==49
 print(json.dumps({'phase':'bindings','unique_chains':len(requests),'stream_file_checks':counts['current_entry_stream_file_checks']}),flush=True)
 native_cache=WORK/'tmp/current-selected-audit';native_cache.mkdir(parents=True,exist_ok=True);tempfile.tempdir=str(native_cache)
 decoded={};reference_pcm={}
 with BatchSession('batch',v3_features=124,speech=True,speech_compact=True) as common,BatchSession('batch',v3_features=124,speech=True,speech_compact=True,compact_only=True) as only:
  for index,((case,chain),expected) in enumerate(requests.items()):
   if case not in reference_pcm:
    record=references[case];path=Path(record['path']);file=path.read_bytes()
    if 'file_sha256' in record:assert sha(file)==record['file_sha256']
    ref,rate=sf.read(path,dtype='int16');assert rate==8000 and ref.ndim==1 and sha(ref.astype('<i2').tobytes())==record['pcm16_sha256'];reference_pcm[case]=ref
   ref=reference_pcm[case];parts=[]
   for blob in chains[chain]:
    digest=sha(blob);n=compact.unpack(blob)[0]
    if digest not in decoded:
     model=compact.decode_model(blob);pwm=pwm_duties(model)
     for receiver in (common,only):
      assert np.array_equal(receiver.decode_one_s16(blob,n),model) and np.array_equal(receiver.decode_one(blob,n),pwm)
      counts['fresh_native_pcm_pwm_comparisons']+=2
     decoded[digest]=model;counts['fresh_unique_streams']+=1;counts['fresh_unique_stream_samples']+=n
    parts.append(decoded[digest])
   output=np.concatenate(parts);assert len(ref)==len(output)==expected['samples']
   pcm_hash=sha(output.astype('<i2').tobytes());pwm_hash=sha(pwm_duties(output).tobytes())
   assert pcm_hash==expected['output_pcm16_sha256'] and pwm_hash==expected['output_pwm_sha256']
   metrics={'pcm16':error_metrics(ref,output,True),'pwm8':error_metrics(ref,pwm_pcm16(output),True)}
   for value in metrics.values():
    if value['stoi'] is not None and not np.isfinite(value['stoi']):value['stoi']=None
   assert metrics==expected['metrics'];counts['fresh_whole_chain_metric_sets']+=1
   save(WORK/'validation/current-selected-private'/sha((case+chain).encode())/'receipt.json',{'case':case,'ordered_chain_key':chain,'reference_pcm16_sha256':references[case]['pcm16_sha256'],'pcm16_sha256':pcm_hash,'pwm_sha256':pwm_hash,'metrics':metrics,'common_v5only_model_exact':True})
   if (index+1)%25==0:
    assert source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src')==source
    print(json.dumps({'phase':'fresh-output-quality','chains':index+1,'total':len(requests)}),flush=True)
 assert source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src')==source and quality_source_fingerprint()==quality
 assert selected_path.read_bytes()==selected_bytes and cost_path.read_bytes()==cost_bytes
 summary={'schema':'lpx-v5-integrated-selected-chain-audit-v1','status':'complete','cases':49,'profile_groups':98,'across_profile_groups':49,'counts':dict(counts),'current_source_fingerprint':fingerprint,'current_source_sha256':source,'historical_decoder_source_fingerprint':old_source,'quality_source_fingerprint':quality,'historical_selection_file_sha256':sha(selected_bytes),'historical_costs_file_sha256':sha(cost_bytes),'audit_source_sha256':sha(Path(__file__).read_bytes()),'reference_file_and_pcm_hashes_verified':True,'all_current_stream_files_verified':True,'native_common_v5only_model_exact':True,'historical_pcm_pwm_hashes_exact':True,'whole_original_level_metrics_exact':True,'historical_flash_evidence_accepted_for_new_decoder':False,'physical_board_measured':False,'runtime':{'python':sys.version,'packages':{name:version(name) for name in ('numpy','numba','scipy','pystoi','soundfile')}},'elapsed_seconds':time.perf_counter()-start}
 save(WORK/'public/current-selected-audit.json',summary);print(json.dumps(summary,allow_nan=False),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline-study',type=Path,required=True);args=parser.parse_args();main(args.baseline_study.resolve())
