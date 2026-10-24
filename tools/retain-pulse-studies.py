"""Retain completed pulse studies after checking Git source and PCM hashes.

Build inputs stay ignored; only models and reports with reproducible sources
are copied. Run the independent retained-result contracts after this script.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes'
spec=importlib.util.spec_from_file_location('retained_pulse_shapes',ROOT/'tools/fit-mixed-lattice.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def save(p,data):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
def verify(report,revision):
    for path,expected in report['source_sha256_normalized_lf'].items():
        data=subprocess.check_output(['git','show',f'{revision}:{path}'],cwd=ROOT)
        assert hashlib.sha256(data.decode('utf-8').replace('\r\n','\n').encode()).hexdigest()==expected,(revision,path)

original_seed='../q4-pattern-precision/mixed/q8/best-intelligibility-model.json'
runs={};aliases={};proposals={}
for name,revision in [('control16','fc4cb8d'),('wide32','fc4cb8d'),('wide32-zero','fc4cb8d'),
    ('q2-short','9b800c2'),('q2-wide-zero','9b800c2'),('q2-continuation-legacy','e0b161e'),('q2-continuation-reference','e0b161e'),
    ('voice-search','5106758'),('voice-control','5106758'),('voice-continuation','acdbc4f'),
    ('balanced-q1','acdbc4f'),('balanced-q2','acdbc4f'),('joint-blocks','cdbd9c2'),('literal-four-fit','6bc814a')]:
    folders={'balanced-q1':'balanced-pulses/q1','balanced-q2':'balanced-pulses/q2',
        'joint-blocks':'lattice-blocks/from-voice','literal-four-fit':'balanced-pulses/literal-four-fit'}
    source=ROOT/'build'/folders.get(name,'wide-pulse/'+name)
    if not (source/'report.json').exists():continue
    r=read(source/'report.json');verify(r,revision);target=DEST/name;target.mkdir(parents=True,exist_ok=True)
    for file in ('model.json','report.json'):shutil.copyfile(source/file,target/file)
    model=target/'model.json';s,b,state_bits,mode,_,_,meta=fit.load(model)
    pcm,counts=fit.render(s,b,state_bits,mode)
    assert not np.any(counts) and hashlib.sha256(pcm.tobytes()).hexdigest()==r['final']['pcm_sha256']
    used=np.unique(s.modes[(s.pitches>0)&(s.gains_q1>0)]);width=s.waves_q1.shape[1]
    stored_width=16 if s.tail_policy=='balance16' else width
    wave_bytes=(len(used)*stored_width*(s.wave_fraction_bits+3)+7)//8
    seed=('voice-search/model.json' if name in ('voice-continuation','joint-blocks') else
        'wide32-zero/model.json' if name.startswith('balanced-') else
        'prune-literal/4/model.json' if name=='literal-four-fit' else
        'q2-continuation-legacy/model.json' if name.startswith('voice-') else
        'wide32-zero/model.json' if name.startswith('q2-continuation') else original_seed)
    entry=dict(source_commit=revision,model=name+'/model.json',report=name+'/report.json',final=r['final'],
        seed_model=seed,
        active_forms=int(len(used)),wave_fraction_bits=s.wave_fraction_bits,pulse_length=width,
        nonzero_tail_taps=int(np.count_nonzero(s.waves_q1[used,16:])),packed_waveform_bytes=wave_bytes,
        waveforms_fit_eeprom=wave_bytes<=64,serialized_format=False,
        phase_mode_counts={str(code):int(np.sum(s.phase_modes==code)) if s.phase_modes is not None else 0 for code in range(4)})
    if s.tail_policy=='balance16':
        entry.update(tail_policy=s.tail_policy,area_descriptor_bytes=len(used)*(1 if s.wave_fraction_bits==1 else 2))
        shutil.copyfile(source/'initial-model.json',target/'initial-model.json')
        entry['initial_model']=name+'/initial-model.json'
    if 'best_intelligibility' in r:
        best=source/'best-intelligibility-model.json';key=name+'/best-intelligibility-model.json'
        if best.read_bytes()==model.read_bytes():aliases[key]=entry['model']
        else:shutil.copyfile(best,DEST/key);entry['best_model']=key
    runs[name]=entry

cases=[('q1-16','fit-16',16,1,'f2f344b'),('q1-32','fit-32',32,1,'f2f344b'),
    ('q2-16','q2-fit-16',16,2,'b422f4c'),('q2-32','q2-fit-32',32,2,'b422f4c'),
    ('reference-q2-16','reference-q2-16',16,2,'e0b161e'),('reference-q2-32','reference-q2-32',32,2,'e0b161e')]
for name,folder,width,precision,revision in cases:
    source=ROOT/'build/pulse-output'/folder
    if not (source/'report.json').exists():continue
    r=read(source/'report.json');verify(r,revision);target=DEST/'forward'/name;target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source/'report.json',target/'report.json')
    entry=dict(report='forward/'+name+'/report.json',source_commit=revision,seed_model=original_seed,
        pulse_length=width,wave_fraction_bits=precision,accepted=len(r['history']),final=r['final'])
    if r['history']:
        shutil.copyfile(source/'model.json',target/'model.json');entry['model']='forward/'+name+'/model.json'
    proposals[name]=entry

pruning={}
source=ROOT/'build/balanced-pulses/prune-literal'
if (source/'report.json').exists():
    r=read(source/'report.json');verify(r,'6bc814a');target=DEST/'prune-literal';target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source/'report.json',target/'report.json')
    for entry in r['records']:
        p=Path(entry['model']);(target/p).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/p,target/p)
    pruning=dict(report='prune-literal/report.json',source_commit='6bc814a',seed_model='wide32-zero/model.json')
for name,entry in {**runs,**proposals,**({'pruning':pruning} if pruning else {})}.items():assert sha(DEST/entry['seed_model'])==read(DEST/entry['report'])['seed_sha256'],name
manifest=dict(schema='q4-pulse-shape-research-v1',reference='web-player/audio/originals/vinni.wav',reference_sha256=sha(ROOT/'web-player/audio/originals/vinni.wav'),
    sample_rate=7500,samples=22272,selected_firmware='../q3-adaptive/half-pitch/model.json',firmware_changed=False,
    achieved=False,full_player_implemented=False,hardware_tested=False,target=dict(stoi=.93,spectrogram_loss=.344975553560209,flash_bytes=1024,eeprom_bytes=64),
    runs=runs,aliases=aliases,forward_proposals=proposals,form_pruning=pruning,
    scope='PC pulse and phase study; waveform counts exclude every speech byte, decoder, EOF and alignment; step-policy changes remain explicit controls')
best=None
for name,entry in runs.items():
    report=read(DEST/entry['report']);score=report['best_intelligibility']
    path=entry.get('best_model',entry['model'])
    if best is None or score['stoi']>best[0]:best=(score['stoi'],path,score)
manifest.update(highest_stoi_model=best[1],highest_stoi_metrics=best[2],highest_stoi_avr_player_qualified=False)
if (DEST/'../word-q4/filter-joint-best.json').exists():manifest['word_filter_proof']='../word-q4/filter-joint-best.json'
manifest['artifact_sha256']={p.relative_to(DEST).as_posix():sha(p) for p in sorted(DEST.rglob('*.json')) if p.name!='manifest.json'}
save(DEST/'manifest.json',manifest)
print(json.dumps({name:dict(stoi=r['final']['stoi'],spectrum=r['final']['spectrogram_loss'],wave_bytes=r['packed_waveform_bytes']) for name,r in runs.items()},indent=2))
