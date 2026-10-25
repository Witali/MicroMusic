#!/usr/bin/env python3
"""Merge completed shards; export paired SER/peak-error and listening data."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import statistics
import numpy as np
import soundfile as sf
from benchmark_standards import save,RATES,STANDARD,SPEEX_CBR_RATES
from standard_metrics import pwm_pcm16

CODECS=('LPX',)+STANDARD
AGG_CODECS=CODECS+('speex_cbr_under',)
PHASES=('unaligned_pcm16','aligned_pcm16','aligned_pwm8')


def cbr_under(case,cap,field='audio_packet_bytes'):
    candidates=[r for r in case['speex_cbr_points'] if r['status']=='ok' and r[field]<=cap]
    return max(candidates,key=lambda r:r[field]) if candidates else {'status':'no_fit'}


def aggregate(items,phase):
    valid=[(key,r) for key,r in items if r['status']=='ok']
    metrics=[r['metrics'][phase] for _,r in valid]
    finite=[m['ser_db'] for m in metrics if m['ser_db'] is not None]
    stoi=[m['stoi'] for m in metrics if m['stoi'] is not None]
    power=sum(m['reference_energy'] for m in metrics);error=sum(m['error_energy'] for m in metrics)
    samples=sum(m['samples'] for m in metrics)
    worst=max(valid,key=lambda p:p[1]['metrics'][phase]['max_abs_error_pcm16']) if valid else None
    return {'encoded_cases':len(valid),'ser_finite_cases':len(finite),
        'ser_mean_db':statistics.mean(finite) if finite else None,
        'ser_median_db':statistics.median(finite) if finite else None,
        'ser_aggregate_db':10*math.log10(power/error) if power and error else None,
        'rmse_aggregate_pcm16':math.sqrt(error/samples) if samples else None,
        'mean_max_abs_error_pcm16':statistics.mean(m['max_abs_error_pcm16'] for m in metrics) if metrics else None,
        'worst_max_abs_error_pcm16':worst[1]['metrics'][phase]['max_abs_error_pcm16'] if worst else None,
        'worst_case':worst[0] if worst else None,
        'worst_sample':worst[1]['metrics'][phase]['max_error_sample'] if worst else None,
        'stoi_mean':statistics.mean(stoi) if stoi else None,
        'stoi_min':min(stoi) if stoi else None,
        'audio_kbps_mean':statistics.mean(r['audio_packet_bytes']*8/4/1000 for _,r in valid) if valid else None,
        'file_bytes_mean':statistics.mean(r['file_bytes'] for _,r in valid) if valid else None}


def paired(cases,rate,codec,phase,matched=False):
    pairs=[]
    for case in cases:
        row=next(r for r in case['rates'] if r['ceiling_bps']==rate)
        left=row['LPX']
        if codec=='speex_cbr_under':
            right=(cbr_under(case,left['file_bytes'],'file_bytes') if left['status']=='ok' else None) if matched else cbr_under(case,row['cap_audio_bytes'])
        else:right=case['matched_file'].get(codec) if matched else row[codec]
        if left['status']=='ok' and right and right['status']=='ok':pairs.append((case['id'],left,right))
    delta=[];peak=[];stoi=[]
    for _,a,b in pairs:
        x=a['metrics'][phase];y=b['metrics'][phase]
        if x['ser_db'] is not None and y['ser_db'] is not None:delta.append(x['ser_db']-y['ser_db'])
        peak.append(x['max_abs_error_pcm16']-y['max_abs_error_pcm16'])
        if x['stoi'] is not None and y['stoi'] is not None:stoi.append(x['stoi']-y['stoi'])
    return {'paired_cases':len(pairs),'case_ids':[p[0] for p in pairs],
        'lpx_ser_minus_standard_mean_db':statistics.mean(delta) if delta else None,
        'lpx_higher_ser_cases':sum(v>1e-9 for v in delta),
        'standard_higher_ser_cases':sum(v < -1e-9 for v in delta),
        'lpx_lower_max_error_cases':sum(v<0 for v in peak),
        'standard_lower_max_error_cases':sum(v>0 for v in peak),
        'lpx_max_error_minus_standard_mean_pcm16':statistics.mean(peak) if peak else None,
        'lpx_stoi_minus_standard_mean':statistics.mean(stoi) if stoi else None,
        'LPX':aggregate([(key,a) for key,a,_ in pairs],phase),
        'standard':aggregate([(key,b) for key,_,b in pairs],phase)}


def export_csv(report,path):
    rows=[]
    for case in report['cases']:
        streams=[]
        for rate in case['rates']:
            for codec in CODECS:streams.append(('audio_ceiling',rate['ceiling_bps'],codec,rate[codec]))
            streams.append(('audio_ceiling',rate['ceiling_bps'],'speex_cbr_under',cbr_under(case,rate['cap_audio_bytes'])))
        for codec,r in case['matched_file'].items():streams.append(('matched_complete_file',24000,codec,r))
        for r in case['speex_cbr_points']:streams.append(('speex_cbr_point',r.get('requested_bitrate'),'speex_cbr',r))
        for budget,rate,codec,r in streams:
            for phase in PHASES:
                m=r.get('metrics',{}).get(phase,{})
                rows.append({'case':case['id'],'group':case['group'],'kind':case['kind'],'budget':budget,
                    'ceiling_or_native_bps':rate,'codec':codec,'status':r['status'],'phase':phase,
                    'requested_bitrate':r.get('requested_bitrate'),
                    'audio_bytes':r.get('audio_packet_bytes'),'file_bytes':r.get('file_bytes'),
                    'codec_setup_bytes':r.get('codec_setup_bytes'),'comment_bytes':r.get('comment_bytes'),
                    'container_overhead_bytes':r.get('container_overhead_bytes'),
                    'delay_samples':r.get('metrics',{}).get('delay_samples'),
                    **{k:m.get(k) for k in ('ser_db','ser_status','rmse_pcm16','max_abs_error_pcm16',
                        'max_abs_error_percent_fs','max_error_signed_pcm16','max_error_sample','max_error_seconds','stoi')}})
    with Path(path).open('w',encoding='utf-8',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def retained(report):
    """Keep measurements/commands; summarize bulky offline-search internals."""
    def item(r):
        result={k:v for k,v in r.items() if k not in ('selection','search','exact_repack','scale_repack')}
        if 'selection' in r:
            result['selection']={k:r['selection'][k] for k in ('profile','lambda','preQ14','bytes','v2_bytes','audio_packet_bytes') if k in r['selection']}
            s=r['search'];result['search']={k:v for k,v in s.items() if k!='stages'}
            result['search']['stages']=[{k:v for k,v in stage.items() if k not in ('report','changes','proposals')}
                                       for stage in s.get('stages',[])]
            result['exact_repack']={k:v for k,v in r['exact_repack'].items() if k!='changes'}
            result['exact_repack']['changed_chunks']=len(r['exact_repack'].get('changes',[]))
            result['scale_repack']=r['scale_repack']
        return result
    result={k:v for k,v in report.items() if k!='cases'};result['cases']=[]
    for case in report['cases']:
        c={k:v for k,v in case.items() if k not in ('rates','matched_file','speex_cbr_points')}
        c['rates']=[{'ceiling_bps':row['ceiling_bps'],'cap_audio_bytes':row['cap_audio_bytes'],
                     **{codec:item(row[codec]) for codec in CODECS},
                     'speex_cbr_under':item(cbr_under(case,row['cap_audio_bytes']))} for row in case['rates']]
        c['matched_file']={key:item(r) for key,r in case['matched_file'].items()}
        c['speex_cbr_points']=[item(r) for r in case['speex_cbr_points']]
        result['cases'].append(c)
    return result


def listening(report,corpus,results,output):
    output=Path(output);assets=output/'assets';assets.mkdir(parents=True,exist_ok=True)
    fixed=('ru_pushkin_a4','ru_russia_b4','en_letter_a4','en_normcore_a4_quiet',
           'ru_russia_a4_noise15','piano','orchestra','violin')
    key={};html=[]
    for index,name in enumerate(fixed,1):
        case=next(c for c in report['cases'] if c['id']==name)
        row=next(r for r in case['rates'] if r['ceiling_bps']==24000)
        row={**row,'speex_cbr_under':cbr_under(case,row['cap_audio_bytes'])}
        available=[c for c in AGG_CODECS if row[c]['status']=='ok']
        random.Random(int.from_bytes(hashlib.sha256(name.encode()).digest()[:8],'little')).shuffle(available)
        mapping=dict(zip('ABCDEF',available));key[str(index)]={'case':name,'labels':mapping}
        reference=Path(corpus)/name/'reference.wav'
        sources=[('R',reference)]
        for label,codec in mapping.items():
            source=(Path(results)/name/f'speex-cbr-{row[codec]["requested_bitrate"]}.wav' if codec=='speex_cbr_under'
                    else Path(results)/name/'24000'/('decoded.wav' if codec=='LPX' else codec+'.wav'))
            sources.append((label,source))
        for label,source in sources:
            pcm,rate=sf.read(source,dtype='int16')
            sf.write(assets/f'{index:02d}-{label}.wav',pcm,rate,subtype='PCM_16')
            sf.write(assets/f'{index:02d}-{label}-pwm.wav',pwm_pcm16(pcm).astype(np.int16),rate,subtype='PCM_16')
        controls=lambda suffix:' '.join('<label>'+label+'<audio controls preload="none" src="assets/'+f'{index:02d}-{label}{suffix}.wav'+'"></audio></label>' for label in ['R']+list(mapping))
        html.append('<section><h2>Case '+str(index)+'</h2><p>PCM16</p>'+controls('')+'<p>Common PWM8</p>'+controls('-pwm')+'</section>')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>LPX blinded codec comparison</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:24px auto}section{padding:16px;border-bottom:1px solid #ccc}label{display:inline-flex;flex-direction:column;margin:6px}audio{width:300px}</style>'
        '<h1>Blinded codec comparison</h1><p>R is reference. A–F are shuffled codecs at the same audio-packet ceiling. Compare at the same volume; no gain normalization. Record preference before opening listening-key.json. Digital PWM excludes the analog circuit.</p>'
        '<p><a href="attribution.json">Sources, credits and licenses</a></p>'+''.join(html),encoding='utf-8')
    save(output/'listening-key.json',key)
    save(output/'attribution.json',{'sources':report['sources'],
        'cases':{str(i):{'source_case':name,'provenance':next(c for c in report['cases'] if c['id']==name)['provenance'],
                         'changes':'4-second mono 8kHz excerpt, codec reconstruction; separate fixed PWM derivatives; no level normalization'}
                 for i,name in enumerate(fixed,1)}})


def summarize(report):
    summary={'cases':len(report['cases']),'reference_seconds':sum(c['samples']/8000 for c in report['cases']),
        'rate_groups':[],'matched_file_groups':[],'reference_pwm_floor_groups':[]}
    for group in ('clean','quiet','noise15','acoustic_music','synthetic'):
        cases=[c for c in report['cases'] if c['group']==group]
        floor=[(c['id'],{'status':'ok','audio_packet_bytes':0,'file_bytes':0,
                'metrics':{'aligned_pwm8':c['reference_pwm_floor']}}) for c in cases]
        summary['reference_pwm_floor_groups'].append({'group':group,'metrics':aggregate(floor,'aligned_pwm8')})
        for rate in RATES:
            rows={c['id']:next(r for r in c['rates'] if r['ceiling_bps']==rate) for c in cases}
            rows={c['id']:{**rows[c['id']],'speex_cbr_under':cbr_under(c,rows[c['id']]['cap_audio_bytes'])} for c in cases}
            item={'group':group,'ceiling_bps':rate,'expected_cases':len(cases),'codecs':{},'paired':{}}
            for codec in AGG_CODECS:
                item['codecs'][codec]={phase:aggregate([(c['id'],rows[c['id']][codec]) for c in cases],phase) for phase in PHASES}
            for codec in AGG_CODECS[1:]:item['paired'][codec]={phase:paired(cases,rate,codec,phase) for phase in PHASES}
            summary['rate_groups'].append(item)
        item={'group':group,'expected_cases':len(cases),'paired':{}}
        for codec in AGG_CODECS[1:]:item['paired'][codec]={phase:paired(cases,24000,codec,phase,True) for phase in PHASES}
        summary['matched_file_groups'].append(item)
    return summary


def run(parts,corpus,results,output):
    reports=[json.loads(Path(p).read_text(encoding='utf-8')) for p in parts]
    expected=json.loads((Path(corpus)/'corpus.json').read_text(encoding='utf-8'))
    report={k:v for k,v in reports[0].items() if k not in ('cases','shard','shards')};report['cases']=[]
    seen=set()
    for part in reports:
        for field in ('rates','lambdas','search','ffmpeg_sha256','lpx_revision'):
            if part[field]!=report[field]:raise ValueError('Mixed benchmark configurations')
        for case in part['cases']:
            if case['id'] in seen:raise ValueError('Overlapping shards')
            if len(case['rates'])!=4 or len(case['speex_cbr_points'])!=len(SPEEX_CBR_RATES):raise ValueError('Incomplete case')
            if case['rates'][-1]['LPX']['status']=='ok' and len(case['matched_file'])!=4:raise ValueError('Incomplete file match')
            seen.add(case['id']);report['cases'].append(case)
    if seen!={c['id'] for c in expected['cases']}:raise ValueError('Missing corpus cases')
    report['cases'].sort(key=lambda c:c['id']);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    summary=summarize(report);save(output/'measurements.json',retained(report));save(output/'summary.json',summary)
    export_csv(report,output/'measurements.csv');listening(report,corpus,results,output/'listening')
    return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('parts',type=Path,nargs='+');ap.add_argument('--corpus',type=Path,required=True)
    ap.add_argument('--results',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();run(a.parts,a.corpus,a.results,a.output)
