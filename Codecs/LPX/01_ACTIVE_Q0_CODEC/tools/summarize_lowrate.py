"""Retain paired low-rate ablations, common-cohort summaries and listening WAVs."""
import argparse,csv,json,math,random,shutil,statistics
from pathlib import Path
import numpy as np
import soundfile as sf
from benchmark_standards import save,sha,file_sha
from benchmark_lowrate import STAGES,CONFIG
from standard_metrics import pwm_pcm16

PHASES=('aligned_pcm16','aligned_pwm8')


def aggregate(rows,phase='aligned_pcm16'):
    good=[(name,r) for name,r in rows if r['status']=='ok']
    metrics=[r['metrics'][phase] for _,r in good]
    power=sum(m['reference_energy'] for m in metrics);error=sum(m['error_energy'] for m in metrics)
    n=sum(m['samples'] for m in metrics);stoi=[m['stoi'] for m in metrics if m['stoi'] is not None]
    finite=[m['ser_db'] for m in metrics if m['ser_db'] is not None]
    worst=max(good,key=lambda p:p[1]['metrics'][phase]['max_abs_error_pcm16']) if good else None
    return {'encoded_cases':len(good),'ser_aggregate_db':10*math.log10(power/error) if power and error else None,
        'ser_mean_db':statistics.mean(finite) if finite else None,'stoi_mean':statistics.mean(stoi) if stoi else None,
        'rmse_pcm16':math.sqrt(error/n) if n else None,
        'max_abs_error_pcm16':worst[1]['metrics'][phase]['max_abs_error_pcm16'] if worst else None,
        'worst_case':worst[0] if worst else None,
        'audio_kbps_mean':statistics.mean(r['audio_packet_bytes']/500 for _,r in good) if good else None,
        'file_bytes_mean':statistics.mean(r['file_bytes'] for _,r in good) if good else None}


def summarize(report,baseline):
    result={'cases':len(report['cases']),'groups':[],'standard_comparison':[],'crossrate_12_vs_old16':[]}
    for group in ('clean','tuning','validation','quiet','noise15','acoustic_music','synthetic'):
        cases=[c for c in report['cases'] if c['group']==group or group in ('tuning','validation') and c['group']=='clean' and c['split']==group]
        for rate in CONFIG['rates']:
            rows={c['id']:next(r for r in c['rates'] if r['ceiling_bps']==rate) for c in cases}
            item={'group':group,'ceiling_bps':rate,'expected_cases':len(cases),'stages':{},'paired_vs_baseline':{}}
            for stage in ('baseline',)+STAGES:
                item['stages'][stage]={phase:aggregate([(c['id'],rows[c['id']][stage]) for c in cases],phase) for phase in PHASES}
            for stage in STAGES:
                paired=[c for c in cases if rows[c['id']]['baseline']['status']=='ok' and rows[c['id']][stage]['status']=='ok']
                item['paired_vs_baseline'][stage]={'case_ids':[c['id'] for c in paired]}
                for phase in PHASES:
                    a=aggregate([(c['id'],rows[c['id']]['baseline']) for c in paired],phase)
                    b=aggregate([(c['id'],rows[c['id']][stage]) for c in paired],phase)
                    delta=[rows[c['id']][stage]['metrics'][phase]['stoi']-rows[c['id']]['baseline']['metrics'][phase]['stoi'] for c in paired if rows[c['id']][stage]['metrics'][phase]['stoi'] is not None]
                    item['paired_vs_baseline'][stage][phase]={'baseline':a,'new':b,
                         'stoi_delta_mean':statistics.mean(delta) if delta else None,
                         'stoi_improved_cases':sum(d>1e-9 for d in delta),'stoi_worse_cases':sum(d < -1e-9 for d in delta)}
            result['groups'].append(item)
        paired=[c for c in cases if next(r for r in c['rates'] if r['ceiling_bps']==16000)['baseline']['status']=='ok'
                and next(r for r in c['rates'] if r['ceiling_bps']==12000)['joint']['status']=='ok']
        cross={'group':group,'case_ids':[c['id'] for c in paired]}
        for phase in PHASES:
            a=aggregate([(c['id'],next(r for r in c['rates'] if r['ceiling_bps']==16000)['baseline']) for c in paired],phase)
            b=aggregate([(c['id'],next(r for r in c['rates'] if r['ceiling_bps']==12000)['joint']) for c in paired],phase)
            cross[phase]={'old16':a,'new12':b,'actual_audio_bitrate_reduction_percent':100*(1-b['audio_kbps_mean']/a['audio_kbps_mean']) if a['audio_kbps_mean'] else None}
        result['crossrate_12_vs_old16'].append(cross)
    for rate in CONFIG['rates']:
        cases=[c for c in report['cases'] if c['group']=='clean'];entries={}
        for stage in STAGES:entries[stage]=aggregate([(c['id'],next(r for r in c['rates'] if r['ceiling_bps']==rate)[stage]) for c in cases])
        for codec in ('opus_audio','opus_voip','vorbis','speex_abr','speex_cbr_under'):
            entries[codec]=aggregate([(c['id'],next(r for r in next(x for x in baseline['cases'] if x['id']==c['id'])['rates'] if r['ceiling_bps']==rate)[codec]) for c in cases])
        result['standard_comparison'].append({'ceiling_bps':rate,'cases':len(cases),'codecs':entries})
    return result


def listening(report,baseline,baseline_root,corpus,output):
    output=Path(output);assets=output/'assets';assets.mkdir(parents=True,exist_ok=True);key={};html=[];attribution={}
    ids=('ru_pushkin_a4','ru_russia_b4','en_letter_a4','en_normcore_a4_quiet','ru_russia_a4_noise15','piano','orchestra','violin')
    playlist=[(ceiling,name) for ceiling in (16000,12000) for name in ids]
    for index,(ceiling,name) in enumerate(playlist,1):
        case=next(c for c in report['cases'] if c['id']==name);row=next(r for r in case['rates'] if r['ceiling_bps']==ceiling)
        old=next(c for c in baseline['cases'] if c['id']==name);previous=next(r for r in old['rates'] if r['ceiling_bps']==ceiling)
        variants=[]
        for stage in ('target_budget','joint','perceptual'):
            if row[stage]['status']=='ok':variants.append((stage,Path(row[stage]['path']).with_suffix('.wav'),row[stage]['audio_packet_bytes']/500))
        if previous['LPX']['status']=='ok':variants.append(('baseline_LPX',baseline_root/previous['LPX']['path'].replace('selected.l4hy','decoded.wav'),previous['LPX']['audio_packet_bytes']/500))
        for codec in ('opus_audio','vorbis','speex_cbr_under'):
            r=previous[codec]
            if r['status']!='ok':continue
            path=(baseline_root/'build/lpx-standards/results'/name/(f'speex-cbr-{r["requested_bitrate"]}.wav' if codec=='speex_cbr_under' else str(ceiling)+'/'+codec+'.wav'))
            variants.append((codec,path,r['audio_packet_bytes']/500))
        random.Random(int.from_bytes(bytes.fromhex(sha(name.encode()))[:8],'little')).shuffle(variants)
        mapping={letter:{'variant':kind,'actual_audio_kbps':rate} for letter,(kind,_,rate) in zip('ABCDEFG',variants)}
        key[str(index)]={'case':name,'ceiling_bps':ceiling,'labels':mapping};sources=[('R',corpus/name/'reference.wav')]+[(letter,p) for letter,(_,p,_) in zip('ABCDEFG',variants)]
        for letter,path in sources:
            pcm,rate=sf.read(path,dtype='int16');assert rate==8000 and pcm.shape==(32000,)
            sf.write(assets/f'{index:02d}-{letter}.wav',pcm,rate,subtype='PCM_16')
            sf.write(assets/f'{index:02d}-{letter}-pwm.wav',pwm_pcm16(pcm).astype(np.int16),rate,subtype='PCM_16')
        controls=lambda suffix:' '.join('<label>'+letter+'<audio controls preload="none" src="assets/'+f'{index:02d}-{letter}{suffix}.wav'+'"></audio></label>' for letter,_ in sources)
        html.append(f'<section><h2>Пример {index} — потолок {ceiling//1000} кбит/с</h2><p>PCM16</p>'+controls('')+'<p>Общий цифровой PWM8</p>'+controls('-pwm')+'</section>')
        attribution[str(index)]={'case':name,'provenance':case['provenance'],'changes':'4s mono 8kHz codec reconstructions and digital PWM derivatives; no gain normalization'}
    (output/'index.html').write_bytes(('<!doctype html><meta charset="utf-8"><title>LPX: слепое сравнение</title><style>body{font:16px system-ui;max-width:1100px;margin:24px auto}section{padding:16px;border-bottom:1px solid #ccc}label{display:inline-flex;flex-direction:column;margin:6px}audio{width:300px}</style><h1>LPX: сравнение при потолках 12 и 16 кбит/с</h1><p>R — эталон. Остальные варианты перемешаны. Фактические битрейты различаются. Громкость не нормализована. Запишите предпочтение до открытия listening-key.json. PWM — цифровая модель выхода.</p><p><a href="attribution.json">Источники и лицензии</a></p>'+''.join(html)).encode())
    save(output/'listening-key.json',key);save(output/'attribution.json',{'sources':report['sources'],'cases':attribution})


def run(parts,corpus,baseline_root,output,avr=None):
    corpus,baseline_root,output=map(Path,(corpus,baseline_root,output));output.mkdir(parents=True,exist_ok=True)
    reports=[json.loads(Path(p).read_text(encoding='utf-8')) for p in parts]
    manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    baseline=json.loads((baseline_root/'Codecs/LPX/research/q0-standards-2026-10-25/measurements.json').read_text(encoding='utf-8'))
    report={k:v for k,v in reports[0].items() if k not in ('cases','shard','shards')};report['cases']=[];report['sources']=manifest['sources']
    seen=set()
    for part in reports:
        if any(part[k]!=report[k] for k in ('revision','config','corpus_sha256')):raise ValueError('Mixed benchmark configurations')
        for c in part['cases']:
            if c['id'] in seen or len(c['rates'])!=2:raise ValueError('Duplicate/incomplete cases')
            seen.add(c['id']);report['cases'].append(c)
    if seen!={c['id'] for c in manifest['cases']}:raise ValueError('Missing corpus cases')
    report['cases'].sort(key=lambda c:c['id']);summary=summarize(report,baseline)
    if avr:
        validation=json.loads(Path(avr).read_text(encoding='utf-8'))
        if {c['id'] for c in validation['cases']}!=seen:raise ValueError('Missing AVR cases')
        points=[p for c in validation['cases'] for p in c['points']]
        summary['avr']={'successful_points':len(points),'unique_images':len(validation['images']),
          'non_admitted_points':sum(not p['avr_admitted'] for p in points),
          'mean_budget_percent_min':min(p['mean_decode_budget_percent'] for p in points),
          'mean_budget_percent_max':max(p['mean_decode_budget_percent'] for p in points)}
    save(output/'measurements.json',report);save(output/'summary.json',summary)
    rows=[]
    for c in report['cases']:
        for r in c['rates']:
            for stage in ('baseline',)+STAGES:
                item=r[stage]
                for phase in PHASES:
                    m=item.get('metrics',{}).get(phase,{})
                    rows.append({'case':c['id'],'group':c['group'],'split':c['split'],'ceiling_bps':r['ceiling_bps'],
                        'stage':stage,'phase':phase,'status':item['status'],'audio_bytes':item.get('audio_packet_bytes'),
                        'file_bytes':item.get('file_bytes'),**{k:m.get(k) for k in ('ser_db','ser_status','rmse_pcm16','max_abs_error_pcm16','max_abs_error_percent_fs','max_error_signed_pcm16','max_error_sample','max_error_seconds','stoi')}})
    with (output/'measurements.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    listening(report,baseline,baseline_root,corpus,output/'listening');return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('parts',nargs='+',type=Path)
    ap.add_argument('--corpus',type=Path,required=True);ap.add_argument('--baseline-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--avr',type=Path)
    a=ap.parse_args();run(a.parts,a.corpus,a.baseline_root,a.output,a.avr)
