"""Compare equal-seed legacy and voice-priority Vinni initialization.

Full-clip metrics include sound effects. The additional voice-mask STOI uses
the same concatenated accepted blocks for both candidates; joins change the
metric's context, so this diagnostic is not a replacement for full-clip STOI.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[5]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
sys.path.insert(0,str(ROOT/'tools'))
from auto_encoder import SpectralObjective
from period_wave import encode_model,decode_model,packed_bytes
from refine_period_helpers import matched_audio


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'build/tiny-speech/vinni/pitch-study')
    parser.add_argument('--starts',type=int,default=8)
    args=parser.parse_args()
    if digest(args.reference)!='749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03':
        raise ValueError('Reference differs from canonical Vinni source')
    args.output.mkdir(parents=True,exist_ok=True)
    reference,sr=sf.read(args.reference)
    objective=SpectralObjective(reference,sr)
    candidates={}
    for mode in ('legacy','voice-priority'):
        model,analysis=encode_model(reference,seed=23065,starts=args.starts,pitch_mode=mode)
        candidates[mode]=(model,analysis,decode_model(model))
        save(args.output/(mode+'-model.json'),model)
    robust=candidates['voice-priority'][1]
    mask=np.repeat(robust['voice_mask'],64)[:len(reference)]
    metrics={}
    for mode,(model,analysis,audio) in candidates.items():
        metrics[mode]=dict(stoi=float(stoi(reference,audio,sr)),**objective.spectrum(audio),
            voice_mask_concatenated_stoi=float(stoi(reference[mask],audio[mask],sr)),
            voice_mask_mse=float(np.mean((reference[mask]-audio[mask])**2)),
            voiced_frames=int(np.count_nonzero(analysis['voice_mask'])),
            book_frames=int(np.count_nonzero(analysis['book_mask'])),
            f0_voiced_percentiles_hz=np.percentile(analysis['f0'][analysis['voice_mask']],[0,25,50,75,100]).tolist(),
            phase_code_frequency_median_hz=float(np.median(np.asarray(model['frames'])[:,0]*sr*32/65536)),
            data_bytes=len(packed_bytes(model)),model_sha256=digest(args.output/(mode+'-model.json')))
    sources=[Path(__file__),ROOT/'tools/refine_period_helpers.py']+[CODEC/name for name in (
        'period_wave.py','speech_pitch.py','auto_encoder.py')]
    report=dict(schema='vinni-voice-priority-comparison-v1',reference_sha256=digest(args.reference),
        sample_rate=sr,samples=len(reference),seed=23065,starts=args.starts,refinement_proposals=0,
        runtime={name:importlib.metadata.version(name) for name in ('numpy','scipy','pystoi','soundfile')},
        source_sha256_normalized_lf={str(p.relative_to(ROOT)).replace('\\','/'):
            hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in sources},
        metrics=metrics,voice_mask_samples=int(np.count_nonzero(mask)),
        voice_mask_metric_caveat='Identical automatically accepted 64-sample blocks are concatenated for both candidates; artificial joins alter STOI context. This diagnostic is not full-record STOI or independently annotated speech ground truth.',
        interpretation='Persistent voice F0 is protected from isolated resonances. Full-record initialization quality regresses, while the common accepted-voice diagnostic improves. No public firmware or quality promotion follows from these measurements.',
        recording_trimmed=False,transients_discarded=False,
        transient_path='Existing unvoiced colored-noise frames; later residual refinement may fit the full source. No reference samples are read during decoding.',
        avr_assembled=False,hardware_verified=False)
    save(args.output/'pitch-analysis.json',robust['pitch_analysis'])
    save(args.output/'quality.json',report)
    matched_audio(args.output,dict(Original=reference,Legacy=candidates['legacy'][2],
                                 VoicePriority=candidates['voice-priority'][2]),objective,
                  ('Original','Legacy','Original','VoicePriority'))
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'build/matplotlib-config'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from scipy.signal import stft
    fig,axes=plt.subplots(3,1,figsize=(11,8),layout='constrained')
    axes[0].plot(np.arange(len(reference))/sr,reference,linewidth=.55,color='0.3')
    centres=robust['centres']/sr
    pitch=robust['pitch_analysis']
    for i in np.flatnonzero(pitch['attack_frames']):
        axes[0].axvspan(i*64/sr,(i+1)*64/sr,color='tab:red',alpha=.2,linewidth=0)
    axes[0].set_ylabel('Amplitude');axes[0].set_title('Original recording; automatically rejected attack frames in red',loc='left')
    frequencies,times,spectrum=stft(reference,fs=sr,nperseg=512,noverlap=448)
    db=20*np.log10(np.maximum(abs(spectrum)/np.max(abs(spectrum)),1e-4))
    axes[1].pcolormesh(times,frequencies,db,shading='auto',cmap='magma',vmin=-65,vmax=0)
    axes[1].plot(centres,np.where(np.asarray(pitch['raw_f0_hz'])>0,pitch['raw_f0_hz'],np.nan),'.',
                 color='0.65',markersize=3,label='Legacy F0 candidates')
    axes[1].plot(centres,np.where(robust['voice_mask'],robust['f0'],np.nan),'.',
                 color='cyan',markersize=4,label='Accepted voice F0')
    axes[1].axhline(pitch['prior_hz'],color='lime',linestyle='--',linewidth=.8,label=f"Persistent prior {pitch['prior_hz']:.1f} Hz")
    axes[1].set_ylim(50,900);axes[1].set_ylabel('Frequency, Hz');axes[1].legend(loc='upper right')
    axes[2].step(centres,robust['voice_mask'].astype(int),where='mid',label='Voice mask')
    axes[2].step(centres,robust['book_mask'].astype(int)*.8,where='mid',label='Dictionary mask')
    axes[2].set_ylabel('Accepted');axes[2].set_xlabel('Time, seconds');axes[2].set_ylim(-.05,1.1);axes[2].legend()
    for axis in axes:axis.set_xlim(0,len(reference)/sr)
    fig.suptitle('Vinni: automatic persistent-voice analysis; no manual time boundaries\nPC initialization comparison; F0 is an estimate, not annotated ground truth')
    fig.savefig(args.output/'f0-comparison.png',dpi=130);plt.close(fig)
    print(json.dumps(dict(metrics=metrics,prior_hz=pitch['prior_hz'],
                         prior_runs=[run for run in pitch['prior_runs'] if run['accepted']]),indent=2))


if __name__=='__main__':main()
