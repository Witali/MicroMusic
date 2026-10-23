"""Make an unchanged-level original/previous/current listening comparison.

Both firmware inputs must be actual three-engine-qualified raw captures.
No highpass, gain/RMS matching, clipping, normalization or smoothing is used.
"""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import shutil
import wave

import numpy as np
import soundfile as sf


def sha(data):
    return hashlib.sha256(data).hexdigest()


def qualified_phrase(folder,samples):
    report = json.loads((folder/'build.json').read_text(encoding='utf-8'))
    v = report.get('verification',{})
    if (report.get('status') != 'verified' or not v.get('pass')
            or set(v.get('engines',[])) != {'reference','wasm','wasm-unoptimized'}
            or v.get('phraseSamples') != samples or v.get('verifiedSamples') != samples*3
            or v.get('silenceSamplesVerified') != samples*2 or v.get('mismatches') != 0
            or v.get('lostOverflows') != 0 or v.get('missedSamples') != 0):
        raise ValueError('Listening requires matching full three-engine one-shot verification')
    for name,key in [('firmware.bin','imageSha256'),('eeprom.bin','eepromSha256')]:
        if sha((folder/name).read_bytes()) != report[key]:
            raise ValueError('Firmware/EEPROM hash differs from its actual verification')
    raw = (folder/'actual.raw').read_bytes()
    if len(raw) != samples*3 or sha(raw) != v['actualPcmSha256'] or raw[samples:] != bytes([128])*(samples*2):
        raise ValueError('Actual raw capture/silence does not match its complete verification')
    return raw[:samples],dict(build_sha256=sha((folder/'build.json').read_bytes()),
        image_sha256=report['imageSha256'],phrase_pcm_sha256=sha(raw[:samples]),
        full_actual_pcm_sha256=sha(raw),flash_bytes=report['flashBytes'],eeprom_bytes=report['eepromBytes'],
        verified_samples=v['verifiedSamples'],silence_samples=v['silenceSamplesVerified'],engines=v['engines'])


def run(reference_path,previous,current,output,*,previous_label='Previous cycle02',current_label='Stronger balanced',pause_seconds=.3):
    original,sr = sf.read(reference_path,dtype='float64')
    if sr != 7500 or original.ndim != 1 or not np.all(np.isfinite(original)) or not 0 <= pause_seconds <= 5:
        raise ValueError('Expected unchanged finite mono7500Hz original and a bounded pause')
    samples = len(original)
    before,before_proof = qualified_phrase(previous,samples)
    after,after_proof = qualified_phrase(current,samples)
    output.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(reference_path,output/'01-original.wav')
    for name,raw in [('02-previous.wav',before),('03-current.wav',after)]:
        with wave.open(str(output/name),'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(1)
            wav.setframerate(sr)
            wav.writeframes(raw)
        decoded,rate = sf.read(output/name,dtype='float64')
        if rate != sr or not np.array_equal(decoded,(np.frombuffer(raw,np.uint8).astype(float)-128)/128):
            raise AssertionError('Individual WAV changed an actual unsigned DAC sample')
    pause = np.zeros(round(pause_seconds*sr),np.float32)
    clips = [original,(np.frombuffer(before,np.uint8).astype(float)-128)/128,
        (np.frombuffer(after,np.uint8).astype(float)-128)/128]
    comparison = np.concatenate([clips[0],pause,clips[1],pause,clips[2]]).astype(np.float32)
    sf.write(output/'04-comparison-raw.wav',comparison,sr,subtype='FLOAT')
    reloaded,rate = sf.read(output/'04-comparison-raw.wav',dtype='float32')
    if rate != sr or not np.array_equal(reloaded,comparison):
        raise AssertionError('Sequential FLOAT comparison changed stored PCM samples')
    labels = ['Original',previous_label,current_label]
    files = ['01-original.wav','02-previous.wav','03-current.wav']
    segments = [dict(label=label,file=name,start_sample=i*(samples+len(pause)),samples=samples,
        source_pcm_f32_sha256=sha(audio.astype('<f4').tobytes())) for i,(label,name,audio) in enumerate(zip(labels,files,clips))]
    report = dict(schema='q3-raw-listening-v1',sample_rate=sr,phrase_samples=samples,pause_samples=len(pause),
        original_sha256=sha(reference_path.read_bytes()),original_file_byte_exact=True,
        previous=before_proof,current=after_proof,segments=segments,comparison_samples=len(comparison),
        comparison_processing='Unchanged original/actual DAC levels and DC; noHP/RMS/gain/clipping; zero pauses only; FLOAT32 storage',
        source_sha256_normalized_lf=sha(Path(__file__).read_bytes().replace(b'\r\n',b'\n')),
        files={path.name:dict(sha256=sha(path.read_bytes()),bytes=path.stat().st_size) for path in sorted(output.glob('*.wav'))})
    (output/'listening.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    cards = ''.join(f'<section><h2>{escape(label)}</h2><audio controls preload="metadata" src="{name}"></audio></section>' for label,name in zip(labels,files))
    page = '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Vinni: raw comparison</title><style>body{font:17px system-ui;max-width:820px;margin:40px auto;padding:0 20px;background:#171b22;color:#e7ebf3}section{padding:12px 20px;margin:14px 0;background:#242b35;border-radius:12px}audio{width:100%}h2{font-size:19px}p{line-height:1.5}</style><h1>Винни-Пух: сравнение</h1><p>Оригинал → предыдущий cycle02 → stronger balanced. Исходная громкость и смещение нуля сохранены.</p><section><h2>Все три подряд</h2><audio controls preload="metadata" src="04-comparison-raw.wav"></audio></section>'+cards+'</html>'
    (output/'index.html').write_text(page,encoding='utf-8')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--previous',required=True,type=Path,help='Actual qualified AVR build directory')
    p.add_argument('--current',required=True,type=Path,help='Actual qualified AVR build directory')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--previous-label',default='Previous cycle02')
    p.add_argument('--current-label',default='Stronger balanced')
    args = p.parse_args()
    run(args.reference,args.previous,args.current,args.output,previous_label=args.previous_label,current_label=args.current_label)


if __name__ == '__main__':
    main()
