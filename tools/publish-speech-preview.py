"""Export the retained best Q5 speech model and its exact PCM for the website.

Reproduce with --source-root pointing at the speech-quality checkout at the
recorded commit. --check only needs Python's standard library.
"""
import argparse
import array
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'web-player/audio/speech-previews'
SOURCE_COMMIT='9f7fff6a77ab05e8060e3bffff8a31983b69a35a'
MODEL='ATtiny13A/Sound/research/q4-pulse-shapes/head5/best-intelligibility-model.json'
REPORT='ATtiny13A/Sound/research/q4-pulse-shapes/head5/report.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def write_wav(path,values,rate):
    data=array.array('h',map(int,values))
    if sys.byteorder!='little':data.byteswap()
    with wave.open(str(path),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(rate);audio.writeframes(data.tobytes())


def check():
    manifest=json.loads((OUTPUT/'manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['entries']:
        for url,key,rate in ((entry['audioUrl'],'audioSha256',7500),(entry['playbackUrl'],'playbackSha256',44100)):
            path=ROOT/'web-player'/url
            if sha(path)!=entry[key]:raise ValueError('Preview audio hash mismatch')
            with wave.open(str(path),'rb') as audio:
                if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate())!=(1,2,rate):raise ValueError('Unexpected preview WAV format')
                if abs(audio.getnframes()/rate-entry['samples']/7500)>1/rate:raise ValueError('Preview duration changed')
                if rate==7500:
                    values=array.array('h',audio.readframes(audio.getnframes()))
                    if sys.byteorder!='little':values.byteswap()
                    if any(x%256 for x in values):raise ValueError('Canonical preview no longer matches 8-bit decoder output')
                    pcm=bytes(x//256+128 for x in values)
                    if hashlib.sha256(pcm).hexdigest()!=entry['pcmSha256']:raise ValueError('Preview is not the measured decoder output')
        if sha(OUTPUT/'vinni-q5-model.json')!=entry['modelSha256']:raise ValueError('Preview model changed')
    print('Verified exact Q5 PCM, retained model and mobile listening copy.')


def export(source):
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()!=SOURCE_COMMIT:
        raise ValueError('Use the recorded speech-quality commit '+SOURCE_COMMIT)
    for path in ('tools/fit-mixed-lattice.py','ATtiny13A/Sound/codec/mixed_lattice.py','ATtiny13A/Sound/codec/q4_phase_wave.py'):
        expected=subprocess.check_output(['git','show',SOURCE_COMMIT+':'+path],cwd=source)
        if (source/path).read_text(encoding='utf-8')!=expected.decode('utf-8').replace('\r\n','\n'):
            raise ValueError('Numerical decoder source has uncommitted changes: '+path)
    spec=importlib.util.spec_from_file_location('website_q5_fit',source/'tools/fit-mixed-lattice.py')
    fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)
    import numpy as np
    import scipy
    from scipy.signal import resample_poly
    model=source/MODEL;report=json.loads((source/REPORT).read_text(encoding='utf-8'))
    state,bits,state_bits,mode,_,_,meta=fit.load(model);pcm,counts=fit.render(state,bits,state_bits,mode)
    score=report['best_intelligibility'];pcm_hash=hashlib.sha256(pcm.tobytes()).hexdigest()
    if counts.any() or pcm_hash!=score['pcm_sha256']:raise ValueError('Best retained model no longer reproduces the measured PCM')
    original=ROOT/'web-player/audio/originals/vinni.wav'
    if sha(original)!=meta['reference_sha256']:raise ValueError('Website original differs from the measured reference')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    raw=(pcm.astype(np.int16)-128)*256;write_wav(OUTPUT/'vinni-q5.wav',raw,7500)
    playback=np.clip(np.rint(resample_poly(raw.astype(float),147,25)),-32768,32767).astype(np.int16)
    write_wav(OUTPUT/'vinni-q5-playback.wav',playback,44100)
    (OUTPUT/'vinni-q5-model.json').write_bytes(model.read_bytes())
    details=dict(schema=1,sourceCommit=SOURCE_COMMIT,modelPath=MODEL,modelSha256=sha(model),
        referenceSha256=meta['reference_sha256'],metrics=score,fullPlayerImplemented=False,flashQualified=False)
    (OUTPUT/'vinni-q5.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    entry=dict(id='vinni-q5',firmwareId='hq4-vinni',title='Винни-Пух · улучшенная речь Q5',
        audioUrl='./audio/speech-previews/vinni-q5.wav',audioSha256=sha(OUTPUT/'vinni-q5.wav'),
        playbackUrl='./audio/speech-previews/vinni-q5-playback.wav',playbackSha256=sha(OUTPUT/'vinni-q5-playback.wav'),
        pcmSha256=pcm_hash,samples=len(pcm),sampleRate=7500,stoi=score['stoi'],spectrogramLoss=score['spectrogram_loss'],
        modelSha256=sha(model),reportUrl='./audio/speech-previews/vinni-q5.json',
        researchUrl='https://github.com/Witali/MicroMusic/blob/'+SOURCE_COMMIT+'/ATtiny13A/Sound/research/q4-pulse-shapes/README.md',
        releaseStatus='pc-prototype',flashQualified=False)
    manifest=dict(schema=1,generator='tools/publish-speech-preview.py',sourceCommit=SOURCE_COMMIT,
        listeningResampler=dict(name='scipy.signal.resample_poly',version=scipy.__version__,up=147,down=25,window=['kaiser',5.0]),entries=[entry])
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    check()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-root',type=Path);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.check:check()
    elif args.source_root:export(args.source_root.resolve())
    else:parser.error('--source-root is required when exporting')
