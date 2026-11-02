"""Prepare LPX comparisons from the player's already-public speech recordings."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import shutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/shared-speech')
    parser.add_argument('--retain',action='store_true',help='Copy validated public LPX/WAV assets into the shared player')
    args=parser.parse_args()
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    from batch_decoder import BatchSession
    from speech_v4 import encode
    from speech_compact import repack,decode_model
    from standard_metrics import pwm_duties
    player=ROOT/'web-player'
    definitions=[('chego','Чего тебе нужно?'),('otvechaesh','Что ж ты не отвечаешь?'),
                 ('vinni','Сова! Открывай! Медведь пришёл!')]
    clips=[]
    with BatchSession('batch',speech=True,speech_compact=True) as common, BatchSession(
            'batch',speech=True,speech_compact=True,compact_only=True) as only:
        for clip_id,title in definitions:
            source=player/'audio/originals'/(clip_id+'.wav')
            pcm,rate=sf.read(source,dtype='int16')
            if rate!=7500 or pcm.ndim!=1:raise ValueError('Unexpected canonical source')
            reference=np.clip(np.rint(resample_poly(pcm.astype(float),16,15)),-32768,32767).astype(np.int16)
            destination=args.output/clip_id;destination.mkdir(parents=True,exist_ok=True)
            sf.write(destination/'reference.wav',reference,8000,subtype='PCM_16')
            variants=[]
            for variant_id,profile,label in [('compact',4,'Компактный'),('quality',6,'Повышенное качество')]:
                stream_path=destination/(variant_id+'.lpx')
                seed,decoded,_=encode(reference,profile,common)
                stream,_=repack(seed)
                np.testing.assert_array_equal(decoded,decode_model(stream))
                np.testing.assert_array_equal(decoded,common.decode_one_s16(stream,len(reference)))
                np.testing.assert_array_equal(decoded,only.decode_one_s16(stream,len(reference)))
                stream_path.write_bytes(stream)
                pwm=pwm_duties(decoded)
                sf.write(destination/(variant_id+'.wav'),(pwm.astype(np.int16)-128)*256,8000,subtype='PCM_16')
                variants.append(dict(id=variant_id,label=label,profile=profile,
                    audio=f'audio/lpx-speech/{clip_id}/{variant_id}.wav',stream=f'audio/lpx-speech/{clip_id}/{variant_id}.lpx',
                    bytes=len(stream),bitrateBps=len(stream)*8*8000/len(reference)))
                print(f'{clip_id}/{variant_id}: {len(stream)} bytes, {len(reference)} samples; model/common/v5-only exact',flush=True)
            clips.append(dict(schemaVersion=1,clipId=clip_id,title=title,codec='LPX',sampleRate=8000,
                samples=len(reference),durationSeconds=len(reference)/8000,previewKind='native-pwm8',
                reference=dict(audio=f'audio/originals/{clip_id}.wav',playback=f'audio/originals/playback/{clip_id}.wav',
                               sourceSha256=sha(source.read_bytes()),label='Исходная запись'),variants=variants))
    bread=json.loads((player/'audio/lpx-bread/manifest.json').read_text(encoding='utf-8'))
    clips.append(dict(bread,clipId='bread'))
    (args.output/'manifest.json').write_text(json.dumps(dict(schemaVersion=1,clips=clips),ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    if args.retain:
        for clip in clips[:3]:
            destination=player/'audio/lpx-speech'/clip['clipId'];destination.mkdir(parents=True,exist_ok=True)
            for variant in clip['variants']:
                for extension in ('lpx','wav'):
                    filename=variant['id']+'.'+extension
                    shutil.copyfile(args.output/clip['clipId']/filename,destination/filename)
        sources=[Path(__file__),*[ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'/name for name in
                 ('speech_v4.py','speech_compact.py','q0_model.py','wav_lpc.py','standard_metrics.py')]]
        retained=dict(schemaVersion=1,clips=clips[:3],generator='tools/prepare-shared-speech.py',
            sourceSha256NormalizedLF={p.relative_to(ROOT).as_posix():sha(p.read_text(encoding='utf-8').encode()) for p in sources})
        (player/'audio/lpx-speech/manifest.json').write_text(json.dumps(retained,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':main()
