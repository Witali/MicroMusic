"""Independent receiver, cap and whole-reference audit of current corpus artifacts."""
import collections,hashlib,json,time
from pathlib import Path
import numpy as np
from batch_decoder import BatchSession
import speech_compact as compact
from standard_metrics import error_metrics,pwm_duties,pwm_pcm16
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from benchmark import quality,floors,sources
ROOT=Path.cwd();BASE=ROOT/'build/v5-joint/corpus';BRANCH=sys.argv[1] if len(sys.argv)>1 else 'full'
assert BRANCH in ('full','lsf-only')
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
 import soundfile as sf
 start=time.perf_counter();manifest=read(BASE/'strong-private.json');lookup={c['id']:c for c in manifest['cases']};current=sources();rows=[];seen=set();decoded={};metric_cache={};counts=collections.Counter()
 with BatchSession('batch',speech=True,speech_compact=True) as common,BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as only:
  for shard in range(3):
   folder=BASE/BRANCH/f'shard-{shard}';report=read(folder/'results.json')
   assert report['status']=='complete' and report['environment']['source_sha256']==current
   assert report['manifest_sha256']==sha((BASE/'strong-private.json').read_bytes())
   assert len(report['cases'])==report['completed_variants']==report['expected_variants']
   for row in report['cases']:
    identity=(row['id'],row['profile'],row['growth_percent']);assert identity not in seen;seen.add(identity)
    case=lookup[row['id']];profile=next(p for p in case['profiles'] if p['profile']==row['profile']);budget=next(b for b in profile['budgets'] if b['growth_percent']==row['growth_percent']);dest=folder/row['id']/str(row['profile'])/f"growth-{row['growth_percent']:02d}"
    reference,rate=sf.read(case['reference']['path'],dtype='int16');assert rate==8000 and reference.ndim==1 and sha(reference.astype('<i2').tobytes())==case['reference']['pcm16_sha256']
    arrays={tag:[] for tag in ('incumbent','candidate','raw','selected')};sizes={tag:0 for tag in arrays}
    for seg,inc,cap in zip(row['segments'],budget['incumbent']['segments'],budget['segment_caps']):
     assert seg['index']==inc['index'] and seg['start']==inc['start'] and seg['samples']==inc['samples'] and seg['cap_bytes']==cap==(profile['variants'][0]['segments'][seg['index']]['file_bytes']*(100+row['growth_percent'])+99)//100
     paths={'incumbent':Path(inc['path']),'candidate':dest/f"segment-{seg['index']:03d}"/'candidate.l4hy','raw':dest/f"segment-{seg['index']:03d}"/'raw.l4hy','selected':dest/f"segment-{seg['index']:03d}.l4hy"}
     for tag,path in paths.items():
      blob=path.read_bytes();digest=sha(blob);n,pr,*_=compact.unpack(blob);assert n==seg['samples'] and pr==row['profile'] and len(blob)<=cap
      if tag!='selected':
       prefix='input' if tag=='incumbent' else tag
       assert digest==seg[prefix+'_sha256'] and len(blob)==seg[prefix+'_bytes']
      if digest not in decoded:
       y=compact.decode_model(blob);duties=pwm_duties(y)
       for receiver in (common,only):
        assert np.array_equal(receiver.decode_one_s16(blob,n),y) and np.array_equal(receiver.decode_one(blob,n),duties)
        counts['native_pcm_pwm_checks']+=2
       decoded[digest]=y;counts['distinct_streams']+=1
      arrays[tag].append(decoded[digest]);sizes[tag]+=len(blob);counts['serialized_stream_instances']+=1
    arrays={tag:np.concatenate(parts) for tag,parts in arrays.items()}
    measured={}
    for tag,y in arrays.items():
     metric_key=(case['reference']['pcm16_sha256'],sha(y.astype('<i2').tobytes()))
     if metric_key not in metric_cache:
      metric_cache[metric_key]=quality(reference,y);counts['fresh_unique_quality_evaluations']+=1
     measured[tag]=metric_cache[metric_key]
    assert all(len(y)==case['samples'] for y in arrays.values())
    for tag in arrays:assert measured[tag]==row[tag]
    assert measured['incumbent']==budget['incumbent']['metrics'] and floors(measured['selected'],measured['incumbent'])
    assert sizes['selected']==row['file_bytes']<=row['complete_stream_cap_bytes'] and sum(budget['segment_caps'])==row['complete_stream_cap_bytes']
    assert sha(arrays['selected'].astype('<i2').tobytes())==row['output_pcm16_sha256'] and sha(pwm_duties(arrays['selected']).tobytes())==row['output_pwm_sha256']
    assert np.array_equal(arrays['selected'],arrays[row['selected_variant']])
    for tag,y in arrays.items():
     disk,rate=sf.read(dest/f"{tag}.wav",dtype='int16');assert rate==8000 and np.array_equal(disk,y)
    rows.append(row);counts['joined_metric_sets']+=4
 expected={(c['id'],p['profile'],b['growth_percent']) for c in manifest['cases'] for p in c['profiles'] for b in p['budgets']};assert seen==expected
 groups=[]
 for profile in (4,6):
  for growth in (0,5,10):
   subset=[r for r in rows if r['profile']==profile and r['growth_percent']==growth];g={'profile':profile,'growth_percent':growth,'cases':len(subset),'improved':sum(r['quality_improved'] for r in subset),'original_stream_bytes':sum(r['original_bytes'] for r in subset),'incumbent_stream_bytes':sum(r['incumbent_bytes'] for r in subset),'selected_stream_bytes':sum(r['file_bytes'] for r in subset),'selected_variants':dict(collections.Counter(r['selected_variant'] for r in subset))}
   for domain in ('pcm16','pwm8'):
    g[domain]={}
    for baseline in ('original_metrics','incumbent'):
     old=sum(r[baseline][domain]['error_energy'] for r in subset);new=sum(r['selected'][domain]['error_energy'] for r in subset);valid=[r for r in subset if r[baseline][domain]['stoi'] is not None and r['selected'][domain]['stoi'] is not None]
     g[domain][baseline]={'baseline_error_energy':old,'selected_error_energy':new,'sse_reduction_percent':100*(old-new)/old if old else 0,'stoi_pairs':len(valid),'mean_stoi_gain':float(np.mean([r['selected'][domain]['stoi']-r[baseline][domain]['stoi'] for r in valid])) if valid else None}
   groups.append(g)
 summary={'schema':'lpx-v5-joint-independent-audit-v1','status':'complete','branch':BRANCH,'cases':len(manifest['cases']),'segments':manifest['segment_count'],'variants':len(rows),'counts':dict(counts),'source_sha256':current,'audit_sha256':sha(Path(__file__).read_bytes()),'manifest_sha256':sha((BASE/'strong-private.json').read_bytes()),'groups':groups,'elapsed_seconds':time.perf_counter()-start}
 (BASE/('independent-audit.json' if BRANCH=='full' else BRANCH+'-independent-audit.json')).write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n');print(json.dumps({k:v for k,v in summary.items() if k!='source_sha256'},allow_nan=False))
if __name__=='__main__':main()
