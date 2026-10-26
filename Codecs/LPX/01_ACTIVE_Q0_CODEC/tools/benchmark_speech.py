"""Local, common-signal speech comparison. Media and provenance stay in build/."""
import argparse, hashlib, json, shutil, time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from speech_v4 import encode
from encode_lowrate import encode_lowrate
from standard_metrics import compare, pwm_duties
from benchmark_standards import external_encoder, score_external, save


def sha(b):return hashlib.sha256(b).hexdigest()


def run(corpus,output,ids,lpx8_root=None):
    corpus,output=Path(corpus),Path(output);output.mkdir(parents=True,exist_ok=True)
    sources=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    report={'protocol':'Same full PCM16/8kHz signals; no gain fitting; known LPX sample shift zero; external alignment preserves full reference.',
        'trained_codebooks':False,'human_listening_scores_collected':False,
        'physical_hardware_measured':False,'cases':[]}
    with BatchSession('batch',v3_features=24,speech=True) as decoder:
        for index,key in enumerate(ids):
            folder=output/f'case-{index+1:02d}';folder.mkdir(exist_ok=True)
            reference,rate=sf.read(corpus/key/'reference.wav',dtype='int16')
            assert rate==8000 and reference.shape==(32000,)
            source=next(c for c in sources['cases'] if c['id']==key)
            assert sha(reference.astype('<i2').tobytes())==source['reference_sha256']
            sf.write(folder/'original.wav',reference,8000,subtype='PCM_16')
            sf.write(folder/'encoder-tail.wav',np.r_[reference,np.zeros(640,np.int16)],8000,subtype='PCM_16')
            # Source names and attribution are local only, not copied into the
            # compact aggregate intended for a repository commit.
            save(folder/'private-provenance.json',{'case':source,'catalog_sources':sources['sources']})
            row={'id':folder.name,'reference_sha256':source['reference_sha256'],'samples':len(reference),
                 'language':key[:2],'profiles':{},'standards':{}}
            for profile in (4,6,8):
                stream=folder/f'lpx{profile}.l4hy';wav=stream.with_suffix('.wav')
                if stream.exists():
                    blob=stream.read_bytes();pcm=decoder.decode_one_s16(blob,len(reference))
                    meta=json.loads(stream.with_suffix('.json').read_text(encoding='utf-8'))
                    if meta['reference_sha256']!=row['reference_sha256'] or sha(blob)!=meta['stream_sha256']:
                        raise ValueError('Stale local cache; remove this output profile explicitly')
                else:
                    if profile in (4,6):blob,pcm,meta=encode(reference,profile,decoder)
                    else:
                        previous=Path(lpx8_root)/key/'8000-enhanced.l4hy' if lpx8_root else None
                        if previous and previous.exists():
                            blob=previous.read_bytes();pcm=decoder.decode_one_s16(blob,len(reference))
                            meta={'source':'retained original encoder LPX8','version':blob[4]}
                        else:
                            blob,pcm,meta=encode_lowrate(reference,decoder,4020,'speech','target',
                                lambdas=(.001,.01,.1,1.),refinement_trials=2)
                            if blob is None:raise ValueError('Original LPX8 encoder could not fit')
                    assert pcm is not None
                    meta.update(reference_sha256=row['reference_sha256'],stream_sha256=sha(blob))
                    stream.write_bytes(blob);save(stream.with_suffix('.json'),meta)
                assert pcm is not None and len(pcm)==len(reference)
                assert np.array_equal(decoder.decode_one(blob,len(reference)),pwm_duties(pcm))
                sf.write(wav,pcm,8000,subtype='PCM_16')
                metrics,_=compare(reference,pcm,True,known_delay=0)
                row['profiles'][str(profile)]={'file_bytes':len(blob),'payload_bytes':len(blob)-20,
                    'file_bps':len(blob)*64000/len(reference),'payload_bps':(len(blob)-20)*64000/len(reference),
                    'stream_sha256':sha(blob),'pcm16_sha256':sha(pcm.astype('<i2').tobytes()),
                    'metrics':metrics,'clipped_output_samples':int(np.count_nonzero((pcm==-32768)|(pcm==32767))),
                    'version':blob[4],'encode_seconds':meta.get('seconds')}
                m=metrics['aligned_pcm16']
                print(folder.name,profile,round(m['ser_db'],3),round(m['stoi'],3),flush=True)
            for codec,rates in (('opus_voip',(6000,8000)),('speex_cbr',(3950,5950,8000))):
                for bitrate in rates:
                    item=external_encoder(folder/'encoder-tail.wav',folder/'standards',codec,bitrate)
                    scored=score_external(reference,item,'speech',folder/f'{codec}-{bitrate}.wav')
                    row['standards'][f'{codec}-{bitrate}']=scored
            report['cases'].append(row);save(output/'measurements.json',report)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('corpus',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--ids',nargs='+',required=True);ap.add_argument('--lpx8-root',type=Path)
    a=ap.parse_args();run(a.corpus,a.output,a.ids,a.lpx8_root)
