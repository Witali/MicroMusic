"""Audit full saved signals and summarize the completed 8/12/16 study.

Production and final decoder-admission revisions are recorded separately.
Audio/input paths remain local; retained JSON/CSV use anonymous case IDs.
"""
import argparse,ast,csv,json,math,re,subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save,sha
from benchmark_profile_development import floor_ok
from standard_metrics import error_metrics,pwm_duties,pwm_pcm16
from q0_model import decode_pcm16

ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(path):return sha(Path(path).read_bytes())
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def need(ok,message):
    if not ok:raise ValueError(message)
def git(*args):return subprocess.check_output(['git',*args])

def producer_revision(commit):
    prefix='Codecs/LPX/01_ACTIVE_Q0_CODEC'
    def at(path):return git('show',commit+':'+prefix+'/'+path)
    tree=ast.parse(at('tools/benchmark_profile_development.py'))
    config=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='revision')
    names=next(ast.literal_eval(n.value) for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='names' for t in n.targets))
    source_names=git('ls-tree','--name-only',commit+':'+prefix+'/src').decode().splitlines()
    # Producer ran on Windows: Path ordering is case-insensitive.
    files=[(name,at('src/'+name)) for name in sorted(source_names,key=str.casefold)]
    files.extend((name+'.py',at('tools/'+name+'.py')) for name in names)
    return sha(b''.join(name.encode()+data for name,data in files)+json.dumps(config,sort_keys=True).encode())

def metrics_equal(a,b):
    for key,value in a.items():
        other=b[key]
        if isinstance(value,float):need(other is not None and math.isclose(value,other,rel_tol=1e-12,abs_tol=1e-9),'Saved error metrics changed')
        else:need(value==other,'Saved error metadata changed')

def image_audit(folder,record,n,pwm,assembly,irq):
    need(record['done'] and not record['decoder_error'],'AVR decode incomplete')
    need(record['input_samples']==record['played']==record['produced']==record['decode_calls']==n,'AVR sample count differs')
    need(record['timer_ticks']==n+record['underruns'],'AVR timer count differs')
    need(record['cpu_hz']==16000000 and record['audio_hz']==8000,'AVR clock differs')
    need(record['pwm_sha256']==pwm and record['stack_margin_bytes']>0 and record['flash_bytes']<=32768,'AVR waveform/memory admission failed')
    if assembly:need(record['underruns']==0,'ASM underrun')
    need(record['extra_irq_cycles']==irq,'IRQ stress setting differs')
    for file,key in (('profile.elf','elf_sha256'),('profile.hex','hex_sha256'),('valid.pcm8','pwm_sha256')):
        need(digest(folder/file)==record[key],'Saved AVR artifact changed')

def stats(values):
    values=[float(x) for x in values if x is not None]
    return {'mean':sum(values)/len(values),'min':min(values),'max':max(values)} if values else None

def aggregate(rows):
    result={}
    for rate in (8000,12000,16000):
        pairs=[next(r for r in c['rates'] if r['ceiling_bps']==rate) for c in rows]
        out={'cases':len(pairs),'changed_streams':sum(r['changed'] for r in pairs)}
        for stage in ('baseline','selected'):
            points=[r[stage] for r in pairs];energy=sum(p['quality']['reference_energy'] for p in points);error=sum(p['quality']['error_energy'] for p in points)
            out[stage]={'pooled_ser_db':10*math.log10(energy/error) if energy>0 and error>0 else None,
                'stoi':stats(p['quality']['stoi'] for p in points),'max_abs_error_pcm16':max(p['quality']['max_abs_error_pcm16'] for p in points),
                'file_bps':stats(p['file_bps'] for p in points),'payload_bps':stats(p['payload_bps'] for p in points)}
        out['lower_sse']=sum(r['selected']['quality']['error_energy']<r['baseline']['quality']['error_energy'] for r in pairs)
        out['equal_sse']=sum(r['selected']['quality']['error_energy']==r['baseline']['quality']['error_energy'] for r in pairs)
        out['larger_sse']=sum(r['selected']['quality']['error_energy']>r['baseline']['quality']['error_energy'] for r in pairs)
        out['peak_increases']=sum(r['selected']['quality']['max_abs_error_pcm16']>r['baseline']['quality']['max_abs_error_pcm16'] for r in pairs)
        out['pwm_peak_increases']=sum(r['selected']['pwm_quality']['max_abs_error_pcm16']>r['baseline']['pwm_quality']['max_abs_error_pcm16'] for r in pairs)
        result[str(rate)]=out
    return result

def run(inputs,results,default_avr,small_avr,stress,output,producer='22a7f722',playlist=None):
    inputs,results,default_avr,small_avr,stress,output=map(Path,(inputs,results,default_avr,small_avr,stress,output))
    manifest=load(inputs);default=load(default_avr/'verification.json');small=load(small_avr/'verification.json');long=load(stress/'verification.json')
    expected=producer_revision(producer);cases=[];csv_rows=[];points=0
    need(len(manifest['cases'])==len(default['cases'])==len(small['cases'])==27,'Incomplete full-corpus result')
    need(small['environment']['settings']['speech']==small['environment']['settings']['speech_compact']==False,'Legacy recipe unexpectedly includes speech parsers')
    need(small['recipe']=='unroll1-tune0-lto-call-relax','Unexpected final recipe')
    for name,value in small['environment']['source_sha256'].items():need(digest(ROOT/'src'/name)==value,'Final decoder source changed')
    with BatchSession('batch',v3_features=24) as decoder:
        for c in manifest['cases']:
            folder=results/c['id'];data=load(folder/'complete.json')
            need(data['fingerprint']==sha(json.dumps([expected,c],sort_keys=True).encode()),'Production fingerprint differs from pinned producer')
            need(default['cases'][c['id']]['quality_fingerprint']==small['cases'][c['id']]['quality_fingerprint']==data['fingerprint'],'AVR/quality cases differ')
            ref,sr=sf.read(c['reference'],dtype='int16');need(sr==8000 and ref.shape==(32000,) and sha(ref.astype('<i2').tobytes())==c['reference_sha256'],'Reference changed')
            saved,sr=sf.read(folder/'original.wav',dtype='int16')
            need(sr==8000 and np.array_equal(saved,ref),'Saved listening reference changed')
            need({r['ceiling_bps'] for r in data['rates']}=={8000,12000,16000},'Missing rate point')
            for row in data['rates']:
                rate=row['ceiling_bps'];need(row['full_file_cap_bytes']==20+rate//2,'Wrong full-file cap')
                for stage in ('baseline','selected'):
                    meta=row[stage];path=folder/str(rate)/(stage+'.l4hy');blob=path.read_bytes();pcm,sr=sf.read(path.with_suffix('.wav'),dtype='int16')
                    need(sha(blob)==meta['stream_sha256'] and len(blob)==meta['file_bytes']<=row['full_file_cap_bytes'],'Stream/cap changed')
                    need(sr==8000 and pcm.shape==(32000,) and sha(pcm.astype('<i2').tobytes())==meta['pcm16_sha256'],'Saved full WAV changed')
                    native=decoder.decode_one_s16(blob,32000)
                    need(native is not None and np.array_equal(pcm,native) and np.array_equal(pcm,decode_pcm16(blob)),'Final native/model output changed')
                    pwm=pwm_duties(pcm).tobytes();need(sha(pwm)==meta['pwm_sha256'],'PWM hash changed')
                    metrics_equal(error_metrics(ref,pcm,c['kind']=='speech'),meta['quality']);metrics_equal(error_metrics(ref,pwm_pcm16(pcm),c['kind']=='speech'),meta['pwm_quality'])
                    need(meta['file_bps']==len(blob)*2 and meta['payload_bps']==(len(blob)-20)*2,'Actual rate accounting differs')
                    record=default['images'][meta['stream_sha256']]
                    image_audit(default_avr/'images'/meta['stream_sha256'],record,32000,meta['pwm_sha256'],True,0)
                    csv_rows.append({'id':c['id'],'group':c['group'],'kind':c['kind'],'rate':rate,'stage':stage,
                        'file_bps':meta['file_bps'],'payload_bps':meta['payload_bps'],'ser_db':meta['quality']['ser_db'],
                        'stoi':meta['quality']['stoi'],'max_abs_error_pcm16':meta['quality']['max_abs_error_pcm16'],
                        'pwm_ser_db':meta['pwm_quality']['ser_db'],'pwm_stoi':meta['pwm_quality']['stoi'],'default_cycles':record['mean_decode_wall_cycles']})
                    points+=1
                need(floor_ok(row['baseline']['quality'],row['selected']['quality']) and floor_ok(row['baseline']['pwm_quality'],row['selected']['pwm_quality']),'Final PCM/PWM floors failed')
                selected=row['selected'];record=small['images'][selected['stream_sha256']]
                cache=load(small_avr/'images'/selected['stream_sha256']/'verification.json')
                need(cache['measurement']==record and cache['measurement_sha256']==sha(canonical(record)),'Small-code cache metadata changed')
                image_audit(small_avr/'images'/selected['stream_sha256'],record,32000,selected['pwm_sha256'],True,0)
                need('-DLPX4_ENABLE_SPEECH=0' in record['compiler_options'] and '-DLPX4_ENABLE_SPEECH_COMPACT=0' in record['compiler_options'],'Final speech-parser flags differ')
            cases.append(data)
    need(points==162,'Expected162 full-waveform checks')
    for study,location,small_recipe in ((long,stress,False),(small,small_avr/'stress',True)):
        for rate in (8000,12000,16000):
            entry=(study['stress'] if small_recipe else study['profiles'])[str(rate)]
            path=location/str(rate)/'repeat.l4hy';blob=path.read_bytes();need(sha(blob)==entry['repeat_stream_sha256'],'Stress stream changed')
            pwm=sha(pwm_duties(decode_pcm16(blob)).tobytes())
            for name,assembly,irq in (('normal',True,0),('extra_irq100',True,100),('c_fallback',False,0)):
                image_audit(path.parent/name,entry['images'][name],64000,pwm,assembly,irq)
    summary={'schema':1,'producer_commit':producer,'producer_revision':expected,'case_count':27,'points':81,
        'native_full_waveform_checks':points,'historical8_cases':sum(c['baseline8_historically_measured'] for c in cases),
        'new8_baselines':sum(not c['baseline8_historically_measured'] for c in cases),
        'physical_hardware_measured':False,'human_listening_scores_collected':False,'groups':{'all':aggregate(cases)},
        'final_recipe':small['recipe'],'final_decoder_sources':small['environment']['source_sha256'],'resources':{},
        'default_unique_images':len(default['images']),'small_unique_images':len(small['images']),'continuous_images':18}
    groups={'clean_speech':[c for c in cases if c['kind']=='speech' and c['group']=='clean'],
            'historical8_subset':[c for c in cases if c['baseline8_historically_measured']],
            'new8_baseline_subset':[c for c in cases if not c['baseline8_historically_measured']]}
    groups.update({'group_'+g:[c for c in cases if c['group']==g] for g in sorted({c['group'] for c in cases})})
    for label,rows in groups.items():
        if rows:summary['groups'][label]=aggregate(rows)
    for rate in (8000,12000,16000):
        old=[];new=[]
        for c in cases:
            meta=next(r for r in c['rates'] if r['ceiling_bps']==rate)['selected'];old.append(default['images'][meta['stream_sha256']]);new.append(small['images'][meta['stream_sha256']])
        summary['resources'][str(rate)]={'default_selected_cycles':stats(r['mean_decode_wall_cycles'] for r in old),
            'small_selected_cycles':stats(r['mean_decode_wall_cycles'] for r in new),'program_flash_bytes':stats(r['flash_excluding_stream_bytes'] for r in new),
            'static_sram_bytes':stats(r['static_sram_bytes'] for r in new),'stack_margin_bytes':stats(r['stack_margin_bytes'] for r in new),
            'observed_stack_bytes_after_ready':stats(r['stack_high_water_bytes_after_ready'] for r in new),'underruns':sum(r['underruns'] for r in new)}
    output.mkdir(parents=True,exist_ok=True);save(output/'summary.json',summary);save(output/'measurements.json',{'cases':cases,'producer_commit':producer,'producer_revision':expected})
    save(output/'default-avr.json',default);save(output/'small-avr.json',small);save(output/'default-stress.json',long)
    with (output/'measurements.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(csv_rows[0]));writer.writeheader();writer.writerows(csv_rows)
    chosen=list(playlist or [c['id'] for c in cases if c['baseline8_historically_measured']][:4])
    need(len(chosen)==4 and len(set(chosen))==4 and set(chosen)<={c['id'] for c in cases},'Playlist needs4 existing distinct cases')
    listening=results.parent/'listening';listening.mkdir(parents=True,exist_ok=True);gap=np.zeros(4000,np.int16)
    players=[('original',None,None)]
    players.extend((stage+str(rate//1000),rate,stage) for rate in (8000,12000,16000) for stage in ('baseline','selected'))
    tracks={}
    for name,rate,stage in players:
        pieces=[]
        for i,case in enumerate(chosen):
            if i:pieces.append(gap)
            path=results/case/'original.wav' if rate is None else results/case/str(rate)/(stage+'.wav')
            pcm,sr=sf.read(path,dtype='int16');need(sr==8000 and pcm.shape==(32000,),'Playlist source changed');pieces.append(pcm)
        pcm=np.concatenate(pieces);sf.write(listening/(name+'.wav'),pcm,8000,subtype='PCM_16')
        read,sr=sf.read(listening/(name+'.wav'),dtype='int16');need(sr==8000 and read.shape==(140000,) and np.array_equal(read,pcm),'Playlist WAV changed')
        tracks[name]={'samples':140000,'pcm16_sha256':sha(read.astype('<i2').tobytes())}
    save(listening/'summary.json',summary);save(listening/'tracks.json',{'case_order':chosen,'gap_samples':4000,'tracks':tracks})
    options=''.join(f'<option value="{c["id"]}">{c["id"]}: {c["kind"]}, {c["group"]}</option>' for c in cases)
    audio=''.join(f'<section><h3>{label}</h3><audio controls preload="none" src="{name}.wav"></audio></section>' for name,label in
        [('original','Оригинал'),('baseline8','LPX8 до'),('selected8','LPX8 после'),('baseline12','LPX12 до'),('selected12','LPX12 после'),('baseline16','LPX16 до'),('selected16','LPX16 после')])
    percase='<audio id="caseOriginal" controls preload="none"></audio>'+''.join(f'<p>LPX{r}: до / после</p><audio id="b{r}" controls preload="none"></audio><audio id="s{r}" controls preload="none"></audio>' for r in (8,12,16))
    page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>LPX8/12/16: до и после</title>
<style>body{max-width:1000px;margin:28px auto;padding:0 18px;font:17px/1.5 system-ui;background:#f4f6f8;color:#172431}section{padding:12px 18px;background:white;border-radius:10px;margin:10px 0}audio{width:100%}select{font:inherit;padding:7px}</style>
<h1>Выбранные профили LPX8/12/16</h1><p>Одинаковые полные mono/8kHz/PCM16 записи, без подгонки громкости и задержки. Сборники по17,5 секунды: четыре фрагмента по4 секунды и паузы по0,5. Порядок: '''+', '.join(chosen)+'''.</p>
<p>«До» для8 — пять прежних точек либо отдельно созданная допустимая база; это указано в JSON. PCM/PWM SSE и речевая STOI не ухудшились, но пиковая ошибка в некоторых случаях выросла. Эти WAV — линейный PCM16, а не запись аналогового выхода платы.</p>'''+audio+'''
<h2>Все27 образцов отдельно</h2><select id="case">'''+options+'''</select>'''+percase+'''
<p>Полные числа — в <a href="summary.json">JSON</a>. Качество зависит от записи; без человеческих оценок и физической платы.</p>
<script>const select=document.getElementById('case');function update(){const base='../quality/'+select.value+'/';document.getElementById('caseOriginal').src=base+'original.wav';for(const r of [8,12,16]){document.getElementById('b'+r).src=base+(r*1000)+'/baseline.wav';document.getElementById('s'+r).src=base+(r*1000)+'/selected.wav';}}select.addEventListener('change',update);update();</script></html>'''
    (listening/'index.html').write_text(page,encoding='utf-8');save(output/'listening.json',{'case_order':chosen,'gap_samples':4000,'tracks':tracks})
    print('Verified 27 cases / 81 points, 162 native full signals, all AVR artifacts and seven exact listening tracks.',flush=True)
    return summary

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('inputs','results','default_avr','small_avr','stress','output'):ap.add_argument(name,type=Path)
    ap.add_argument('--producer',default='22a7f722');ap.add_argument('--playlist',nargs=4)
    a=ap.parse_args();run(a.inputs,a.results,a.default_avr,a.small_avr,a.stress,a.output,a.producer,a.playlist)
