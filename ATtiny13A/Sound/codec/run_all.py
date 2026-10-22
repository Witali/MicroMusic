#!/usr/bin/env python3
"""ONE-COMMAND MicroMusic LPC2->ATtiny13A auto optimization pipeline.

1. Prepare source (MP3/WAV) and an LPC2 Improved teacher automatically.
2. If a new phrase, derive a quantized initial LPC parameter stream.
3. Run closed-loop perceptual optimization with AVR-exact DSP and guardrails.
4. Choose the best non-regressing preset; pack and compile AVR firmware.
5. Execute the HEX independently through JS AVR emulator; byte-compare outputs.
6. Generate a self-contained A/B listening webpage, WAV, and JSON report.

This is a fixed-phrase teacher/student *approximation*, NOT a bitstream-
compatible LPC2 decoder. Audio inputs belong to the user; output speech files
are intended for private research and need rights review before public upload.
"""
from __future__ import annotations
import argparse, base64, html, json, os, shutil, subprocess, sys
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from model_lite import render,reference_selftest
from perceptual import Evaluator,load_wav
ROOT=Path(__file__).resolve().parent
FS=7500

def shell(*cmd,env=None):
    print('+',' '.join(map(str,cmd)),flush=True)
    p=subprocess.run([str(a) for a in cmd],cwd=ROOT,env=env,check=True,text=True)

def gain_match(arr,target=.13):
    y=np.asarray(arr,dtype=float)
    if len(y)==0:return y
    pk=np.max(np.abs(y));rms=np.sqrt(np.mean(y*y))
    if pk<1e-7:return y
    return y*min(target/max(rms,1e-5),.96/max(pk,1e-5))

def save_wav(path,a,sr=FS):
    sf.write(path,np.asarray(a,dtype=np.float64),sr,subtype='PCM_16')

def build_html(out,metrics,sources):
    variants=[('Оригинал',out/'original.wav'),('LPC2 Improved',out/'lpc2.wav'),
              ('ATtiny13A — начальный вариант',out/'baseline.wav'),('ATtiny13A — оптимизированный HEX',out/'optimized_avr.wav')]
    links=[]
    for name,filepath in variants:
        encoded=base64.b64encode(filepath.read_bytes()).decode('ascii')
        links.append((html.escape(name),f'data:audio/wav;base64,{encoded}'))
    rows='\n'.join(f'<tr><td>{html.escape(k)}</td><td>{metrics["baseline"][k]:.4f}</td><td>{metrics["optimized"][k]:.4f}</td></tr>' for k in ['stoi','mel_original','mel_lpc2','envelope','max_step','clicks_48','clicks_60'])
    plays='\n'.join(f'<div class="track"><div class="label">{name}</div><audio controls preload="none" src="{url}"></audio></div>' for name,url in links)
    webpage='''<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MicroMusic — LPC2 Teacher / ATtiny13A Student</title><style>
:root{font-family:system-ui,sans-serif;color-scheme:dark}body{max-width:850px;padding:16px;margin:auto;background:#111827;color:#eef3ff;line-height:1.5}
h1{font-size:clamp(24px,5vw,34px)}p{color:#c5d0e2}.track{border:1px solid #364457;background:#1c283a;padding:14px 16px;margin:12px 0;border-radius:12px}
.label{font-weight:700;margin-bottom:8px}audio{width:100%}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:9px;border-bottom:1px solid #39485a;text-align:right}td:first-child,th:first-child{text-align:left}
footer{font-size:13px;color:#abb9d0}a{color:#9eceff}
</style></head><body><h1>MicroMusic · LPC2 → ATtiny13A</h1><p>Автоматическая оптимизация LPC с обратной связью. Сравнение оригинала, полного LPC2 Improved, начальной AVR-прошивки и автоматически подобранной AVR-прошивки. Для равных условий клипы нормированы по RMS с ограничением пиков.</p>
'''+plays+'''<h2>Объективные метрики (ниже лучше, кроме STOI)</h2><table><thead><tr><th>Показатель</th><th>Было</th><th>Стало</th></tr></thead><tbody>'''+rows+'''</tbody></table>
<p>AVR-проигрывание проверено независимым интерпретатором инструкций; здесь для удобства воспроизводится сохранённый результат этой проверки. Другие проигрыватели, фильтры и громкоговорители могут звучать иначе.</p>
<footer>Для частной проверки; оригинальная реплика из мультфильма не предназначена для публикации без разрешения.</footer></body></html>'''
    (out/'index.html').write_text(webpage,encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,default=ROOT/'references/original_reference.wav',help='Audio clip; MP3, WAV, and other ffmpeg-supported formats')
    ap.add_argument('--trim',help='Manual start:end seconds; by default custom recordings are VAD-trimmed')
    ap.add_argument('--budget',type=int,default=2500,help='Candidate tests PER preset')
    ap.add_argument('--presets',default='balanced',help='Comma-separated optimization priorities: balanced,voice,lpc2')
    ap.add_argument('--teacher-wav',type=Path,help='Optional externally decoded LPC2 teacher WAV; otherwise run the original LPC2 Improved HTML encoder automatically')
    ap.add_argument('--seed-params',type=Path,help='Optional saved initial K/P/E .npz')
    ap.add_argument('--candidate',type=Path,help='Resume a previously optimized .npz checkpoint; checked against current source/teacher before selection')
    ap.add_argument('--out',type=Path,default=ROOT/'results/current')
    a=ap.parse_args()
    out=a.out.resolve();out.mkdir(exist_ok=True,parents=True)
    reference=(ROOT/'references/original_reference.wav').resolve()
    source=a.input.resolve()
    if source==reference:
        prepared=reference
    else:
        from prepare_source import convert
        prepared=convert(source,out/'source_prepared.wav',a.trim)
    if a.teacher_wav:
        teacher=a.teacher_wav.resolve()
    else:
        shell(sys.executable,ROOT/'generate_lpc2_teacher.py','--source',prepared,'--out',out)
        teacher=out/'teacher_8000.wav'
    if a.seed_params:
        seed=a.seed_params.resolve()
    elif source==reference:
        seed=ROOT/'references/base_parameters.npz'
        assert reference_selftest(ROOT)==0
    else:
        from generate_seed import generate
        seed=generate(prepared,out/'fresh_seed.npz')
    from optimize import load_params,configure,accept_guard
    from perceptual import Evaluator
    x=load_wav(prepared);t=load_wav(teacher)
    ev=Evaluator(x,t)
    BK,BP,BE=load_params(seed)
    n=len(BP)*256
    base=ev.metrics(render(BK,BP,BE,n))
    choices=[('baseline',seed,base,ev.fitness(base,configure('balanced')))]
    if a.candidate:
        extra=a.candidate.resolve()
        C,CP,CE=load_params(extra)
        if C.shape!=BK.shape or len(CP)!=len(BP):raise ValueError('Checkpoint shape does not match source')
        cm=ev.metrics(render(C,CP,CE,n))
        valid=(cm['stoi']>=base['stoi']-0.0002 and cm['mel_original']<=base['mel_original']+1e-5
               and cm['max_step']<=base['max_step'] and cm['clicks_48']<=base['clicks_48']
               and cm['clicks_60']<=base['clicks_60'])
        print('CHECKPOINT',extra,'valid',valid,'metrics',cm,flush=True)
        if valid:choices.append(('checkpoint',extra,cm,ev.fitness(cm,configure('balanced'))))
    for j,preset in enumerate(a.presets.split(',')):
        preset=preset.strip()
        if not preset:continue
        if preset not in ('balanced','voice','lpc2'):raise ValueError('Invalid preset '+preset)
        candidate=out/('train_'+preset)
        shell(sys.executable,ROOT/'optimize.py','--source',prepared,'--teacher',teacher,
              '--seed-params',seed,'--budget',str(a.budget),'--seed',str(2026+j*17),
              '--target',preset,'--output-dir',candidate)
        zpath=candidate/'optimized_parameters.npz'
        K,P,E=load_params(zpath)
        m=ev.metrics(render(K,P,E,n))
        # Strict final selector: no STOI or original-spectrum regression.
        ok=(m['stoi']>=base['stoi']-0.0002 and
            m['mel_original']<=base['mel_original']+1e-5 and
            m['max_step']<=base['max_step'] and
            m['clicks_48']<=base['clicks_48'] and
            m['clicks_60']<=base['clicks_60'])
        s=ev.fitness(m,configure('balanced'))
        print('SELECTOR',preset,'passes quality gate',ok,'balanced score',round(s,6),flush=True)
        if ok:choices.append((preset,zpath,m,s))
    name,selected,m,_=max(choices,key=lambda row:row[-1])
    print('WINNER',name,selected,flush=True)
    shutil.copy2(selected,ROOT/'firmware/best_parameters.npz')
    # Finish on the actual MCU instruction sequence and check hard limits.
    shell(sys.executable,ROOT/'firmware/package_stream.py')
    shell(sys.executable,ROOT/'firmware/build_firmware.py')
    e=os.environ.copy();e['FRAMES']=str(len(BP))
    shell('node',ROOT/'firmware/verify.js',env=e)
    compiled=np.fromfile(ROOT/'firmware/emu_pwm_u8.raw',dtype='u1').astype('int16')-128
    K,P,E=load_params(selected)
    predicted=render(K,P,E,len(compiled))
    if not np.array_equal(predicted,compiled):
        ix=np.flatnonzero(predicted!=compiled)
        raise AssertionError(f'AVR emulation diverged from optimization model at {ix[:10]}')
    actual=ev.metrics(compiled)
    if not accept_guard(actual,base):raise AssertionError('Quality guard failed on HEX execution')
    size=(ROOT/'firmware/tinylpc.bin').stat().st_size
    speech_bytes=(ROOT/'firmware/voice_tinylpc.bin').stat().st_size
    if size>1024:raise AssertionError('Flash overflow')
    (out/'optimized.hex').write_bytes((ROOT/'firmware/tinylpc.hex').read_bytes())
    (out/'optimized.bin').write_bytes((ROOT/'firmware/tinylpc.bin').read_bytes())
    (out/'voice.bin').write_bytes((ROOT/'firmware/voice_tinylpc.bin').read_bytes())
    (out/'optimized_parameters.npz').write_bytes(selected.read_bytes())
    save_wav(out/'original.wav',gain_match(x))
    save_wav(out/'lpc2.wav',gain_match(t))
    baseline_pcm=render(BK,BP,BE,n)
    save_wav(out/'baseline.wav',gain_match(baseline_pcm/128.))
    save_wav(out/'optimized_avr.wav',gain_match(compiled/128.))
    pieces=[];pause=np.zeros(round(FS*0.3))
    for f in ['original.wav','baseline.wav','original.wav','optimized_avr.wav','lpc2.wav','optimized_avr.wav']:
        clip,sr=sf.read(out/f);pieces.extend([clip,pause])
    save_wav(out/'AB_comparison.wav',np.concatenate(pieces))
    report={'best_preset':name,'baseline':base,'optimized':actual,'flash_bytes':size,'speech_bytes':speech_bytes,
            'frame_count':len(BP),'samples':len(compiled),'model_vs_avr_mismatches':0,'voice_coded_format':'TinyLPC 7-pole RLE (not LPC2-bitstream-compatible)',
            'experimental':True,'notes':'Metrics measure matched digital sample outputs; listening quality/hardware must be evaluated separately.'}
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    build_html(out,report,[prepared,teacher])
    from package_project import package
    package(out,report_dir=out)
    print('PASS:',json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return report

if __name__=='__main__': main()
