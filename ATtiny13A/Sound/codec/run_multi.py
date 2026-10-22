#!/usr/bin/env python3
"""One command: two or more user-provided clips -> LPC2 reference -> TinyLPC fit ->
closed-loop search -> assemble ATtiny13A -> execute AVR HEX -> WAV and browser player.
No hardcoded 87-frame restriction; a too-large phrase is reported, not truncated.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, zipfile
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from model_lite import render
from model8 import render as render8
from perceptual import Evaluator,load_wav
from make_player import generate as make_player
R=Path(__file__).resolve().parent

def run(*args,cwd=R,env=None):
    print('+',' '.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),cwd=cwd,check=True,env=env)

def read_params(z):
    z=np.load(z);return (z[q].astype('int64') for q in ('K','P','E'))

def save_wav(p,x,sr=7500):
    arr=np.asarray(x,dtype=float)
    sf.write(p,np.clip(arr,-1,1),sr,subtype='PCM_16')

def clip_name(name):
    return {'xtuj-ntt':'Чего тебе нужно?','ne-otv':'Что ж ты не отвечаешь?','vinni':'Сова! Открывай! Медведь пришёл!'}.get(name,name)

def build_clip(name,source,budget,refine,only_existing,budget8):
    folder=R/name
    folder.mkdir(exist_ok=True,parents=True)
    firmware=folder/'firmware'
    if not only_existing:
        from prepare_source import convert
        prepared=convert(source,folder/'original.wav')
        run(sys.executable,R/'generate_lpc2_teacher.py','--source',prepared,'--out',folder)
        from generate_seed import generate
        generate(prepared,folder/'seed.npz')
        if not firmware.exists():shutil.copytree(R/'firmware_template',firmware)
        run(sys.executable,R/'optimize.py','--source',prepared,'--teacher',folder/'teacher_8000.wav',
            '--seed-params',folder/'seed.npz','--budget',budget,'--seed',2026,
            '--target','balanced','--output-dir',folder/'train')
        if refine:
            run(sys.executable,R/'optimize.py','--source',prepared,'--teacher',folder/'teacher_8000.wav',
                '--seed-params',folder/'train/optimized_parameters.npz','--budget',refine,'--seed',3055,
                '--target','balanced','--output-dir',folder/'refine')
    selected=(folder/'refine/optimized_parameters.npz') if (only_existing or refine>0) and (folder/'refine/optimized_parameters.npz').exists() else (folder/'train/optimized_parameters.npz')
    if not selected.exists():raise RuntimeError(f'{name}: missing trained checkpoint')
    if not firmware.exists():shutil.copytree(R/'firmware_template',firmware)
    shutil.copy2(selected,firmware/'best_parameters.npz')
    run(sys.executable,firmware/'package_stream.py',cwd=firmware)
    run(sys.executable,firmware/'build_firmware.py',cwd=firmware)
    K,P,E=read_params(selected)
    env=dict(os.environ,FRAMES=str(len(P)))
    run('node',firmware/'verify.js',cwd=firmware,env=env)
    final=np.fromfile(firmware/'emu_pwm_u8.raw',dtype='u1').astype('int16')-128
    predicted=render(K,P,E,len(P)*256)
    if not np.array_equal(final,predicted):raise ValueError(f'AVR and Python synthesis disagree for {name}')
    BK,BP,BE=read_params(folder/'seed.npz')
    baseline=render(BK,BP,BE,len(BP)*256)
    ev=Evaluator(load_wav(folder/'original.wav'),load_wav(folder/'teacher_8000.wav'))
    initial=ev.metrics(baseline);optimized=ev.metrics(final)
    print('METRICS',name,'STOI',round(initial['stoi'],5),'->',round(optimized['stoi'],5),flush=True)
    raw=firmware/'tinylpc.bin'
    report={'name':name,'phrase':clip_name(name),'initial':initial,'optimized':optimized,
        'flash':raw.stat().st_size,'speech':(firmware/'voice_tinylpc.bin').stat().st_size,
        'sample_rate':7500,'samples':len(final),'model_equals_AVR':True,
        'budget':budget,'refine':refine,'note':'LPC2 is teacher/reference; compiled decoder is 7-stage TinyLPC, NOT full LPC2 Improved.'}
    (folder/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    save_wav(folder/'baseline.wav',baseline/128.)
    save_wav(folder/'optimized_avr.wav',final/128.)

    # Experiment with the NEW 8-stage bitstream/decoder (one extra coefficient per frame).
    f8=folder/'format8';f8.mkdir(exist_ok=True)
    if not only_existing:
        K8=np.column_stack([K,np.zeros(len(K),dtype='int64')])
        np.savez(f8/'seed8.npz',K=K8,P=P,E=E)
        if not (f8/'firmware').exists():shutil.copytree(R/'format8',f8/'firmware')
        run(sys.executable,R/'optimize8.py','--source',folder/'original.wav',
            '--teacher',folder/'teacher_8000.wav','--seed-params',f8/'seed8.npz',
            '--budget',budget8,'--seed',4067,'--target','balanced','--output-dir',f8/'train')
    selected8=f8/'train/optimized_parameters.npz'
    if not selected8.exists():raise RuntimeError(f'{name}: missing 8-pole checkpoint')
    if not (f8/'firmware').exists():shutil.copytree(R/'format8',f8/'firmware')
    shutil.copy2(selected8,f8/'firmware/best_parameters.npz')
    run(sys.executable,f8/'firmware/package_stream.py',cwd=f8/'firmware')
    run(sys.executable,f8/'firmware/build_firmware.py',cwd=f8/'firmware')
    run('node',f8/'firmware/verify.js',cwd=f8/'firmware',env=env)
    K8,P8,E8=read_params(selected8)
    actual8=np.fromfile(f8/'firmware/emu_pwm_u8.raw',dtype='u1').astype('int16')-128
    if not np.array_equal(actual8,render8(K8,P8,E8,len(P8)*256)):
        raise AssertionError('8-pole model/AVR mismatch')
    metric8=ev.metrics(actual8)
    report['optimized8']=metric8
    report['flash8']=(f8/'firmware/tinylpc.bin').stat().st_size
    report['speech8']=(f8/'firmware/voice_tinylpc.bin').stat().st_size
    report['best_format']='LPC-8' if metric8['stoi']>=optimized['stoi'] and metric8['mel_original']<=optimized['mel_original'] else 'LPC-7'
    (folder/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    save_wav(f8/'optimized8.wav',actual8/128.)
    print('FORMAT COMPARISON',name,'7p',round(optimized['stoi'],5),'8p',round(metric8['stoi'],5),flush=True)
    return report

def assemble(groups,reports,include_winnie=True):
    dest=R/'release';dest.mkdir(exist_ok=True)
    listen=[]
    for groupname in groups:
        src=R/groupname
        folder=dest/groupname;folder.mkdir(exist_ok=True)
        keep={'source.wav':src/'original.wav','lpc2.wav':src/'teacher_8000.wav',
            'baseline.wav':src/'baseline.wav','optimized.wav':src/'optimized_avr.wav',
            'firmware.hex':src/'firmware/tinylpc.hex','firmware.bin':src/'firmware/tinylpc.bin',
            'voice.bin':src/'firmware/voice_tinylpc.bin','parameters.npz':src/'firmware/best_parameters.npz',
            'metrics.json':src/'metrics.json',
            'optimized8.wav':src/'format8/optimized8.wav','firmware8.hex':src/'format8/firmware/tinylpc.hex',
            'firmware8.bin':src/'format8/firmware/tinylpc.bin',
            'voice8.bin':src/'format8/firmware/voice_tinylpc.bin',
            'parameters8.npz':src/'format8/firmware/best_parameters.npz'}
        for key,source in keep.items():shutil.copyfile(source,folder/key)
        variants=[{'name':'Оригинальная запись','file':folder/'source.wav','wav_download':groupname+'/source.wav'},
                {'name':'Полный LPC2 Improved (ориентир)','file':folder/'lpc2.wav','wav_download':groupname+'/lpc2.wav'},
                {'name':'ATtiny13A — до обучения (HEX)','file':folder/'baseline.wav','wav_download':groupname+'/baseline.wav'},
                {'name':'ATtiny13A — LPC-7 после обучения (HEX)','file':folder/'optimized.wav','wav_download':groupname+'/optimized.wav'},
                {'name':'ATtiny13A — LPC-8, новый формат (HEX)','file':folder/'optimized8.wav','wav_download':groupname+'/optimized8.wav'}]
        listen.append({'title':clip_name(groupname),'desc':'Пять вариантов одной реплики: LPC2 — эталон, LPC-7 и LPC-8 — настоящие AVR-прошивки.',
            'variants':variants,'report':reports[groupname]})
    if include_winnie:
        w=Path('/mnt/data/MicroMusic_AutoLPC2/results/release')
        if (w/'optimized_avr.wav').exists():
            destw=dest/'vinni';destw.mkdir(exist_ok=True)
            for out,original in [('source.wav','original.wav'),('lpc2.wav','lpc2.wav'),('baseline.wav','baseline.wav'),('optimized.wav','optimized_avr.wav')]:
                shutil.copyfile(w/original,destw/out)
            variants=[{'name':txt,'file':destw/key,'wav_download':'vinni/'+key} for txt,key in
                    [('Оригинальная запись','source.wav'),('LPC2 Improved','lpc2.wav'),('ATtiny13A — прежний','baseline.wav'),('ATtiny13A — AutoLPC2','optimized.wav')]]
            listen.insert(0,{'title':clip_name('vinni'),'desc':'Предыдущий образец для сравнения с двумя новыми голосами.',
                'variants':variants,'report':{}})
    make_player(listen,dest/'index.html')
    # Provide A/B WAV previews that will work in ordinary audio players.
    pause=np.zeros(7500//4)
    for name in groups:
        samples=[]
        for variant in ('source.wav','baseline.wav','source.wav','optimized.wav','source.wav','optimized8.wav','lpc2.wav'):
            x=load_wav(dest/name/variant)
            pk=max(1e-9,np.max(np.abs(x)));rms=max(1e-9,np.sqrt(np.mean(x*x)))
            x*=min(.15/rms,.88/pk)
            samples.extend([x,pause])
        save_wav(dest/name/'AB.wav',np.concatenate(samples))
    return dest

def pack(clips,release):
    base=R/'MicroMusic_MultiPhrase'
    scripts=['run_multi.py','make_player.py','README.md','prepare_source.py','generate_seed.py',
            'generate_lpc2_teacher.py','optimize.py','optimize8.py','model_lite.py','model8.py','perceptual.py','lpc2_improved_encoder.html','evaluate_codebooks.py']
    firmware=['firmware_template/tinylpc.S','firmware_template/package_stream.py',
              'firmware_template/build_firmware.py','firmware_template/avr_emulator.js','firmware_template/verify.js',
              'format8/tinylpc.S','format8/package_stream.py','format8/build_firmware.py',
              'format8/avr_emulator.js','format8/verify.js']
    with zipfile.ZipFile(R/'MicroMusic_MultiPhrase_code_only.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for n in scripts+firmware:z.write(R/n,arcname=str(base.name+'/'+n))
    with zipfile.ZipFile(R/'MicroMusic_MultiPhrase_private.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        for n in scripts+firmware:z.write(R/n,arcname=str(base.name+'/'+n))
        for name,src in clips:
            if src.exists():z.write(src,arcname=f'{base.name}/inputs/{name}{src.suffix.lower()}')
            for relative in ['seed.npz','train/optimized_parameters.npz','refine/optimized_parameters.npz','format8/seed8.npz','format8/train/optimized_parameters.npz']:
                source=R/name/relative
                if source.exists():z.write(source,arcname=str(base.name+'/'+name+'/'+relative))
        if (R/'codebook_trial_report.json').exists():
            z.write(R/'codebook_trial_report.json',arcname=str(base.name+'/codebook_trial_report.json'))
        for f in release.rglob('*'):
            if f.is_file():z.write(f,arcname=str(base.name+'/release/'+str(f.relative_to(release))))
    print('Archives created',R/'MicroMusic_MultiPhrase_code_only.zip',R/'MicroMusic_MultiPhrase_private.zip')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--clip',action='append',metavar='NAME=PATH',help='one or more input MP3 or WAV clips, repeated')
    ap.add_argument('--budget',type=int,default=1200)
    ap.add_argument('--refine',type=int,default=3000)
    ap.add_argument('--budget8',type=int,default=4000,help='Tests for additional 8-stage LPC coefficient')
    ap.add_argument('--reuse-existing',action='store_true',help='reuse already prepared and trained NPZ (still rebuild/verify firmware)')
    ap.add_argument('--no-winnie',action='store_true')
    args=ap.parse_args()
    if args.clip: clips=[(v.split('=',1)[0],Path(v.split('=',1)[1]).resolve()) for v in args.clip]
    else:clips=[('xtuj-ntt',Path('/mnt/data/xtuj-ntt.mp3')),('ne-otv',Path('/mnt/data/ne-otv.mp3'))]
    reports={}
    for name,src in clips:
        if not src.exists() and not args.reuse_existing:raise FileNotFoundError(src)
        reports[name]=build_clip(name,src,args.budget,args.refine,args.reuse_existing,args.budget8)
    release=assemble(list(reports),reports,include_winnie=not args.no_winnie)
    pack(clips,release)
    print('COMPLETED',release/'index.html',flush=True)

if __name__=='__main__':main()
