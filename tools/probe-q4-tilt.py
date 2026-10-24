"""Screen a global output pole and source scale without changing timing/data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q4_phase_wave as codec
from spectrogram_objective import SpectrogramObjective
from stoi_diagnostics import band_scores


def run(reference_path,model_path,output):
    m=json.loads(model_path.read_text(encoding='utf-8'))
    if m['schema']!='q4-lattice-fit-v1':raise ValueError('Expected tagged joint-fit teacher')
    array=lambda name:np.asarray(m[name],np.int16)
    p,g,d,k,mode,b,h=map(array,('pitches','gains_q1','durations','coefficients','modes','waves_q1','halves'))
    x,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or x.ndim!=1 or int(d.sum())!=len(x):raise ValueError('Expected complete mono7500 original')
    rows,excitation=codec.legacy_excitation(p,g,d,mode,b,h);excitation[p[rows]==0]*=2
    objective=SpectrogramObjective(x);results=[]
    for shift in range(5):
        for fraction in (1,2,3):
            pcm,counts=codec.filter_signal(excitation,rows,k,tilt_shift=shift,
                state_bits=m['state_bits'],nearest=m['nearest'],fraction_bits=fraction)
            raw=pcm.astype(np.int16)-128;y=raw.astype(float)/128
            valid=not np.any(counts) and abs(raw).max()<=115 and not np.any(abs(np.diff(raw))>=48)
            results.append(dict(tilt_shift=shift,excitation_scale=2.**(2-fraction),
                guards_pass=bool(valid),stoi=float(stoi(x,y,sr)),**objective.evaluate(y),
                raw_mean=float(y.mean()),raw_rms=float(np.sqrt(np.mean(y*y))),peak=int(abs(raw).max()),
                wrap_counts=counts.tolist(),pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
                bands=band_scores(x,y,sr)['bands'] if valid else None))
    report=dict(schema='q4-output-pole-probe-v1',reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        teacher_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),results=results,
        avr_implemented=False,hardware_tested=False,
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
            for p in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py',ROOT/'ATtiny13A/Sound/codec/stoi_diagnostics.py')})
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps([{k:v for k,v in result.items() if k in ('tilt_shift','excitation_scale','guards_pass','stoi','spectrogram_loss','raw_mean')} for result in results]));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','model','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();run(a.reference,a.model,a.output)
