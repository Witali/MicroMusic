"""Independent local receipts; publish only the anonymous aggregate output."""
import collections,hashlib,json,math,struct,time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
import speech_compact as compact
from standard_metrics import error_metrics,pwm_duties,pwm_pcm16
from select_speech_budget import (select,evaluation_fingerprint,decoder_source_fingerprint,
                                 quality_source_fingerprint)
ROOT=Path.cwd();BASE=ROOT/'build/v5-joint'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def save(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def key(hashes):return sha(json.dumps(hashes,separators=(',',':')).encode())
def floors(a,b):
 return all(a[d]['error_energy']<=b[d]['error_energy'] and (b[d]['stoi'] is None or (a[d]['stoi'] is not None and a[d]['stoi']>=b[d]['stoi']-1e-12)) for d in ('pcm16','pwm8'))
def dominance(a,b):
 if a['firmware']['flash_bytes']>b['firmware']['flash_bytes']:return False
 x=[];y=[]
 for d in ('pcm16','pwm8'):
  am,bm=a['metrics'][d],b['metrics'][d];x.append(am['error_energy']);y.append(bm['error_energy'])
  if (am['stoi'] is None)!=(bm['stoi'] is None):return False
  if am['stoi'] is not None:x.append(-am['stoi']);y.append(-bm['stoi'])
 return all(a<=b+1e-12 for a,b in zip(x,y)) and (a['firmware']['flash_bytes']<b['firmware']['flash_bytes'] or any(a<b-1e-12 for a,b in zip(x,y)))
def elf_sections(data):
 header=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
 assert header[0][:6]==b'\x7fELF\x01\x01' and header[2]==83 and header[11]==40
 sections=[struct.unpack_from('<IIIIIIIIII',data,header[6]+i*header[11]) for i in range(header[12])]
 strings=sections[header[13]];names=data[strings[4]:strings[4]+strings[5]];result={}
 for section in sections:
  name=names[section[0]:].split(b'\0')[0].decode()
  if section[2]&2:result[name]=(section,data[section[4]:section[4]+section[5]])
 assert set(result)=={'.text','.data','.bss'}
 return result

def main():
 start=time.perf_counter();cost_path=BASE/'firmware/all-costs.json';result_path=BASE/'selection/results.json';cost_blob=cost_path.read_bytes();result_blob=result_path.read_bytes();costs=json.loads(cost_blob);result=json.loads(result_blob)
 assert result['status']=='complete' and result['costs_sha256']==sha(cost_blob),'Final selection has not yet adopted current costs'
 source=decoder_source_fingerprint();quality=quality_source_fingerprint()
 assert result['source_fingerprint']==source and result['quality_source_fingerprint']==quality
 assert len(result['profiles'])==98 and len(result['across_profiles'])==49 and costs['complete']
 counts=collections.Counter();chain_blobs={};reference_records={};cost_range=[]
 for group in costs['groups']:
  reference_records[group['id']]=group['reference']
  for entry in group['entries']:
   streams=[Path(s['path']).read_bytes() for s in entry['segments']];hashes=[sha(b) for b in streams];k=entry['key']
   assert hashes==[s['stream_sha256'] for s in entry['segments']] and [len(b) for b in streams]==[s['file_bytes'] for s in entry['segments']] and key(hashes)==k
   fields=[compact.unpack(b) for b in streams];assert [f[0] for f in fields]==[s['samples'] for s in entry['segments']] and all(f[1]==group['profile'] for f in fields)
   assert [s['index'] for s in entry['segments']]==list(range(len(streams))) and [s['start'] for s in entry['segments']]==list(np.cumsum([0]+[f[0] for f in fields][:-1]))
   chain_blobs[k]=streams;counts['current_entry_stream_checks']+=len(streams)
 assert set(chain_blobs)==set(costs['costs'])
 for k,streams in chain_blobs.items():
  cost=costs['costs'][k];assert cost is not None and cost['complete_image'] and cost['embedded_streams_exact'] and cost['source_fingerprint']==source
  assert cost['stream_sha256']==[sha(b) for b in streams] and cost['stream_bytes']==sum(map(len,streams))
  assert cost['measurement']=='linked-elf-text-plus-data' and cost['image_kind']=='elf' and cost['flash_bytes']<=32768
  folder=BASE/'firmware/images'/k;elf=(folder/'profile.elf').read_bytes();binary=(folder/'program.bin').read_bytes();assert sha(elf)==cost['image_sha256'] and sha(binary)==cost['binary_sha256']
  sections=elf_sections(elf);text=sections['.text'];data=sections['.data'];bss=sections['.bss'];assert text[0][5]==cost['text_bytes'] and data[0][5]==cost['data_bytes'] and bss[0][5]==cost['bss_bytes']
  assert binary==text[1]+data[1] and len(binary)==cost['flash_bytes']==cost['text_bytes']+cost['data_bytes']
  assert cost['program_flash_bytes']==cost['flash_bytes']-cost['stream_bytes'] and cost['static_sram_bytes']==cost['data_bytes']+cost['bss_bytes']
  ranges=cost['embedded_segment_ranges'];assert len(ranges)==len(streams)
  for i,((a,b),stream) in enumerate(zip(ranges,streams)):
   assert 0<=a<b<=len(binary) and b-a==len(stream) and binary[a:b]==stream
   assert all(b<=x or a>=y for x,y in ranges[:i])
  counts['linked_images_verified']+=1;cost_range.append(cost['flash_bytes'])
 print(json.dumps({'phase':'linked-images','verified':counts['linked_images_verified']}),flush=True)
 fresh_requests={};profile_lookup={(row['id'],row['profile']):row for row in result['profiles']}
 def bind(row,case,profile):
  k=key(row['stream_sha256']);assert k in chain_blobs and row['firmware']==costs['costs'][k]
  assert row['evaluation_fingerprint']==evaluation_fingerprint(row) and row['decoder_source_fingerprint']==source and row['quality_source_fingerprint']==quality
  assert row['reference_pcm16_sha256']==reference_records[case]['pcm16_sha256'] and row['segment_samples']==[compact.unpack(b)[0] for b in chain_blobs[k]] and row['profiles']==[profile]*len(chain_blobs[k])
  assert row['samples']==sum(row['segment_samples']) and row['stream_bytes']==sum(map(len,chain_blobs[k]))
  counts['stored_evaluation_bindings']+=1;return k
 def audit_selection(group,baseline_id):
  evaluated=group['evaluated'];byid={row['id']:row for row in evaluated};assert len(byid)==len(evaluated);baseline=byid[baseline_id]
  for policy,name in (('review','review'),('metric-proxy','metric_proxy')):
   receipt=group[name];assert receipt==select(evaluated,baseline_id,32768,growth_policy=policy)
   limit=min(32768,baseline['firmware']['flash_bytes']*110//100)
   feasible=[row for row in evaluated if row['firmware']['flash_bytes']<=limit]
   frontier=[row for row in feasible if not any(dominance(other,row) for other in feasible)]
   assert set(receipt['measured_frontier_ids'])=={row['id'] for row in frontier}
   for alternative in receipt['alternatives']:
    row=byid[alternative['id']];assert alternative['four_baseline_floors_passed']==floors(row['metrics'],baseline['metrics'])
    assert set(alternative['dominated_by'])=={other['id'] for other in feasible if dominance(other,row)}
   chosen=byid[receipt['selected_id']];anchor=byid[receipt['no_growth_id']]
   assert chosen in frontier and floors(chosen['metrics'],baseline['metrics']) and chosen['firmware']['flash_bytes']<=limit
   assert anchor['firmware']['flash_bytes']<=baseline['firmware']['flash_bytes'] and floors(anchor['metrics'],baseline['metrics'])
   if policy=='review':assert chosen['firmware']['flash_bytes']<=baseline['firmware']['flash_bytes']
   elif chosen['firmware']['flash_bytes']>anchor['firmware']['flash_bytes']:
    assert floors(chosen['metrics'],anchor['metrics'])
    stoi=all(chosen['metrics'][d]['stoi'] is not None and anchor['metrics'][d]['stoi'] is not None and chosen['metrics'][d]['stoi']-anchor['metrics'][d]['stoi']>=.005-1e-12 for d in ('pcm16','pwm8'))
    ser=all((anchor['metrics'][d]['error_energy']>0 and chosen['metrics'][d]['error_energy']==0) or (anchor['metrics'][d]['error_energy']>0 and chosen['metrics'][d]['error_energy']>0 and 10*math.log10(anchor['metrics'][d]['error_energy']/chosen['metrics'][d]['error_energy'])>=.25-1e-12) for d in ('pcm16','pwm8'))
    assert stoi or ser
   for row in (baseline,anchor,chosen):fresh_requests[(group['id'],key(row['stream_sha256']))]=row
   counts['pure_policy_decisions']+=1;counts[name+'_decisions']+=1
 for group in result['profiles']:
  for row in group['evaluated']:bind(row,group['id'],group['profile'])
  audit_selection(group,'baseline')
 for group in result['across_profiles']:
  for row in group['evaluated']:
   prefix,identifier=row['id'].split('-',1);profile=int(prefix[1:]);bind(row,group['id'],profile)
   original=next(r for r in profile_lookup[group['id'],profile]['evaluated'] if r['id']==identifier)
   expected=dict(original,id=row['id']);expected['evaluation_fingerprint']=evaluation_fingerprint(expected);assert row==expected
  audit_selection(group,'p4-baseline')
 print(json.dumps({'phase':'decisions','verified':counts['pure_policy_decisions'],'fresh_chains':len(fresh_requests)}),flush=True)
 decoded={};references={};fresh={}
 with BatchSession('batch',speech=True,speech_compact=True) as common,BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as only:
  for index,((case,k),row) in enumerate(fresh_requests.items()):
   record=reference_records[case]
   if case not in references:
    ref,rate=sf.read(record['path'],dtype='int16');assert rate==8000 and ref.ndim==1 and sha(ref.astype('<i2').tobytes())==record['pcm16_sha256'];references[case]=ref
   ref=references[case];parts=[]
   for blob in chain_blobs[k]:
    digest=sha(blob);n=compact.unpack(blob)[0]
    if digest not in decoded:
     model=compact.decode_model(blob);duties=pwm_duties(model)
     for receiver in (common,only):
      assert np.array_equal(receiver.decode_one_s16(blob,n),model) and np.array_equal(receiver.decode_one(blob,n),duties)
      counts['fresh_native_pcm_pwm_comparisons']+=2
     decoded[digest]=model;counts['fresh_distinct_streams']+=1
    parts.append(decoded[digest])
   output=np.concatenate(parts);assert len(output)==len(ref)==row['samples']
   assert sha(output.astype('<i2').tobytes())==row['output_pcm16_sha256'] and sha(pwm_duties(output).tobytes())==row['output_pwm_sha256']
   metrics={'pcm16':error_metrics(ref,output,True),'pwm8':error_metrics(ref,pwm_pcm16(output),True)}
   for value in metrics.values():
    if value['stoi'] is not None and not np.isfinite(value['stoi']):value['stoi']=None
   assert metrics==row['metrics'];fresh[case,k]=metrics;counts['fresh_whole_chain_quality_sets']+=1
   save(BASE/'selection/independent-private'/sha((case+k).encode())/'receipt.json',{'case':case,'ordered_chain_key':k,'reference_pcm16_sha256':record['pcm16_sha256'],'output_pcm16_sha256':row['output_pcm16_sha256'],'metrics':metrics,'common_v5only_model_pcm_pwm_exact':True})
   if (index+1)%25==0:print(json.dumps({'phase':'fresh-output-quality','chains':index+1,'total':len(fresh_requests)}),flush=True)
 assert decoder_source_fingerprint()==source and quality_source_fingerprint()==quality and cost_path.read_bytes()==cost_blob and result_path.read_bytes()==result_blob
 summary={'schema':'lpx-v5-budget-independent-audit-v1','status':'complete','cases':49,'profile_groups':98,'across_profile_groups':49,'counts':dict(counts),'full_flash_min_bytes':min(cost_range),'full_flash_max_bytes':max(cost_range),'target_flash_limit_bytes':32768,'complete_image_growth_limit_percent':10,'linked_elf_sections_and_binary_exact':True,'all_current_stream_files_and_cached_evaluations_bound':True,'baseline_anchor_default_proxy_fresh_quality_exact':True,'manual_four_floors_caps_frontiers_and_proxy_thresholds_passed':True,'pure_decisions_reproduced':True,'source_fingerprint':source,'quality_source_fingerprint':quality,'costs_file_sha256':sha(cost_blob),'selection_file_sha256':sha(result_blob),'audit_source_sha256':sha(Path(__file__).read_bytes()),'human_listening_confirmation_collected':False,'physical_board_measured':False,'timing_admission_inferred_from_size':False,'elapsed_seconds':time.perf_counter()-start}
 save(BASE/'selection/independent-audit.json',summary);print(json.dumps(summary,allow_nan=False),flush=True)
if __name__=='__main__':main()
