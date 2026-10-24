"""Compare true STOI band contributions of the selected and PC teacher models."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from stoi_diagnostics import band_scores
import q4_phase_wave as codec


def teacher_pcm(path):
    model=json.loads(path.read_text(encoding='utf-8'))
    schema=model.get('schema');sources=[ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py']
    if schema=='q4-lattice-fit-v1':script='refine-q4-lattice.py'
    elif schema=='q4-quarter-fit-v1':script='refine-q4-quarter.py'
    elif schema in ('q4-product233-v1','q4-product233-phase-v1'):script='fit-q4-product233.py'
    elif schema in ('mixed-lattice-v1','mixed-lattice-pulse-v1','mixed-lattice-balanced-v1'):script='fit-mixed-lattice.py'
    else:raise ValueError('Unsupported explicitly tagged PC speech model')
    spec=importlib.util.spec_from_file_location('band_renderer_'+script.replace('-','_').replace('.','_'),ROOT/'tools'/script)
    renderer=importlib.util.module_from_spec(spec);sys.modules[spec.name]=renderer;spec.loader.exec_module(renderer)
    sources.append(ROOT/'tools'/script)
    if schema in ('mixed-lattice-v1','mixed-lattice-pulse-v1','mixed-lattice-balanced-v1'):
        state,bits,state_bits,mode,_,_,_=renderer.load(path)
        pcm,counts=renderer.render(state,bits,state_bits,mode)
        sources.append(ROOT/'ATtiny13A/Sound/codec/mixed_lattice.py')
    elif schema=='q4-quarter-fit-v1':
        state,_=renderer.load(path)
        pcm,counts=renderer.render(state,model['state_bits'],model['nearest'],model.get('phase_mode',0))
    elif schema.startswith('q4-product233'):
        state=renderer.from_model(model);pcm,counts=renderer.render(state,model['state_bits'],model['nearest'])
        sources.extend((ROOT/'tools/refine-q4-lattice.py',ROOT/'ATtiny13A/Sound/codec/q4_product233.py'))
    else:
        state=renderer.load(path);renderer.validate(state);pcm,counts=renderer.render(state,model['state_bits'],model['nearest'])
    return pcm,counts,model,sources


def run(reference_path,baseline_path,teacher_path,output):
    reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1:raise ValueError('Expected unchanged mono7500 original')
    pcm,counts,teacher,decoder_sources=teacher_pcm(teacher_path)
    if teacher['reference_sha256']!=hashlib.sha256(reference_path.read_bytes()).hexdigest():raise ValueError('Teacher original hash mismatch')
    if np.any(counts):raise ValueError('Teacher arithmetic wraps')
    baseline=json.loads(baseline_path.read_text(encoding='utf-8'));f=np.array(baseline['frames'],np.int16)
    d=np.array(baseline['durations'],np.int16);b=np.array(baseline['pulsebook'],np.int16)
    h=np.array(baseline['fractions'],np.int16);k=np.empty((len(f),8),np.int16)
    k[:,::2]=((f[:,2:]&15)-8)*2;k[:,1::2]=((f[:,2:]>>4)-8)*2
    rows,excitation=codec.legacy_excitation(f[:,0],f[:,1]&15,d,f[:,1]>>4,b,h)
    before,bc=codec.filter_signal(excitation,rows,k)
    if np.any(bc) or len(before)!=len(reference) or len(pcm)!=len(reference):raise ValueError('Invalid complete baseline')
    report=dict(schema='q4-stoi-band-audit-v1',baseline=band_scores(reference,(before.astype(float)-128)/128,sr),
        teacher=band_scores(reference,(pcm.astype(float)-128)/128,sr),
        reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        baseline_sha256=hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        teacher_sha256=hashlib.sha256(teacher_path.read_bytes()).hexdigest(),
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
            for p in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/stoi_diagnostics.py',*decoder_sources)})
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(stoi=report['teacher']['stoi'],bands=report['teacher']['bands'])));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','baseline','teacher','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();run(a.reference,a.baseline,a.teacher,a.output)
