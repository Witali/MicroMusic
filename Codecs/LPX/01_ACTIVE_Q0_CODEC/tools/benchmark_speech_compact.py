"""Common-signal compact-speech study; all media/cache outputs belong in build/.

prepare -> avr (optional independent shards) -> stress -> summarize.
No upload, baseline mutation, training, fitted gain, or subjective rating.
"""
from __future__ import annotations
import argparse, hashlib, html, json, math, os, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save
from profile_avr import ROOT, HARNESS, run as profile
from speech_compact import components, unpack, pack, repack, decode_model
from speech_v4 import decode_model as decode_v4
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16

CASES=tuple(f'case-{i:02d}' for i in range(1,5))
PROFILES=(4,6)
VARIANTS=('baseline_v4','exact_v5','refined_v5','enhanced_v5')
SETTINGS={'queue':512,'prefill':384,'dot_unroll':9,'v3_features':24,
          'speech':True,'speech_compact':True}
AVR_FIELDS=('input_samples','input_bytes','input_sha256','pwm_sha256','elf_sha256','hex_sha256',
    'mean_decode_wall_cycles','decode_wall_cycles_total','decode_wall_cycles_max',
    'decode_wall_cycles_max_160','flash_bytes','flash_excluding_stream_bytes','static_sram_bytes',
    'stack_high_water_bytes_after_ready','stack_margin_bytes','first_output_from_reset_ms',
    'tick_interval_min_cycles','tick_interval_max_cycles','underruns','pwm_native_exact',
    'arithmetic_backend','extra_irq_cycles')


def sha(data):return hashlib.sha256(data).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def need(condition,message):
    if not condition:raise ValueError(message)
def digest(path):return sha(Path(path).read_bytes())


def read_wav(path,n=32000):
    x,rate=sf.read(path,dtype='int16')
    need(rate==8000 and x.shape==(n,),'Expected the complete mono PCM16/8kHz signal')
    return x


def source_hashes():
    return {p.name:digest(p) for p in sorted((ROOT/'src').iterdir()) if p.is_file()}


def fields(blob):
    return components(blob) if blob[4]==4 else unpack(blob)[:7]


def prepare(baseline,refined,enhanced,output):
    baseline,refined,enhanced,output=map(Path,(baseline,refined,enhanced,output))
    for original in (baseline,refined,enhanced):
        a,b=original.resolve(),output.resolve()
        need(a!=b and a not in b.parents and b not in a.parents,'Study output must be separate from every input tree')
    # Refuse incomplete source sets before creating any partial study output.
    for case in CASES:
        for p in PROFILES:
            for path in (baseline/case/f'lpx{p}.l4hy',refined/case/str(p)/'audio.l4hy',
                         enhanced/case/str(p)/'audio.l4hy'):
                need(path.is_file(),f'Missing completed input: {case}/{p}/{path.parent.parent.name}')
    prior={x['id']:x for x in load(baseline/'measurements.json')['cases']}
    need(set(prior)==set(CASES),'Expected four original anonymous cases')
    manifest={'schema':1,'samples':32000,'sample_rate':8000,'case_order':list(CASES),
        'variant_order':list(VARIANTS),'decoder_sources':source_hashes(),
        'protocol':'Same full references, zero LPX delay, no gain fitting; preliminary four-speaker pilot.',
        'physical_hardware_measured':False,'human_listening_scores_collected':False,'cases':{}}
    pending=[]
    with BatchSession('batch',v3_features=24,speech=True,speech_compact=True) as decoder:
        for case in CASES:
            reference=read_wav(baseline/case/'original.wav');refhash=sha(reference.astype('<i2').tobytes())
            need(refhash==prior[case]['reference_sha256'],'Original reference changed')
            row={'reference_sha256':refhash,'profiles':{}}
            for p in PROFILES:
                original=(baseline/case/f'lpx{p}.l4hy').read_bytes()
                changed=(refined/case/str(p)/'audio.l4hy').read_bytes()
                richer=(enhanced/case/str(p)/'audio.l4hy').read_bytes()
                need(sha(original)==prior[case]['profiles'][str(p)]['stream_sha256'],'Baseline aggregate is stale')
                original_fields=components(original);changed_fields=components(changed)
                need(original_fields[:3]==changed_fields[:3] and original_fields[5:]==changed_fields[5:],
                     'Refinement changed geometry, filters, or spectral coefficients')
                need(unpack(richer)[:7]==changed_fields,'Extra-pulse stage changed base parameters/spectrum')
                exact,exact_meta=repack(original);compact,compact_meta=repack(changed)
                need(unpack(exact)[:7]==original_fields,'Exact repack changed parameters')
                blobs=dict(zip(VARIANTS,(original,exact,compact,richer)));records={};pcms={}
                for variant,blob in blobs.items():
                    need(fields(blob)[0]==32000 and fields(blob)[1]==p and fields(blob)[2]==original_fields[2],
                         'Variant changed the reference count/profile/spectrum')
                    pcm=decoder.decode_one_s16(blob,32000);pwm=decoder.decode_one(blob,32000)
                    need(pcm is not None and pwm is not None,'Native decoder rejected a study stream')
                    model=decode_v4(blob) if blob[4]==4 else decode_model(blob)
                    need(np.array_equal(pcm,model) and np.array_equal(pwm,pwm_duties(pcm)),
                         'Native/model/PWM mismatch')
                    cap=20+p*500;need(len(blob)<=cap,'Variant exceeds the original full-file budget')
                    header=20 if blob[4]==4 else 22
                    records[variant]={'version':blob[4],'file_bytes':len(blob),'payload_bytes':len(blob)-header,
                        'header_bytes':header,'file_bps':len(blob)*2,'payload_bps':(len(blob)-header)*2,
                        'full_file_cap_bytes':cap,'stream_sha256':sha(blob),
                        'pcm16_sha256':sha(pcm.astype('<i2').tobytes()),'pwm_sha256':sha(pwm.tobytes()),
                        'quality':error_metrics(reference,pcm,True),
                        'pwm_quality':error_metrics(reference,pwm_pcm16(pcm),True),
                        'native_model_exact':True,'spectra_exact':True,
                        'clipped_output_samples':int(np.count_nonzero((pcm==-32768)|(pcm==32767)))}
                    pcms[variant]=pcm
                need(np.array_equal(pcms['baseline_v4'],pcms['exact_v5']),'Pure repacking changed PCM')
                need(len(exact)<len(original),'No exact data saving on this pilot stream')
                for old,new in (('baseline_v4','refined_v5'),('refined_v5','enhanced_v5')):
                    a,b=records[old]['quality'],records[new]['quality']
                    need(b['error_energy']<=a['error_energy'] and b['stoi']>=a['stoi']-1e-12,
                         'Full-reference SSE/STOI floor failed')
                records['exact_v5']['packing']=exact_meta
                records['refined_v5']['packing']=compact_meta
                records['enhanced_v5']['extra_pulses']=sum(a!=0 for pos,a in unpack(richer)[7])
                row['profiles'][str(p)]={'variants':records,'exact_pcm_pwm_equal':True}
                pending.append((case,p,reference,blobs,pcms))
            manifest['cases'][case]=row
    for case,p,reference,blobs,pcms in pending:
        folder=output/case/str(p);folder.mkdir(parents=True,exist_ok=True)
        sf.write(output/case/'original.wav',reference,8000,subtype='PCM_16')
        for variant,blob in blobs.items():
            (folder/(variant+'.l4hy')).write_bytes(blob)
            sf.write(folder/(variant+'.wav'),pcms[variant],8000,subtype='PCM_16')
    save(output/'manifest.json',manifest)
    print('Prepared four references, eight profile points, four variants; spectra and quality floors verified.',flush=True)
    return manifest


def manifest_checked(output):
    output=Path(output);m=load(output/'manifest.json')
    need(set(m['cases'])==set(CASES) and m['decoder_sources']==source_hashes(),
         'Incomplete or stale preparation; rerun prepare for the current decoder')
    for case in CASES:
        reference=read_wav(output/case/'original.wav')
        need(sha(reference.astype('<i2').tobytes())==m['cases'][case]['reference_sha256'],'Study reference changed')
        for p in PROFILES:
            for variant in VARIANTS:
                row=m['cases'][case]['profiles'][str(p)]['variants'][variant]
                path=output/case/str(p)/(variant+'.l4hy')
                need(digest(path)==row['stream_sha256'],'Prepared stream changed')
                pcm=read_wav(path.with_suffix('.wav'))
                need(sha(pcm.astype('<i2').tobytes())==row['pcm16_sha256'],'Prepared WAV changed')
    return m


def environment(avr_bin,runner,lib,wsl):
    avr_bin,runner=Path(avr_bin),Path(runner);suffix='.exe' if os.name=='nt' else ''
    compiler=avr_bin/('avr-g++'+suffix)
    cc1=Path(subprocess.check_output([str(compiler),'-print-prog-name=cc1plus'],text=True).strip())
    files=[HARNESS/'profile.cpp',HARNESS/'sim_profile.c',ROOT/'tools/profile_avr.py',
           ROOT/'tools/batch_decoder.py',Path(__file__),compiler,cc1,runner]
    dependencies={p.name:digest(p) for p in files}
    for name in ('avr-as','avr-ld','avr-objcopy','avr-size'):
        path=avr_bin/(name+suffix)
        if path.is_file():dependencies[path.name]=digest(path)
    for path in sorted(Path(lib).glob('*.so*')):
        try:dependencies['sim-library-'+path.name]=digest(path)
        except OSError:dependencies['sim-library-'+path.name]='WSL symlink; regular targets hashed separately'
    dependencies['compiler_version']=subprocess.check_output([str(compiler),'--version'],text=True).splitlines()[0]
    return {'sources':source_hashes(),'dependencies':dependencies,'settings':SETTINGS,'wsl':wsl}


def check_measurement(row,n,stream_hash,pwm_hash=None):
    need(row['done'] and not row['decoder_error'] and row['pwm_native_exact'],'Incomplete AVR decode/PWM equality')
    need(row['input_sha256']==stream_hash and row['input_samples']==row['played']==row['produced']==row['decode_calls']==n,
         'AVR stream/sample mismatch')
    need(row['timer_ticks']==n+row['underruns'] and row['stack_margin_bytes']>0 and row['flash_bytes']<=32768,
         'AVR timer, stack, or Flash check failed')
    if pwm_hash is not None:need(row['pwm_sha256']==pwm_hash,'AVR PWM differs from prepared reference')


def cached_measure(path,folder,env,assembly,load_cycles,avr_bin,runner,lib,wsl,pwm_hash=None,require=False):
    path,folder=Path(path),Path(folder);blob=path.read_bytes();stream_hash=sha(blob)
    n=int.from_bytes(blob[8:12],'little')
    identity=sha(canonical([env,stream_hash,assembly,load_cycles]))
    cache=folder/'complete.json';r=None
    if cache.exists():
        old=load(cache);candidate=old.get('measurement',{})
        if old.get('fingerprint')==identity and old.get('environment')==env and old.get('measurement_sha256')==sha(canonical(candidate)):
            needed=((folder/'profile.elf','elf_sha256'),(folder/'profile.hex','hex_sha256'),
                    (folder/'valid.pcm8','pwm_sha256'))
            if all(p.exists() and digest(p)==candidate.get(key) for p,key in needed):r=candidate
    if r is None:
        need(not require,'Missing or stale AVR cache; run avr/stress for the current inputs/dependencies')
        r=profile(path,folder,avr_bin,runner,lib,wsl,enable_asm=assembly,irq_load=load_cycles,**SETTINGS)
        r['first_output_from_reset_ms']=r['occupancy_trace'][0]['cycle']/16000
        r['stack_high_water_bytes_after_ready']=2304-r['minimum_stack_pointer']
        r['flash_excluding_stream_bytes']=r['flash_bytes']-r['input_bytes']
        r={k:v for k,v in r.items() if k!='occupancy_trace'}
        save(cache,{'fingerprint':identity,'environment':env,
                    'measurement_sha256':sha(canonical(r)),'measurement':r})
        print(folder.name,round(r['mean_decode_wall_cycles'],3),r['underruns'],'underruns',flush=True)
    check_measurement(r,n,stream_hash,pwm_hash)
    for field,name in (('core_sha256','Lpx4HybridCore.cpp'),('core_header_sha256','Lpx4HybridCore.h'),
                       ('math_header_sha256','Lpx4Math.h')):
        need(r[field]==env['sources'][name],'AVR source hash differs from current environment')
    expected={'cpu_hz':16000000,'audio_hz':8000,'queue_bytes':512,'prefill_samples':384,
        'dot_unroll':9,'v3_compiled_features':24,'speech_compiled':True,'speech_compact_compiled':True,
        'extra_irq_cycles':load_cycles,'arithmetic_backend':'avr5-asm' if assembly else 'c'}
    need(all(r.get(k)==v for k,v in expected.items()),'AVR options differ from the study conditions')
    return r


def jobs(cases=CASES,profiles=PROFILES,variants=VARIANTS):
    result=[(c,p,v) for c in cases for p in profiles for v in variants]
    need(len(result)==len(set(result)),'Duplicate AVR selectors would overlap shards')
    return result


def avr(output,avr_bin,runner,lib,wsl,shard=0,shards=1,cases=CASES,profiles=PROFILES,variants=VARIANTS):
    need(0<=shard<shards,'Invalid AVR shard');output=Path(output)
    m=manifest_checked(output);env=environment(avr_bin,runner,lib,wsl);selected=jobs(cases,profiles,variants)
    done=[]
    for i,(case,p,variant) in enumerate(selected):
        if i%shards!=shard:continue
        row=m['cases'][case]['profiles'][str(p)]['variants'][variant]
        key=f'{case}-{p}-{variant}';path=output/case/str(p)/(variant+'.l4hy')
        r=cached_measure(path,output/'avr'/key,env,True,0,avr_bin,runner,lib,wsl,row['pwm_sha256'])
        need(r['underruns']==0,'Main ASM variant underruns; admission failed');done.append(key)
    save(output/f'avr-part-{shard}.json',{'environment_sha256':sha(canonical(env)),'shard':shard,
        'shards':shards,'images':done,'physical_hardware_measured':False})


def repeat_v5(blob):
    n,p,spectra,params,pulses,pre,bright,extras=unpack(blob)
    need(n==32000,'Stress repetition requires a complete four-second source')
    return pack(n*2,p,spectra*2,params*2,pulses*2,pre,bright,extras*2)[0]


def stress(output,avr_bin,runner,lib,wsl):
    output=Path(output);m=manifest_checked(output);env=environment(avr_bin,runner,lib,wsl)
    report={'environment_sha256':sha(canonical(env)),'profiles':{},'physical_hardware_measured':False}
    with BatchSession('batch',v3_features=24,speech=True,speech_compact=True) as decoder:
        for p in PROFILES:
            costs={}
            for case in CASES:
                row=m['cases'][case]['profiles'][str(p)]['variants']['enhanced_v5']
                path=output/case/str(p)/'enhanced_v5.l4hy'
                r=cached_measure(path,output/'avr'/f'{case}-{p}-enhanced_v5',env,True,0,
                                 avr_bin,runner,lib,wsl,row['pwm_sha256'],require=True)
                costs[case]=r['mean_decode_wall_cycles']
            case=max(costs,key=costs.get);blob=repeat_v5((output/case/str(p)/'enhanced_v5.l4hy').read_bytes())
            pcm=decoder.decode_one_s16(blob,64000);expected=decode_model(blob)
            need(pcm is not None and np.array_equal(pcm,expected),'Continuous-state stress model/native mismatch')
            pwm=sha(pwm_duties(pcm).tobytes());path=output/'stress'/f'repeat-{p}.l4hy'
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
            row={'source_case':case,'source_stream_sha256':m['cases'][case]['profiles'][str(p)]['variants']['enhanced_v5']['stream_sha256'],
                 'repeat_stream_sha256':sha(blob),'pwm_sha256':pwm,'samples':64000,'images':{}}
            for name,assembly,irq in (('normal',True,0),('extra_irq100',True,100),('c_fallback',False,0)):
                r=cached_measure(path,output/'stress'/f'{p}-{name}',env,assembly,irq,avr_bin,runner,lib,wsl,pwm)
                if assembly:need(r['underruns']==0,'ASM stress underruns')
                row['images'][name]={k:r[k] for k in AVR_FIELDS}
            report['profiles'][str(p)]=row;save(output/'stress.json',report)
    return report


def statistics(values):
    values=[float(x) for x in values if x is not None]
    need(all(math.isfinite(x) for x in values),'Nonfinite summary value')
    return {'mean':sum(values)/len(values),'min':min(values),'max':max(values)} if values else None


def summarize(output,avr_bin,runner,lib,wsl):
    output=Path(output);m=manifest_checked(output);env=environment(avr_bin,runner,lib,wsl)
    result={'schema':1,'case_count':4,'samples_per_case':32000,'useful_seconds':16,'sample_rate_hz':8000,
        'physical_hardware_measured':False,'human_listening_scores_collected':False,'trained_codebooks':False,
        'alignment':'Same complete 4-second signals; zero shift; no fitted gain or normalization.',
        'cpu_scope':'Wall decode intervals include active IRQ and instrumentation; budget2000 cycles/sample.',
        'stack_scope':'Observed high-water after profile_ready; constructor/begin before ready not measured.',
        'decoder_source_sha256':env['sources'],'measurement_dependencies':env['dependencies'],
        'settings':SETTINGS,'profiles':{},'cases':{},'stress':{}}
    measured={}
    for case,p,variant in jobs():
        row=m['cases'][case]['profiles'][str(p)]['variants'][variant]
        r=cached_measure(output/case/str(p)/(variant+'.l4hy'),output/'avr'/f'{case}-{p}-{variant}',
            env,True,0,avr_bin,runner,lib,wsl,row['pwm_sha256'],require=True)
        need(r['underruns']==0,'Main ASM variant underruns')
        measured[(case,p,variant)]=r
        result['cases'].setdefault(case,{}).setdefault(str(p),{})[variant]={**row,
            'avr':{k:r[k] for k in AVR_FIELDS}}
    for p in PROFILES:
        result['profiles'][str(p)]={}
        for variant in VARIANTS:
            rows=[m['cases'][c]['profiles'][str(p)]['variants'][variant] for c in CASES]
            images=[measured[(c,p,variant)] for c in CASES]
            summary={key:statistics(r['quality'][key] for r in rows) for key in
                ('ser_db','stoi','rmse_pcm16','max_abs_error_pcm16','max_abs_error_percent_fs')}
            power=sum(r['quality']['reference_energy'] for r in rows)
            error=sum(r['quality']['error_energy'] for r in rows)
            summary['pooled_energy_ser_db']=10*math.log10(power/error) if power and error else None
            summary.update({key:statistics(r[key] for r in rows) for key in ('file_bytes','file_bps','payload_bps')})
            summary.update({key:statistics(r[key] for r in images) for key in
                ('mean_decode_wall_cycles','flash_bytes','flash_excluding_stream_bytes','static_sram_bytes',
                 'stack_high_water_bytes_after_ready','stack_margin_bytes','first_output_from_reset_ms',
                 'decode_wall_cycles_max_160','tick_interval_min_cycles','tick_interval_max_cycles')})
            summary['underruns']=sum(r['underruns'] for r in images)
            summary['data_saving_percent_vs_v4']=100*(1-sum(r['file_bytes'] for r in rows)/
                sum(m['cases'][c]['profiles'][str(p)]['variants']['baseline_v4']['file_bytes'] for c in CASES))
            result['profiles'][str(p)][variant]=summary
    recorded=load(output/'stress.json')
    need(recorded['environment_sha256']==sha(canonical(env)),'Stale stress environment')
    for p in PROFILES:
        saved=recorded['profiles'][str(p)]
        heaviest=max(CASES,key=lambda c:measured[(c,p,'enhanced_v5')]['mean_decode_wall_cycles'])
        need(saved['source_case']==heaviest and saved['source_stream_sha256']==
             m['cases'][heaviest]['profiles'][str(p)]['variants']['enhanced_v5']['stream_sha256'],'Stale stress source')
        path=output/'stress'/f'repeat-{p}.l4hy'
        need(digest(path)==saved['repeat_stream_sha256'],'Stress stream changed')
        images={}
        for name,assembly,irq in (('normal',True,0),('extra_irq100',True,100),('c_fallback',False,0)):
            r=cached_measure(path,output/'stress'/f'{p}-{name}',env,assembly,irq,avr_bin,runner,lib,wsl,
                saved['pwm_sha256'],require=True)
            if assembly:need(r['underruns']==0,'ASM stress underruns')
            images[name]={k:r[k] for k in AVR_FIELDS}
            images[name]['realtime_under_measured_conditions']=r['underruns']==0
        result['stress'][str(p)]={'source_case':heaviest,'samples':64000,'images':images}
    # No source names, raw commands, input paths or attribution enter this JSON.
    listening=output/'listening';listening.mkdir(parents=True,exist_ok=True)
    gap=np.zeros(4000,np.int16)
    players=[('original','Оригинал',None,None)]
    for p in PROFILES:
        players.extend((f'{label}{p}',f'LPX{p}: {title}',p,variant) for label,title,variant in
            (('baseline','исходный v4','baseline_v4'),('refined','уточнение возбуждения','refined_v5'),
             ('enhanced','уточнение и дополнительные импульсы','enhanced_v5')))
    audio_html=[]
    for name,label,p,variant in players:
        clips=[read_wav(output/c/'original.wav' if p is None else output/c/str(p)/(variant+'.wav')) for c in CASES]
        pieces=[]
        for i,clip in enumerate(clips):
            if i:pieces.append(gap)
            pieces.append(clip)
        pcm=np.concatenate(pieces);path=listening/(name+'.wav');sf.write(path,pcm,8000,subtype='PCM_16')
        need(np.array_equal(read_wav(path,140000),pcm),'Written playlist changed PCM')
        audio_html.append(f'<section><h2>{html.escape(label)}</h2><audio controls preload="none" src="{name}.wav"></audio></section>')
    table=[]
    names={'baseline_v4':'Исходный v4','exact_v5':'Точная упаковка v5','refined_v5':'Уточнение v5','enhanced_v5':'Доп. импульсы v5'}
    for p in PROFILES:
        for variant in VARIANTS:
            r=result['profiles'][str(p)][variant]
            table.append(f'<tr><td>{p}</td><td>{names[variant]}</td><td>{r["file_bytes"]["mean"]:.1f}</td>'
                f'<td>{r["ser_db"]["mean"]:.3f}</td><td>{r["stoi"]["mean"]:.4f}</td>'
                f'<td>{r["mean_decode_wall_cycles"]["mean"]:.2f}</td><td>{r["underruns"]}</td></tr>')
    page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>LPX: компактная упаковка и качество</title><style>body{font:17px/1.5 system-ui;max-width:1100px;margin:30px auto;padding:0 20px;background:#f5f7fa;color:#182535}section{background:white;padding:12px 20px;margin:12px 0;border-radius:10px}audio{width:100%}table{border-collapse:collapse;background:white}th,td{padding:8px;border-bottom:1px solid #d6dce4;text-align:right}td:nth-child(2){text-align:left}.table{overflow:auto}</style>
<h1>Компактная речь LPX</h1><p>Четыре одинаковые полные записи по 4 секунды; между ними 0,5 секунды тишины. Каждая дорожка длится 17,5 секунды. Коэффициенты спектра одинаковы во всех вариантах. Усиление и временной сдвиг не подгонялись.</p>
<p>Точная упаковка v5 побитово сохраняет PCM/PWM исходного v4, поэтому отдельный плеер ей не нужен. Уточнение и дополнительные импульсы меняют возбуждение и проверяются по полным SSE/STOI. Это предварительные результаты четырёх голосов, без человеческих оценок прослушивания и без физической платы.</p>'''+''.join(audio_html)+'''
<h2>Средние по четырём записям</h2><div class="table"><table><tr><th>кбит/с</th><th>Вариант</th><th>Файл, байт</th><th>SER дБ</th><th>STOI</th><th>Wall тактов/отсчёт</th><th>Underrun</th></tr>'''+''.join(table)+'''</table></div>
<p>Бюджеты полного файла: 2020/3020 байт, включая 22-байтный header v5. Меньший поток сам по себе не означает меньшую прошивку: новый parser требует Flash/SRAM. Полные числа, net Flash и stack high-water после ready — в <a href="summary.json">обезличенном JSON</a>.</p>
<p>ATmega328P 16 МГц, вывод8 кГц, queue512/prefill384/unroll9, явный ASM, активные IRQ. Wall cycles включают измерительную обвязку. Длинные C fallback controls сохраняют полезный PWM; пропуски и пригодность real-time показаны отдельно в JSON.</p></html>'''
    save(listening/'summary.json',result);(listening/'index.html').write_bytes(page.encode())
    save(output/'summary.json',result)
    print('Validated all32 AVR images and six continuous-state controls; wrote anonymous summary/listening package.',flush=True)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='mode',required=True)
    prep=sub.add_parser('prepare')
    prep.add_argument('--baseline',type=Path,default=Path('build/lpx-speech/comparison'))
    prep.add_argument('--refined',type=Path,default=Path('build/lpx-speech-compact/refinement/pass2-320'))
    prep.add_argument('--enhanced',type=Path,default=Path('build/lpx-speech-compact/enhanced'))
    prep.add_argument('--output',type=Path,default=Path('build/lpx-speech-compact/study'))
    parsers={name:sub.add_parser(name) for name in ('avr','stress','summarize')}
    for parser in parsers.values():
        parser.add_argument('--output',type=Path,default=Path('build/lpx-speech-compact/study'))
        for name in ('avr-bin','runner','lib'):parser.add_argument('--'+name,type=Path,required=True)
        parser.add_argument('--wsl',default=None)
    parsers['avr'].add_argument('--shard',type=int,default=0);parsers['avr'].add_argument('--shards',type=int,default=1)
    parsers['avr'].add_argument('--cases',choices=CASES,nargs='+',default=CASES)
    parsers['avr'].add_argument('--profiles',type=int,choices=PROFILES,nargs='+',default=PROFILES)
    parsers['avr'].add_argument('--variants',choices=VARIANTS,nargs='+',default=VARIANTS)
    args=vars(ap.parse_args());mode=args.pop('mode')
    globals()[mode](**args)


if __name__=='__main__':main()
