"""Pair complete diagnostic matrices by private identity; export anonymous rows."""
import argparse,hashlib,json
from pathlib import Path

def load(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def compare(before,after,output):
 before=Path(before);after=Path(after);output=Path(output)
 old=load(before/'results-private.json');new=load(after/'results-private.json')
 a=load(before/'public/summary.json');b=load(after/'public/summary.json')
 assert old['status']==new['status']==a['status']==b['status']=='complete'
 assert old['inputs_sha256']==new['inputs_sha256'] and a['validator_provenance']==b['validator_provenance']
 assert a['toolchain_dependencies']==b['toolchain_dependencies'] and a['compiler_options']==b['compiler_options']
 def keyed(data):return {(row['key'],row['report']['cost']['extra_irq_cycles']):row for row in data['reports']}
 left=keyed(old);right=keyed(new);assert len(left)==len(right)==116 and left.keys()==right.keys();rows=[]
 for identity,previous in sorted(left.items(),key=lambda pair:pair[1]['id']):
  following=right[identity];x=previous['report'];y=following['report'];xc=x['cost'];yc=y['cost']
  assert previous['id']==following['id']
  assert x['pwm_sha256']==y['pwm_sha256'] and xc['stream_sha256']==yc['stream_sha256']
  for field in ('samples','segments','stream_bytes','compiler_options','harness_sha256','hardware_address_constants'):
   assert xc[field]==yc[field],field
  for value in (x,y):
   assert value['pwm_model_exact'] and value['timing_verified'] and value['decode_timing_complete'] and not value['historical_runner']
   assert value['underruns']==value['decoder_error']==0 and value['played']==value['produced']==value['timer_ticks']==value['decode_calls']==xc['samples']
  fields=('decode_wall_cycles_total','decode_wall_cycles_max','decode_wall_cycles_max_40','decode_wall_cycles_max_80','decode_wall_cycles_max_160','stack_margin_bytes','min_queue_before_producer_eos')
  def point(report,cost):
   return {key:cost[key] for key in ('samples','segments','stream_bytes','flash_bytes','program_flash_bytes','static_sram_bytes')}|{key:report[key] for key in fields}|{'decode_duration_coverage_complete':True}
  rows.append({'id':previous['id'],'extra_irq_cycles':identity[1],'baseline':point(x,xc),'candidate':point(y,yc),
      'full_flash_saved_bytes':xc['flash_bytes']-yc['flash_bytes'],
      'static_sram_saved_bytes':xc['static_sram_bytes']-yc['static_sram_bytes'],
      'decode_wall_cycles_saved_percent':100*(x['decode_wall_cycles_total']-y['decode_wall_cycles_total'])/x['decode_wall_cycles_total'],
      'complete_frozen_model_pwm_exact':True})
 groups=[]
 for irq in (0,100):
  chosen=[row for row in rows if row['extra_irq_cycles']==irq];samples=sum(row['baseline']['samples'] for row in chosen)
  oldcycles=sum(row['baseline']['decode_wall_cycles_total'] for row in chosen);newcycles=sum(row['candidate']['decode_wall_cycles_total'] for row in chosen)
  group={'extra_irq_cycles':irq,'images':len(chosen),'profiled_samples':samples,
      'baseline_mean_cycles_per_sample':oldcycles/samples,'candidate_mean_cycles_per_sample':newcycles/samples,
      'cycles_saved_percent':100*(oldcycles-newcycles)/oldcycles,
      'full_flash_saved_range_bytes':[min(row['full_flash_saved_bytes'] for row in chosen),max(row['full_flash_saved_bytes'] for row in chosen)],
      'static_sram_saved_range_bytes':[min(row['static_sram_saved_bytes'] for row in chosen),max(row['static_sram_saved_bytes'] for row in chosen)],
      'flash_growth_images':sum(row['full_flash_saved_bytes']<0 for row in chosen),
      'image_cycle_change_percent_range':[-max(row['decode_wall_cycles_saved_percent'] for row in chosen),-min(row['decode_wall_cycles_saved_percent'] for row in chosen)]}
  for label in ('baseline','candidate'):
   group[label]={'program_flash_range_bytes':[min(row[label]['program_flash_bytes'] for row in chosen),max(row[label]['program_flash_bytes'] for row in chosen)],
      'static_sram_range_bytes':[min(row[label]['static_sram_bytes'] for row in chosen),max(row[label]['static_sram_bytes'] for row in chosen)],
      'maximum_observed_decode_cycles':max(row[label]['decode_wall_cycles_max'] for row in chosen),
      'maximum_observed_window_cycles':{str(width):max(row[label]['decode_wall_cycles_max_'+str(width)] for row in chosen) for width in (40,80,160)},
      'minimum_stack_margin_bytes':min(row[label]['stack_margin_bytes'] for row in chosen),
      'minimum_queue_before_producer_eos':min(row[label]['min_queue_before_producer_eos'] for row in chosen)}
  groups.append(group)
 summary={'schema':'lpx-v5-full-diagnostic-paired-v1','status':'complete','baseline_source_commit':'b8f473a6','candidate_source_commit':'5c7e0592','normal_images':111,'stress_images':5,
     'all116_full_duration_coverage':True,'all116_complete_model_and_frozen_pwm_exact':True,'all116_zero_underruns_and_errors':True,
     'groups':groups,'baseline_source_sha256':a['source_sha256'],'candidate_source_sha256':b['source_sha256'],
     'toolchain_dependencies':a['toolchain_dependencies'],'compiler_options':a['compiler_options'],
     'validator_provenance':a['validator_provenance'],'immutable_input_manifests_sha256':a['historical_input_manifests_sha256'],
     'comparison_source_sha256':sha(Path(__file__)),
     'scope':'Complete diagnostic images including retained counters, queue512/prefill384 and IRQ harness. These are decoder/source changes under the same harness. Application-player savings require separate same-source production ELF measurements; no capped averages or table-only savings are mixed in.',
     'physical_board_measured':False}
 save(output/'public/summary.json',summary);save(output/'public/rows.json',{'schema':'lpx-v5-full-diagnostic-paired-rows-v1','rows':rows})
 print(json.dumps({'normal':groups[0],'stress':groups[1]},allow_nan=False),flush=True)
 return summary
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('before',type=Path);parser.add_argument('after',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args();compare(args.before,args.after,args.output)
