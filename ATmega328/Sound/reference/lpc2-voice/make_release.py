#!/usr/bin/env python3
"""Build self-contained A/B player, WAV comparison files and release bundles."""
import os, json, zipfile, shutil
from pathlib import Path
import numpy as np
import soundfile as sf
from make_player import generate
R=Path(__file__).resolve().parent
DATA=Path(os.environ.get('MICROMUSIC_DATA_ROOT',R.parent/'MicroMusic_MultiPhrase'))
P=R/'release';P.mkdir(parents=True,exist_ok=True)
report=json.loads((R/'experiment_report.json').read_text())
groups=[]
for clip in ('xtuj-ntt','ne-otv','vinni'):
    d=P/clip;d.mkdir(exist_ok=True)
    mp={'xtuj-ntt':'«Чего тебе нужно?»','ne-otv':'«Что ж ты не отвечаешь?»','vinni':'«Сова, открывай! Медведь пришёл!»'}
    variants=[]
    def copy(src,name,pretty):
        dest=d/name;shutil.copyfile(src,dest)
        variants.append({'name':pretty,'file':dest,'wav_download':f'{clip}/{name}'})
    copy(DATA/'release'/clip/'source.wav','original.wav','Оригинальный голос')
    copy(DATA/'release'/clip/'lpc2.wav','lpc2_v1_old.wav','LPC2 Improved v1: старая версия (F₀ ≤ 420 Гц)')
    if clip!='vinni':
        for n,pr in [('adaptive_unguided_post10','Автоматический F₀ — LPC2 Voice v2'),('adaptive_source_pitch_post10','По F₀ оригинала — LPC2 Voice v2'),('adaptive_source_pitch_post35','Исходный постфильтр 35% — LPC2 Voice v2')]:
            copy(R/'samples'/f'{clip}_{n}.wav',f'{n}.wav',pr)
        # Copy self-describing v2 streams, metadata explicitly includes the pitch range.
        for n in ('adaptive_unguided_post10','adaptive_source_pitch_post10'):
            shutil.copyfile(R/'samples'/f'{clip}_{n}.lp2',d/f'{n}.lp2')
    best=report[clip]['best'];met=report[clip]['variants'][best]['metrics'];old=report[clip]['old']['metrics']
    desc=(f'Было → стало: STOI {old["stoi"]:.3f} → {met["stoi"]:.3f}; '
          f'спектральная ошибка {old["spectral_error"]:.3f} → {met["spectral_error"]:.3f}. '
          'v2 хранит индивидуальный диапазон F₀ в LPC2-файле.' if clip!='vinni' else
          'Для этой записи старый LPC2 v1 пока точнее по спектру; замена кодека не обязательна.')
    groups.append({'title':mp[clip],'desc':desc,'variants':variants})
    if clip!='vinni':
        sr=7500;sequence=[];pause=np.zeros(sr//5)
        for name in ('original.wav','lpc2_v1_old.wav','original.wav','adaptive_unguided_post10.wav','original.wav','adaptive_source_pitch_post10.wav'):
            x,fs=sf.read(d/name)
            if fs!=sr:
                from scipy.signal import resample_poly
                import math
                g=math.gcd(fs,sr);x=resample_poly(x,sr//g,fs//g)
            pk=max(float(np.max(np.abs(x))),1e-9);rms=max(float(np.sqrt(np.mean(x*x))),1e-9)
            x=np.clip(x*min(.16/rms,.9/pk),-1,1)
            sequence.extend((x,pause))
        sf.write(d/'AB.wav',np.concatenate(sequence),sr,subtype='PCM_16')
# This script uses the previously fixed Web Audio implementation.
generate(groups,P/'index.html')
for name in ('README.md','README_RU.md','experiment_report.json','LPC2_Voice_v2.html'):
    shutil.copyfile(R/name,P/name)
common=['README.md','README_RU.md','requirements.txt','build_encoder.py','run_experiments.py','make_release.py','make_player.py','lpc2_v11_original.html','LPC2_Voice_v2.html']
with zipfile.ZipFile(R/'MicroMusic_LPC2_Voice_v2_code.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for n in common:z.write(R/n,arcname='MicroMusic_LPC2_Voice_v2/'+n)
with zipfile.ZipFile(R/'MicroMusic_LPC2_Voice_v2_private.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for n in common+['experiment_report.json']:z.write(R/n,arcname='MicroMusic_LPC2_Voice_v2/'+n)
    for f in P.rglob('*'):
        if f.is_file():z.write(f,arcname='MicroMusic_LPC2_Voice_v2/release/'+str(f.relative_to(P)))
    for clip in ('xtuj-ntt','ne-otv'):
        src=DATA/clip/'teacher.lp2'
        if src.exists():z.write(src,arcname=f'MicroMusic_LPC2_Voice_v2/release/{clip}/old_v1.lp2')
    # The older sample is not included twice.
print('Release',P/'index.html')
