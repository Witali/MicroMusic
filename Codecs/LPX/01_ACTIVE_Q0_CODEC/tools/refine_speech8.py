"""Encoder-only LPX8 search seeded by compact speech spectra/excitation.

Output remains v2/v3, decoded by the original decoder with speech disabled.
The baseline is retained unless full-reference SSE and STOI both pass.
"""
import argparse, inspect, json
from pathlib import Path
import numpy as np
import soundfile as sf
from speech_v4 import unpack, decode_model
from wav_lpc import pack_frames
from lpx4 import encode
from compact_format import pack as compact
from batch_decoder import BatchSession
from budget_search import search_budget
from joint_rate import encode_joint
from standard_metrics import error_metrics
from benchmark_standards import save, sha, lpx_revision


def encoder_revision():
    root=Path(__file__).parent
    dependencies=b''.join((root/(name+'.py')).read_bytes() for name in
        ('budget_search','joint_rate','rate_distortion','speech_v4','standard_metrics'))
    return sha(inspect.getsource(refine).encode()+inspect.getsource(legacy_seed).encode()+
               lpx_revision().encode()+dependencies)


def legacy_seed(blob):
    n,pre,bright,vectors,params,pulses=unpack(blob)
    q=[];scales=[]
    for half,(scale,lag,gain) in enumerate(params):
        scales.extend([scale*8]*2)
        for si in range(8):
            pos,amp=pulses[half*8+si]
            for j in range(20):
                predicted=(gain*(q[-lag] if len(q)>=lag else 0)+8)>>4
                q.append(min(31,max(-32,predicted+(amp if j==pos else 0))))
    raw=bytearray(blob[:20]);raw[:6]=b'L3AV\x01\x03';raw[16:20]=b'\xa0\0\x50\0'
    doc={'raw':bytes(raw),'frames':pack_frames(vectors[:(n+159)//160]),
         'blocks':[{'bits':6,'scale':scales[i//80],'q':q[i:min(n,i+80)]} for i in range(0,n,80)]}
    result=encode(doc,fast=True)[0];packed=compact(result,24)[0]
    return min((result,packed),key=lambda b:(len(b),b))


def refine(reference,baseline,speech_seeds,decoder):
    seeds=[baseline,*[legacy_seed(b) for b in speech_seeds]]
    for original,seed in zip(speech_seeds,seeds[1:]):
        np.testing.assert_array_equal(decoder.decode_one_s16(seed,len(reference)),decode_model(original))
    # Search the new spectra through the existing real-bit greedy encoder,
    # then refine a feasible result through its existing joint/beam search.
    blob,pcm,search=search_budget(seeds,reference,decoder,20+len(reference)//8,
        'speech',lambdas=(.001,.01,.1,1.),refinement_trials=3)
    assert blob is not None
    joined,jpcm,joint=search_budget([blob],reference,decoder,20+len(reference)//8,
        'speech',lambdas=(.1,.14,.18,.24,.32,.45,.6,1.),refinement_trials=4,
        encoder=encode_joint,encoder_options={'beam':4})
    old=decoder.decode_one_s16(baseline,len(reference));before=error_metrics(reference,old,True)
    proposals=[(blob,pcm),(joined,jpcm),(baseline,old)];accepted=[]
    for b,p in proposals:
        metrics=error_metrics(reference,p,True)
        if metrics['error_energy']<=before['error_energy'] and metrics['stoi']>=before['stoi']-1e-12:
            accepted.append((metrics['error_energy'],len(b),sha(b),b,p,metrics))
    selected=min(accepted,key=lambda p:p[:3])
    return selected[3],selected[4],{'search':search,'joint':joint,'baseline':before,
        'selected':selected[5],'decoder_modified':False,'output_version':selected[3][4]}


def run(comparison):
    comparison=Path(comparison)
    revision=encoder_revision()
    with BatchSession('batch',v3_features=24) as decoder:
        for folder in sorted(comparison.glob('case-*')):
            baseline=folder/'lpx8-initial.l4hy';current=folder/'lpx8.l4hy'
            if not baseline.exists():baseline.write_bytes(current.read_bytes())
            report=folder/'lpx8-refinement.json'
            ref,rate=sf.read(folder/'original.wav',dtype='int16');assert rate==8000
            seeds=[(folder/f'lpx{p}.l4hy').read_bytes() for p in (4,6)]
            identity={'reference_sha256':sha(ref.astype('<i2').tobytes()),
                'initial_baseline_sha256':sha(baseline.read_bytes()),'speech_seed_sha256':[sha(b) for b in seeds],
                'selected_stream_sha256':sha(current.read_bytes()),'revision':revision}
            if report.exists():
                old=json.loads(report.read_text(encoding='utf-8'))
                if all(old.get(k)==v for k,v in identity.items()):continue
            blob,pcm,meta=refine(ref,current.read_bytes(),seeds,decoder)
            meta['revision']=revision
            identity['selected_stream_sha256']=sha(blob);meta.update(identity)
            meta['selected_pcm16_sha256']=sha(pcm.astype('<i2').tobytes())
            current.write_bytes(blob);sf.write(current.with_suffix('.wav'),pcm,8000,subtype='PCM_16')
            save(current.with_suffix('.json'),{'reference_sha256':sha(ref.astype('<i2').tobytes()),
                'stream_sha256':sha(blob),'source':'encoder-only speech-seeded legacy LPX8'})
            save(report,meta)
            print(folder.name,'LPX8 refined',len(blob),meta['selected']['ser_db'],meta['selected']['stoi'],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('comparison',type=Path)
    run(ap.parse_args().comparison)
