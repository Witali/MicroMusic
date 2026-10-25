"""Merge and independently audit the frozen two-seed corpus experiment."""
import argparse,csv,json,statistics
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save,sha,file_sha
from benchmark_multiseed import CONFIG,STAGES,revision
from standard_metrics import compare
from summarize_lowrate import aggregate,PHASES
from validate_lowrate_avr import SOURCE


def groups(cases):
    result={'all':cases,'all_except_stimulus':[c for c in cases if c['id']!=CONFIG['stimulus_case']]}
    for name in ('clean','quiet','noise15','acoustic_music','synthetic'):
        result[name]=[c for c in cases if c['group']==name]
    result['clean_except_stimulus']=[c for c in result['clean'] if c['id']!=CONFIG['stimulus_case']]
    for split in ('tuning','validation'):
        result[split]=[c for c in result['clean'] if c['split']==split]
    return result


def paired(cases,rate,stage,phase):
    rows=[(c['id'],next(r for r in c['rates'] if r['ceiling_bps']==rate)) for c in cases]
    deltas=[(name,r,r[stage]['metrics'][phase],r['baseline']['metrics'][phase]) for name,r in rows]
    def ids(test):return [name for name,r,new,old in deltas if test(r,new,old)]
    stoi=[new['stoi']-old['stoi'] for _,_,new,old in deltas if old['stoi'] is not None]
    return {'case_ids':[name for name,_ in rows],
        'baseline':aggregate([(name,r['baseline']) for name,r in rows],phase),
        'new':aggregate([(name,r[stage]) for name,r in rows],phase),
        'error_improved':ids(lambda r,n,o:n['error_energy']<o['error_energy']),
        'error_equal':ids(lambda r,n,o:n['error_energy']==o['error_energy']),
        'error_worse':ids(lambda r,n,o:n['error_energy']>o['error_energy']),
        'byte_improved':ids(lambda r,n,o:r[stage]['file_bytes']<r['baseline']['file_bytes']),
        'byte_equal':ids(lambda r,n,o:r[stage]['file_bytes']==r['baseline']['file_bytes']),
        'byte_larger':ids(lambda r,n,o:r[stage]['file_bytes']>r['baseline']['file_bytes']),
        'rollback':ids(lambda r,n,o:not r[stage]['changed']),
        'spectrum_changed':ids(lambda r,n,o:r[stage]['spectrum_changed']),
        'peak_worse':ids(lambda r,n,o:n['max_abs_error_pcm16']>o['max_abs_error_pcm16']),
        'stoi_delta_mean':statistics.mean(stoi) if stoi else None,
        'stoi_improved':ids(lambda r,n,o:o['stoi'] is not None and n['stoi']>o['stoi']+1e-9),
        'stoi_worse':ids(lambda r,n,o:o['stoi'] is not None and n['stoi']<o['stoi']-1e-9),
        'raw_best_rejected_by_stoi':ids(lambda r,n,o:r[stage]['raw_best_rejected_by_stoi'])}


def audit(report,corpus,avr,old_avr,image_roots):
    manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    expected={c['id'] for c in manifest['cases']}
    assert report['revision']==revision() and report['config']==CONFIG
    assert file_sha(corpus/'corpus.json')==report['corpus_sha256']
    assert len(report['cases'])==len(expected)==27 and {c['id'] for c in report['cases']}==expected
    counts={'cases':27,'selected_points':0,'metric_records':0,'unique_streams':0,'elf_hex_pairs':0}
    digests=set();source_hashes={k:file_sha(p) for k,p in SOURCE.items()}
    if avr:
        assert len(avr['cases'])==27 and {c['id'] for c in avr['cases']}==expected
        assert avr['stages']==list(STAGES) and avr['source_sha256']==source_hashes
    with BatchSession('batch',v3_features=24) as decoder:
        for c in report['cases']:
            ref,sr=sf.read(corpus/c['id']/'reference.wav',dtype='int16')
            assert sr==8000 and ref.shape==(32000,) and sha(ref.astype('<i2').tobytes())==c['reference_sha256']
            if avr:
                verified=next(v for v in avr['cases'] if v['id']==c['id'])
                assert verified['benchmark_fingerprint']==c['fingerprint'] and len(verified['points'])==4
            assert {r['ceiling_bps'] for r in c['rates']}==set(CONFIG['rates'])
            for row in c['rates']:
                seed=next(s for s in c['seed_info'] if s['ceiling_bps']==row['ceiling_bps'])
                assert file_sha(seed['path'])==row['baseline']['stream_sha256']==seed['stream_sha256']
                baseline=decoder.decode_one_s16(Path(seed['path']).read_bytes(),32000)
                for stage in ('baseline',)+STAGES:
                    item=row[stage]
                    if stage=='baseline':pcm=baseline
                    else:
                        raw=Path(item['path']).read_bytes();pcm,rate=sf.read(Path(item['path']).with_suffix('.wav'),dtype='int16')
                        cap=row['ceiling_bps']//2+20 if stage=='enhanced' else seed['file_bytes']
                        assert sha(raw)==item['stream_sha256'] and len(raw)==item['file_bytes']<=cap==item['cap_file_bytes']
                        assert item['audio_packet_bytes']==len(raw)-20 and rate==8000 and pcm.shape==(32000,)
                        assert np.array_equal(decoder.decode_one_s16(raw,32000),pcm)
                        old=row['baseline']['metrics']['aligned_pcm16'];new=item['metrics']['aligned_pcm16']
                        assert new['error_energy']<=old['error_energy']
                        if old['stoi'] is not None:assert new['stoi']>=old['stoi']-1e-12
                        assert item['changed']==(item['stream_sha256']!=row['baseline']['stream_sha256'])
                        if avr:
                            point=next(p for p in verified['points'] if p['ceiling_bps']==row['ceiling_bps'] and p['stage']==stage)
                            assert point['stream_sha256']==item['stream_sha256'] and point['native_pcm16_exact'] and point['native_pwm_exact'] and point['error_metrics_exact']
                        digests.add(item['stream_sha256']);counts['selected_points']+=1
                    assert sha(pcm.astype('<i2').tobytes())==item['pcm16_sha256']
                    metrics,_=compare(ref,pcm,c['kind']=='speech',known_delay=0)
                    for phase in PHASES:
                        for key,value in metrics[phase].items():
                            saved=item['metrics'][phase][key]
                            if isinstance(value,float):assert abs(value-saved)<=1e-10,(c['id'],stage,phase,key)
                            else:assert value==saved,(c['id'],stage,phase,key)
                        counts['metric_records']+=1
    if avr:
        assert set(avr['images'])==digests
        for digest,p in avr['images'].items():
            assert p['input_sha256']==digest and p['produced']==p['played']==p['decode_calls']==32000
            assert p['timer_ticks']==32000+p['underruns'] and p['pwm_native_exact']
            for key,value in source_hashes.items():assert p[key]==value
            for key,value in {'queue_bytes':512,'prefill_samples':384,'dot_unroll':9,'v3_compiled_features':24,'extra_irq_cycles':0,'arithmetic_backend':'avr5-asm'}.items():assert p[key]==value
            found=False
            for root in image_roots:
                directory=root/digest
                if (directory/'profile.elf').exists() and (directory/'profile.hex').exists():
                    if file_sha(directory/'profile.elf')==p['elf_sha256'] and file_sha(directory/'profile.hex')==p['hex_sha256']:found=True;break
            assert found,('Missing original ELF/HEX',digest)
            counts['elf_hex_pairs']+=1
    # Compare every decoder source/table with the earlier standard-codec checkout.
    root=Path(__file__).resolve().parents[1]/'src';source={}
    previous=corpus.parents[2]/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src'
    for path in root.iterdir():
        if path.is_file():assert file_sha(path)==file_sha(previous/path.name);source[path.name]=file_sha(path)
    counts['unique_streams']=len(digests)
    return {'status':'passed','counts':counts,'decoder_source_sha256':source,'avr_complete':avr is not None,
        'checks':['All references, selected streams, WAVs, native PCM and complete metric records recomputed.',
        'Every nominal and original-file cap, explicit baseline SSE/STOI floor and rollback hash checked.',
        'All selected active-IRQ AVR points, unchanged source/settings and original ELF/HEX hashes checked.' if avr else 'AVR audit pending.',
        'Every decoder source/table byte-identical to the earlier standard-codec checkout.']}


def run(parts,corpus,output,avr_path=None,old_avr_path=None,image_roots=()):
    corpus,output=Path(corpus),Path(output);output.mkdir(parents=True,exist_ok=True)
    reports=[json.loads(Path(p).read_text(encoding='utf-8')) for p in parts]
    report={k:v for k,v in reports[0].items() if k not in ('cases','shard','shards')};report['cases']=[]
    for part in reports:
        assert all(part[k]==report[k] for k in ('revision','config','baseline_sha256','corpus_sha256'))
        report['cases'].extend(part['cases'])
    report['cases'].sort(key=lambda c:c['id'])
    avr=json.loads(Path(avr_path).read_text(encoding='utf-8')) if avr_path else None
    old_avr=json.loads(Path(old_avr_path).read_text(encoding='utf-8')) if old_avr_path else None
    consistency=audit(report,corpus,avr,old_avr,list(map(Path,image_roots)))
    summary={'cases':27,'groups':[],'timing':{'case_seconds_sum':sum(c['seconds'] for c in report['cases']),
        'cache_evaluations':sum(c['cache']['new_evaluations'] for c in report['cases']),
        'cache_hits':sum(c['cache']['verified_hits'] for c in report['cases']),
        'scope':'Per-case elapsed time includes guarded search/scoring, excludes old seed generation; concurrent shards overlap. Persistent cache hits are not cold encoding time.'}}
    for group,cases in groups(report['cases']).items():
        for rate in CONFIG['rates']:
            summary['groups'].append({'group':group,'ceiling_bps':rate,'cases':len(cases),
                'stages':{stage:{phase:paired(cases,rate,stage,phase) for phase in PHASES} for stage in STAGES}})
    rows=[]
    for c in report['cases']:
        for row in c['rates']:
            old=row['baseline'];old_cpu=old_avr['images'][old['stream_sha256']]['mean_decode_wall_cycles']/20 if old_avr else None
            for stage in ('baseline',)+STAGES:
                item=row[stage];image=avr['images'][item['stream_sha256']] if avr and stage!='baseline' else None
                for phase in PHASES:
                    m=item['metrics'][phase];before=old['metrics'][phase]
                    rows.append({'case':c['id'],'group':c['group'],'split':c['split'],'ceiling_bps':row['ceiling_bps'],'stage':stage,'phase':phase,
                        'file_bytes':item['file_bytes'],'audio_kbps':item['audio_packet_bytes']/500,'byte_delta':item['file_bytes']-old['file_bytes'],
                        **{key:m[key] for key in ('ser_db','ser_status','error_energy','rmse_pcm16','max_abs_error_pcm16','max_abs_error_percent_fs','max_error_sample','stoi')},
                        'ser_delta_db':m['ser_db']-before['ser_db'] if m['ser_db'] is not None and before['ser_db'] is not None else None,
                        'stoi_delta':m['stoi']-before['stoi'] if m['stoi'] is not None else None,
                        'decode_percent':image['mean_decode_wall_cycles']/20 if image else old_cpu if stage=='baseline' else None,
                        'decode_delta_pp':image['mean_decode_wall_cycles']/20-old_cpu if image and old_cpu is not None else None,
                        'underruns':image['underruns'] if image else None,'flash_bytes':image['flash_bytes'] if image else None})
    if avr:
        points=[p for c in avr['cases'] for p in c['points']];images=list(avr['images'].values())
        deltas=[r['decode_delta_pp'] for r in rows if r['phase']=='aligned_pcm16' and r['stage']!='baseline' and r['decode_delta_pp'] is not None]
        summary['avr']={'points':len(points),'unique_images':len(images),'non_admitted_points':sum(not p['avr_admitted'] for p in points),
            'underruns':sum(p['underruns'] for p in points),'mean_budget_min':min(p['mean_decode_budget_percent'] for p in points),
            'mean_budget_max':max(p['mean_decode_budget_percent'] for p in points),'flash_max':max(p['flash_bytes'] for p in images),
            'sram_max':max(p['static_sram_bytes'] for p in images),'decode_delta_pp_mean':statistics.mean(deltas) if deltas else None,
            'decode_delta_pp_max':max(deltas) if deltas else None}
    save(output/'measurements.json',report);save(output/'summary.json',summary);save(output/'consistency.json',consistency)
    with (output/'measurements.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('parts',nargs='+',type=Path)
    ap.add_argument('--corpus',required=True,type=Path);ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--avr',type=Path);ap.add_argument('--old-avr',type=Path);ap.add_argument('--image-roots',nargs='+',default=[])
    a=ap.parse_args();run(a.parts,a.corpus,a.output,a.avr,a.old_avr,a.image_roots)
