"""Verify final local speech artifacts and create an anonymous report/listening page.

Does not encode, simulate, upload, or infer listening scores. Run only after
benchmark_speech has refreshed its aggregate and all AVR profiles are complete.
Keep the output directory under ignored build/: it contains generated audio.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import numpy as np
import soundfile as sf
from standard_metrics import pwm_duties

CASES=tuple(f'case-{i:02d}' for i in range(1,5))
PROFILES=('4','6','8')
STANDARDS={'opus_voip-6000','opus_voip-8000','speex_cbr-3950','speex_cbr-5950','speex_cbr-8000'}
QUALITY=('ser_db','stoi','rmse_pcm16','max_abs_error_pcm16','max_abs_error_percent_fs')
AVR_FIELDS=('input_samples','input_bytes','mean_decode_wall_cycles','decode_wall_cycles_total',
    'decode_wall_cycles_max','decode_wall_cycles_max_160','flash_bytes','flash_excluding_stream_bytes',
    'static_sram_bytes','stack_high_water_bytes_after_ready','stack_margin_bytes',
    'first_output_from_reset_ms','tick_interval_min_cycles','tick_interval_max_cycles',
    'underruns','pwm_native_exact','arithmetic_backend','extra_irq_cycles')


def sha(data):return hashlib.sha256(data).hexdigest()


def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def require(condition,message):
    if not condition:raise ValueError(message)


def stats(values):
    values=[float(v) for v in values if v is not None]
    require(all(math.isfinite(v) for v in values),'Nonfinite summary input')
    return {'mean':sum(values)/len(values),'min':min(values),'max':max(values)} if values else None


def wav(path,samples):
    pcm,rate=sf.read(path,dtype='int16')
    require(rate==8000 and pcm.shape==(samples,), 'WAV is not the complete mono 8kHz reference/output')
    return pcm


def metric(row,group='aligned_pcm16'):
    result=row['metrics'][group]
    return {key:result[key] for key in QUALITY}


def aggregate_quality(rows):
    result={key:stats(r['metrics']['aligned_pcm16'][key] for r in rows) for key in QUALITY}
    power=sum(r['metrics']['aligned_pcm16']['reference_energy'] for r in rows)
    error=sum(r['metrics']['aligned_pcm16']['error_energy'] for r in rows)
    result['pooled_energy_ser_db']=10*math.log10(power/error) if power and error else None
    result['delay_samples']=stats(r['metrics']['delay_samples'] for r in rows)
    result['unaligned_ser_db']=stats(r['metrics']['unaligned_pcm16']['ser_db'] for r in rows)
    result['pwm8_ser_db']=stats(r['metrics']['aligned_pwm8']['ser_db'] for r in rows)
    result['pwm8_stoi']=stats(r['metrics']['aligned_pwm8']['stoi'] for r in rows)
    return result


def check_avr(row,samples,stream_sha=None):
    require(row['done'] and not row['decoder_error'],'Incomplete AVR decode')
    require(row['produced']==row['played']==row['decode_calls']==row['input_samples']==samples,
            'AVR did not decode/play the complete useful stream')
    require(row['pwm_native_exact'] and row['stack_margin_bytes']>0,'AVR equality or stack check failed')
    require(row['timer_ticks']==samples+row['underruns'],'AVR timer accounting mismatch')
    if stream_sha is not None:require(row['input_sha256']==stream_sha,'AVR stream is stale')
    return {key:row[key] for key in AVR_FIELDS}


def build_summary(comparison,avr_path,legacy_path,fuzz_path):
    comparison=Path(comparison);bench=read_json(comparison/'measurements.json')
    avr,legacy,fuzz=map(read_json,(avr_path,legacy_path,fuzz_path))
    rows={r['id']:r for r in bench['cases']}
    require(len(bench['cases'])==4 and set(rows)==set(CASES),'Expected exactly four anonymous complete cases')
    require(set(avr['cases'])==set(CASES),'AVR case set is incomplete')
    require(not bench.get('physical_hardware_measured') and not avr.get('physical_hardware_measured'),
            'This summary supports simulator-only evidence')
    require(legacy['streams']==91 and legacy['native_pcm16_pwm_exact_speech_enabled'] and
            legacy['fresh_avr_runs_speech_disabled'] and legacy['avr_pwm_exact'] and not legacy['underruns'],
            'Frozen legacy regression is incomplete')
    require(fuzz['cases']>0 and fuzz['speech_enabled'] and fuzz['reset_exact'] and not fuzz['sample_capped'],
            'Speech mutation/reset validation is incomplete')
    require(avr['settings']=={'queue':512,'prefill':384,'dot_unroll':9,'v3_features':24},
            'Unexpected AVR measurement settings')
    for name in ('Lpx4HybridCore.cpp','Lpx4HybridCore.h','Lpx4Math.h'):
        require(legacy['source_sha256'][name]==avr['source_sha256'][name],'Legacy/AVR decoder revisions differ')
    require(fuzz['core_sha256']==avr['source_sha256']['Lpx4HybridCore.cpp'] and
            fuzz['math_header_sha256']==avr['source_sha256']['Lpx4Math.h'],'Fuzz/AVR decoder revisions differ')
    result={'schema':1,'scope':'Four 4-second speech excerpts; preliminary simulator-only evidence.',
        'sample_rate_hz':8000,'samples_per_case':32000,'case_count':4,'useful_seconds':16,
        'human_listening_scores_collected':False,'physical_hardware_measured':False,
        'trained_codebooks':False,'case_order':list(CASES),
        'alignment':'LPX: fixed zero sample shift. Standards: documented full-reference alignment; no gain fitting.',
        'bitrate_denominator':'Useful reference duration; includes all encoded bytes, including the 80ms standards encoder tail.',
        'standards_scope':'Available operating points, not exact bitrate-matched or AVR-admitted comparisons.',
        'stack_scope':'High-water sampled after profile_ready; does not include constructor/begin startup.',
        'cpu_scope':'Decode wall cycles include active IRQ and instrumentation; budget is 2000 cycles/sample.',
        'settings':{k:avr['settings'][k] for k in ('queue','prefill','dot_unroll','v3_features')},
        'decoder_source_fingerprint':sha(json.dumps(avr['source_sha256'],sort_keys=True).encode()),
        'cases':[],'profiles':{},'standards':{},'stress':{},'partial_tail_checks':{},'legacy8_parser_cost':{}}
    audio={key:[] for key in ('original','lpx4','lpx6','lpx8')}
    standard_rows={}
    for key in CASES:
        row=rows[key];require(row['samples']==32000,'Unexpected reference duration')
        folder=comparison/key;reference=wav(folder/'original.wav',32000)
        require(sha(reference.astype('<i2').tobytes())==row['reference_sha256'],'Reference WAV changed')
        audio['original'].append(reference)
        case={'id':key,'reference_sha256':row['reference_sha256'],'profiles':{},'standards':{}}
        for p in PROFILES:
            require(p in row['profiles'] and p in avr['cases'][key],'Missing LPX/AVR profile')
            item=row['profiles'][p];blob=(folder/f'lpx{p}.l4hy').read_bytes();digest=sha(blob)
            require(digest==item['stream_sha256'],'Comparison aggregate is stale; rerun benchmark_speech')
            require(len(blob)==item['file_bytes'] and len(blob)-20==item['payload_bytes'],'LPX byte accounting changed')
            pcm=wav(folder/f'lpx{p}.wav',32000)
            require(sha(pcm.astype('<i2').tobytes())==item['pcm16_sha256'],'Listening WAV is stale')
            require(item['metrics']['delay_samples']==0,'Unexpected fitted LPX delay')
            measured=avr['cases'][key][p];check_avr(measured,32000,digest)
            require(measured['core_sha256']==avr['source_sha256']['Lpx4HybridCore.cpp'] and
                    measured['core_header_sha256']==avr['source_sha256']['Lpx4HybridCore.h'] and
                    measured['math_header_sha256']==avr['source_sha256']['Lpx4Math.h'],
                    'Case decoder revision differs from final AVR manifest')
            require(sha(pwm_duties(pcm).tobytes())==measured['pwm_sha256'],'AVR/listening PWM mismatch')
            require(measured['underruns']==0,'Main ASM profile underruns; report must not imply admission')
            case['profiles'][p]={'stream_sha256':digest,'pcm16_sha256':item['pcm16_sha256'],
                'version':item['version'],'file_bytes':len(blob),'payload_bytes':len(blob)-20,
                'file_bps':len(blob)*2,'payload_bps':(len(blob)-20)*2,
                'quality':metric(item),'pwm8_quality':metric(item,'aligned_pwm8'),
                'clipped_output_samples':item['clipped_output_samples']}
            audio['lpx'+p].append(pcm)
        require('8_without_speech' in avr['cases'][key],'Missing legacy LPX8 parser-cost control')
        original=avr['cases'][key]['8_without_speech'];enabled=avr['cases'][key]['8']
        check_avr(original,32000,row['profiles']['8']['stream_sha256'])
        require(original['pwm_sha256']==enabled['pwm_sha256'],'Parser-cost control changed legacy PWM')
        result['legacy8_parser_cost'][key]={
            'mean_wall_cycles_without_speech':original['mean_decode_wall_cycles'],
            'mean_wall_cycles_with_speech':enabled['mean_decode_wall_cycles'],
            'flash_bytes_added':enabled['flash_bytes']-original['flash_bytes'],
            'static_sram_bytes_added':enabled['static_sram_bytes']-original['static_sram_bytes']}
        require(set(row['standards'])==STANDARDS,'Unexpected or missing standard operating point')
        for codec,item in sorted(row['standards'].items()):
            if item['status']!='ok':
                case['standards'][codec]={'status':item['status']};continue
            # Resolve only the known local output layout, never follow paths
            # copied from a report or include raw commands/provenance in output.
            encoded=folder/'standards'/f"{codec}.ogg"
            require(encoded.exists() and sha(encoded.read_bytes())==item['stream_sha256'],'Standard stream changed')
            pcm=wav(folder/f'{codec}.wav',32000)
            require(sha(pcm.astype('<i2').tobytes())==item['aligned_pcm16_sha256'],'Standard listening WAV changed')
            require(item['decoded_samples']>=32000,'Standard decode omitted reference samples')
            require(item['file_bytes']==item['audio_packet_bytes']+item['codec_setup_bytes']+
                    item['comment_bytes']+item['container_overhead_bytes'],'Standard byte accounting mismatch')
            case['standards'][codec]={'status':'ok','requested_bitrate':item['requested_bitrate'],
                'file_bytes':item['file_bytes'],'payload_bytes':item['audio_packet_bytes'],
                'file_bps':item['file_bytes']*2,'payload_bps':item['audio_packet_bytes']*2,
                'delay_samples':item['metrics']['delay_samples'],'quality':metric(item)}
            standard_rows.setdefault(codec,[]).append(item)
        result['cases'].append(case)
    for p in PROFILES:
        quality=aggregate_quality([rows[key]['profiles'][p] for key in CASES])
        measured=[avr['cases'][key][p] for key in CASES]
        wall=sum(r['decode_wall_cycles_total'] for r in measured)/sum(r['decode_calls'] for r in measured)
        result['profiles'][p]={'quality':quality,'file_bps':stats(rows[k]['profiles'][p]['file_bytes']*2 for k in CASES),
            'payload_bps':stats(rows[k]['profiles'][p]['payload_bytes']*2 for k in CASES),
            'decode_wall_cycles_per_sample':wall,'wall_decode_budget_percent':wall/20,
            'decode_wall_cycles_per_sample_range':stats(r['mean_decode_wall_cycles'] for r in measured),
            **{field:stats(r[field] for r in measured) for field in
                ('decode_wall_cycles_max_160','flash_bytes','flash_excluding_stream_bytes','static_sram_bytes',
                 'stack_high_water_bytes_after_ready','stack_margin_bytes','first_output_from_reset_ms',
                 'tick_interval_min_cycles','tick_interval_max_cycles')},
            'underruns':sum(r['underruns'] for r in measured),'complete_avr_pwm_exact':True}
        require(p in avr['stress'],'Missing 8-second continuous-state stress')
        stress=avr['stress'][p];require(stress['continuous_state_samples']==64000,'Short stress workload')
        result['stress'][p]={'source_case':stress['source_case'],'continuous_state_samples':64000}
        for name in ('normal','extra_irq100','c_fallback'):
            measured=stress[name];compact=check_avr(measured,64000)
            if name!='c_fallback':require(measured['underruns']==0,'ASM stress underruns')
            compact['realtime_under_measured_conditions']=measured['underruns']==0
            result['stress'][p][name]=compact
    for codec,items in standard_rows.items():
        result['standards'][codec]={'cases':len(items),'quality':aggregate_quality(items),
            'payload_bps':stats(r['audio_packet_bytes']*2 for r in items),
            'file_bps':stats(r['file_bytes']*2 for r in items)}
    expected={f'{p}-{n}' for p in ('4','6') for n in (1,19,161,319,321)}
    require(set(avr['partial_tails'])==expected,'Missing partial-tail AVR checks')
    for key,row in avr['partial_tails'].items():
        check_avr(row,int(key.split('-')[1]))
        result['partial_tail_checks'][key]={'played':row['played'],'underruns':row['underruns'],'pwm_native_exact':True}
    result['legacy_regression']={k:legacy[k] for k in ('streams','samples','native_pcm16_pwm_exact_speech_enabled',
        'fresh_avr_runs_speech_disabled','avr_pwm_exact','underruns','current_wall_cycles','round19_wall_cycles',
        'max_sram_bytes','minimum_stack_margin_bytes')}
    result['fuzz']={k:fuzz[k] for k in ('cases','rejected','sample_capped','reset_exact','input_streams',
        'speech_enabled','max_samples_per_decode')}
    return result,audio


def write_artifacts(result,audio,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    gap=np.zeros(4000,np.int16)
    for name,clips in audio.items():
        pieces=[]
        for index,clip in enumerate(clips):
            if index:pieces.append(gap)
            pieces.append(clip)
        sf.write(output/(name+'.wav'),np.concatenate(pieces),8000,subtype='PCM_16')
    (output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    players=''.join(f'<section><h2>{label}</h2><audio controls preload="none" src="{name}.wav"></audio></section>'
        for name,label in (('original','Оригинал'),('lpx4','LPX 4 кбит/с'),('lpx6','LPX 6 кбит/с'),('lpx8','LPX 8 кбит/с')))
    rows=[]
    for p,row in result['profiles'].items():
        q=row['quality'];rows.append(f'<tr><td>LPX{p}</td><td>{row["payload_bps"]["mean"]:.0f}</td>'
            f'<td>{row["file_bps"]["mean"]:.0f}</td><td>{q["ser_db"]["mean"]:.2f}</td>'
            f'<td>{q["stoi"]["mean"]:.3f}</td><td>{q["max_abs_error_pcm16"]["max"]:.0f}</td>'
            f'<td>{row["decode_wall_cycles_per_sample"]:.1f}</td><td>{row["underruns"]}</td></tr>')
    fallback='; '.join(f'LPX{p}: {r["c_fallback"]["underruns"]} underrun' for p,r in result['stress'].items())
    page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>LPX: речь 4 / 6 / 8 кбит/с</title><style>body{font:17px/1.5 system-ui;max-width:1050px;margin:35px auto;padding:0 20px;background:#f5f7fa;color:#182535}h1,h2{line-height:1.2}section{background:white;padding:12px 22px;margin:14px 0;border-radius:12px}audio{width:100%}table{border-collapse:collapse;background:white;width:100%;font-variant-numeric:tabular-nums}th,td{text-align:right;padding:8px;border-bottom:1px solid #d6dce4}th:first-child,td:first-child{text-align:left}.table{overflow:auto}small{color:#405066}</style>
<h1>Речь LPX: 4 / 6 / 8 кбит/с</h1><p>Во всех четырёх дорожках — одинаковые четыре полные записи по 4 секунды, в порядке case-01…case-04, с паузами 0,5 секунды. Общая длительность 17,5 секунды. Уровень не подгонялся; LPX сравнивается с нулевым сдвигом отсчётов.</p>
<p><strong>Предварительные результаты.</strong> Человеческие оценки прослушивания не собирались. SER/STOI не заменяют прослушивание. Проверка процессора выполнена только в simavr, физическая плата не использовалась.</p>'''+players+'''
<h2>Объективные измерения</h2><p>Средние SER/STOI по четырём записям; максимум ошибки по всему набору. Битрейт файла включает заголовки и padding. Wall cycles включают активные IRQ и измерительную обвязку.</p><div class="table"><table><tr><th>Профиль</th><th>Payload бит/с</th><th>Файл бит/с</th><th>SER дБ</th><th>STOI</th><th>Max |ошибка| PCM16</th><th>Тактов/отсчёт</th><th>Underrun</th></tr>'''+''.join(rows)+'''</table></div>
<p>ATmega328P, 16 МГц, вывод 8 кГц; queue512 / prefill384 / unroll9, явное включение ASM. Бюджет — 2000 тактов на отсчёт. C fallback проверен на точность, его пригодность для real-time следует оценивать отдельно по пропускам.</p><p>8-секундные C-проверки: '''+html.escape(fallback)+'''.</p>
<p><small>Stack high-water измеряется после profile_ready. Opus/Speex в JSON — доступные рабочие точки, без заявления о точном совпадении битрейта или пригодности для AVR. Их фактический битрейт включает дополнительные 80 мс encoder tail и все накладные байты; знаменатель — полезные 4 секунды.</small></p><p><a href="summary.json">Полные обезличенные числа</a></p></html>'''
    (output/'index.html').write_text(page,encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('comparison','avr','legacy','fuzz','output'):ap.add_argument(name,type=Path)
    args=ap.parse_args()
    # Validate everything before producing even a partial listening package.
    result,audio=build_summary(args.comparison,args.avr,args.legacy,args.fuzz)
    write_artifacts(result,audio,args.output)
    print('Verified four complete cases, three LPX profiles, AVR/stress/regression/fuzz evidence; wrote local listening package.')


if __name__=='__main__':main()
