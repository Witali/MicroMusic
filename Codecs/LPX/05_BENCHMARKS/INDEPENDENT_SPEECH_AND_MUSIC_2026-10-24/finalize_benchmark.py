from pathlib import Path
import sys,json,hashlib,subprocess,platform,base64,html,zipfile,shutil
import numpy as np,soundfile as sf
from run_ffmpeg_bench import metrics
R=Path(__file__).resolve().parent
SAMPLES={
 'english_dialogue_20s': {'title':'English conversation, two voices, 20 s','kind':'English speech','dir':'english','rights':'External bundled test sample; source recording license not separately verified. Original not redistributed.'},
 'saxophone_16s': {'title':'Saxophone solo, 16 s','kind':'Instrumental','dir':'sax','rights':'External bundled Gradio sample; recording license not separately verified. Original not redistributed.'},
 'synthetic_music_12s': {'title':'Synthetic polyphony, 12 s','kind':'Synthetic music','dir':'music12','rights':'Locally generated original using included deterministic Python script.'},
}
rows=[]
for sample,meta in SAMPLES.items():
    base=R/f'lpx3_{meta["dir"]}'
    x,sr=sf.read(R/'references'/f'{sample}.wav',dtype='float64');assert sr==8000
    duration=len(x)/sr
    for bits in (2,3,4):
        p=base/f'voice_v3_{bits}bit.lpx3';y,_=sf.read(base/f'voice_v3_{bits}bit.wav',dtype='float64')
        rows.append(dict(sample=sample,codec='LPX3 original',mode=f'{bits}-bit',seconds=duration,bytes=p.stat().st_size,actual_kbps=round(p.stat().st_size*8/1000/duration,3),**metrics(x,y,meta['kind']=='English speech')))
    for bits in ((3,) if meta["dir"]=="music12" else (2,3)):
        if bits==2:
            p=base/f'{meta["dir"]}_2bit.l4hy';src=base/f'{meta["dir"]}_lpx4_2bit.pcm'
        else:
            st={'english':'english_3bit','sax':'sax_3bit','music12':'music12_3bit'}[meta['dir']]
            p=base/f'{st}.l4hy';src=base/({'english':'english_lpx4_s16.pcm','sax':'sax_lpx4_s16.pcm','music12':'music12_lpx4_s16.pcm'}[meta['dir']])
        y=np.fromfile(src,dtype='<i2').astype(np.float64)/32768
        rows.append(dict(sample=sample,codec='LPX4 Q0 transcode',mode=f'from LPX3 {bits}-bit',seconds=duration,bytes=p.stat().st_size,actual_kbps=round(p.stat().st_size*8/1000/duration,3),**metrics(x,y,meta['kind']=='English speech')))
ff=json.loads((R/'results'/'ffmpeg_results.json').read_text())
for f in ff: rows.append(dict(sample=f['sample'],codec=f['codec'],mode=f"target {f['target_kbps']} kbps",seconds=f['seconds'],bytes=f['file_bytes'],actual_kbps=f['effective_kbps'],lag_samples=f['lag_samples'],ser_db=f['ser_db'],stoi=f.get('stoi')))
(R/'results'/'all_codecs.json').write_text(json.dumps({'sampling_hz':8000,'format':'16 bit PCM mono before analog PWM','samples':SAMPLES,'results':rows,'matching_experiments':json.loads((R/'results'/'matched_sizes.json').read_text())},ensure_ascii=False,indent=2)+'\n')
# reports
fver=subprocess.check_output(['ffmpeg','-version']).decode().splitlines()[0]
report=[
 '# MicroMusic LPX3/LPX4 vs Opus/AAC — independent samples',
 '',
 '2026-10-24. All measurements executed in this working environment, not extrapolated.',
 '',
 '## Materials',
 '',
 '| Sample | Duration | Source / license disclosure |',
 '|---|---:|---|',
 *[f'| {v["title"]} | {20 if n.startswith("english") else 16 if n.startswith("sax") else 12} s | {v["rights"]} |' for n,v in SAMPLES.items()],
 '',
 'The environment has no outbound DNS access; the previously selected Wikimedia/SoniqTools audio could not be downloaded. The independent English dialogue and sax samples were already installed in third-party audio packages; their raw or compressed content is deliberately omitted from the redistributable bundle. The synthetic musical stimulus is included.',
 '',
 '## Codec comparison: fixed modes',
 '',
 'All files compare against **the exact same 8 kHz mono signed PCM16 reference** per sample. SER = 10 log10(sum(ref^2)/sum((ref-decoded)^2)); align only integer lag ±160ms; no optimizing signal gain. STOI is standard at 8kHz and used only for English speech.',
 '',
 '| Sample | Codec | Mode | File B | Effective kb/s | SER dB | STOI |',
 '|---|---|---|---:|---:|---:|---:|',
]
for sample in SAMPLES:
 for r in rows:
  if r['sample']!=sample: continue
  if r['codec'] in ('Opus','AAC-LC') and r['mode'] not in ('target 16 kbps','target 24 kbps','target 32 kbps'):continue
  report.append(f"| {sample} | {r['codec']} | {r['mode']} | {r['bytes']} | {r['actual_kbps']:.2f} | {r['ser_db']:.2f} | {r.get('stoi') if r.get('stoi') is not None else '—'} |")
report.extend(['',
 '## Files matched by actual size',
 '',
 'These comparisons target the actual byte size of an LPX3/LPX4 stream, including AAC/Opus container. Codec target bitrate was tuned; it is not an exact 1:1 byte match.',
 '',
 '| Sample | Reference | Target B | Codec | Actual B | Delta % | SER dB | STOI |',
 '|---|---|---:|---|---:|---:|---:|---:|'])
for r in json.loads((R/'results'/'matched_sizes.json').read_text()):
 report.append(f"| {r['sample']} | {r['compare_to']} | {r['source_size']} | {r['codec']} | {r['bytes']} | {r['size_delta_percent']:+.2f}% | {r['ser_db']:.2f} | {r.get('stoi','—')} |")
report.extend(['',
 '## How LPX encodes were produced',
 '',
 '* LPX3: Universal encoder from preserved `train_encode.py --fast --no-trim` (LPC2 analysis + 2/3/4-bit closed-loop excitation); no pretrained per-speaker phrases used. This is **original LPX3**, not late AVR Rice v7.',
 '* LPX4: The corresponding original LPX3 streams were converted to L3AV (10-bit LSF), then `lpx4.encode(... fast=True, min_snr=inf)` packaged a **lossless exact-excitation pitch/Rice** format; waveform decoded by `Lpx4HybridCore::nextS16`. No extra rate-distortion search/LSF re-training of the Q0 encoder on these new stimuli was executed. Consequently these figures are a baseline for generalization, not a bound on LPX4 quality.',
 '* LPX4 input 4-bit mode was not benchmarked: long streams exceed the 16-bit stream-size field accepted by the current C++/AVR decoder. LPX3 4-bit mode is included using its independent desktop decoder.',
 '* These long LPC streams cannot fit, with decoder firmware, in the ATmega328P 32KB on-chip Flash. External audio storage or segmented streaming is necessary. Neither hardware decoding cycles at 16 MHz nor underruns have been checked.',
 '* AAC-LC and Opus are FFmpeg encodings at specified target bitrate; measured file byte sizes include container overhead. Opus -application audio -vbr on -compression_level 10.',
 '',
 '## Findings',
 '',
 '* At roughly 24-26 effective kb/s, Opus and AAC usually have higher waveform SER and (on dialogue) STOI than LPX3/LPX4 baseline. LPX4 often shrinks LPX3 data but quantized/integer LPC synthesis can notably increase waveform error on previously unseen speech/music.',
 '* One 12s synthetic-music sample does not substitute for a diverse acoustic music corpus. Copyright/source licensing needs checking before redistributing the bundled third-party recordings.',
 '* To assess final LPX4 Q0 fairly, finish universal WAV-to-Q0 LPC/LSF analysis and per-block excitation optimization without overfitting to the training phrases.',
 '',
 '## Reproduction',
 '',
 f'FFmpeg: `{fver}`',
 f'Python: `{platform.python_version()}`',
 '',
 '1. Use `run_ffmpeg_bench.py` on 8k reference WAVs to reproduce AAC/Opus. `match_size_benchmark.py` selects target kbps for byte-matched comparisons.',
 '2. Obtain the archived LPX3 original encoder `train_encode.py`, its LPC2 HTML and Chromium; command: `python train_encode.py --fast --no-trim --input input.wav --name name --out result_dir`.',
 '3. Use archived `encoder_vbr/tools/pack_lpx3_avr.py input_3bit.lpx3 output.l3av --coeff-bits 10 --representation lsf`, then convert via `tools/lpx4.py` and decode with `src/Lpx4HybridCore.cpp` + `tests/decode_s16_host.cpp`.',
 '4. `finalize_benchmark.py` constructs `all_codecs.json` from source artifacts. Two sample inputs can be found in local `pyannote.audio` and `gradio` installs in this testing environment, but the recording licenses were not verified and those audio files are not copied here.',
 '',
 '## Sources for separate permissively licensed corpus downloads',
 '',
 '- [Russian sayings, ~24s, PD-self](https://commons.wikimedia.org/wiki/File:Russian_sayings.ogg)',
 '- [English LibriSpeech, CC BY 4.0](https://us.openslr.org/12/)',
 '- [Bach Open Goldberg piano 30s, CC0](https://soniqtools.com/test-audio-files)',
 '- [Russian Mozilla Common Voice, CC0 but dataset re-hosting is restricted](https://mozilladatacollective.com/datasets/cmu5x45pn00dao107j4o9w2yv)',
])
(R/'REPORT_RU.md').write_text('\n'.join(report)+'\n')
# standalone audio A/B on music, only auto-generated source is redistributed
import soundfile as sf
m=R/'lpx3_music12'
y=np.fromfile(m/'music12_lpx4_s16.pcm',dtype='<i2')
sf.write(R/'decoded'/'music12_lpx4_16bit.wav',y,8000,subtype='PCM_16')
clips=[
 ('Original PCM16',R/'references'/'synthetic_music_12s.wav'),
 ('LPX3 3-bit',m/'voice_v3_3bit.wav'),
 ('LPX4 3-bit basis',R/'decoded'/'music12_lpx4_16bit.wav'),
 ('Opus ~24k target',R/'decoded'/'synthetic_music_12s_opus_24.wav'),
 ('AAC-LC ~24k target',R/'decoded'/'synthetic_music_12s_aaclc_24.wav')]
assert all(p.exists() for _,p in clips),clips
cards=[]
for title,p in clips:
 b=base64.b64encode(p.read_bytes()).decode('ascii')
 cards.append('<section><h3>'+html.escape(title)+'</h3><audio controls preload="none" src="data:audio/wav;base64,'+b+'"></audio></section>')
page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MicroMusic: sample A/B</title><style>body{font:16px system-ui;max-width:700px;margin:30px auto;padding:0 16px;background:#101820;color:#e9f1f5}section{border:1px solid #344455;background:#192833;border-radius:12px;padding:14px 20px;margin:14px 0}audio{width:100%}h1{font-size:24px}small{color:#b3c5d1}</style><h1>MicroMusic · A/B</h1><p>12-секундная синтетическая музыка, 8 кГц, 16 бит, моно. Каждый плеер содержит декодированный PCM; уровень усиления не выравнивался.</p>'''+''.join(cards)+'''<small>LPX4 здесь получен автоматической конверсией LPX3, не тонкой настройкой кодировщика под звук. Это диагностический тест.</small></html>'''
(R/'SYNTHETIC_MUSIC_AB.html').write_text(page)
# portable script and benchmark data; includes only self-made music WAV
bundle=R/'MicroMusic_Codec_Independent_Benchmark_2026-10-24.zip'
items=[R/'REPORT_RU.md',R/'SYNTHETIC_MUSIC_AB.html',R/'run_ffmpeg_bench.py',R/'match_size_benchmark.py',R/'finalize_benchmark.py',R/'results'/'all_codecs.json',R/'results'/'matched_sizes.json',R/'results'/'ffmpeg_results.json',R/'references'/'synthetic_music_12s.wav',R/'references'/'synthetic_music_24s.wav',R/'decoded'/'music12_lpx4_16bit.wav',m/'voice_v3_3bit.wav',R/'decoded'/'synthetic_music_12s_opus_24.wav',R/'decoded'/'synthetic_music_12s_aaclc_24.wav',R/'lpx3_music12'/'music12_3bit.l4hy',R/'lpx3_music12'/'voice_v3_3bit.lpx3']
with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for f in items:
  z.write(f,f.relative_to(R))
with zipfile.ZipFile(bundle) as z: assert z.testzip() is None
print('REPORT',R/'REPORT_RU.md',(R/'REPORT_RU.md').stat().st_size)
print('ZIP',bundle,bundle.stat().st_size)
print('HTML',R/'SYNTHETIC_MUSIC_AB.html',(R/'SYNTHETIC_MUSIC_AB.html').stat().st_size)
