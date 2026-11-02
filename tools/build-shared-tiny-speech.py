"""Compare bounded tiny speech encoders, verify the winner and retain provenance.

Only the already-public bread/original.wav is used. Search audio, checkpoints
and compiler logs stay in build/. The selected model, report and self-contained
catalog entry are retained in the repository. No firmware arithmetic is changed.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'ATtiny13A/Sound/codec')]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def sha(data):return hashlib.sha256(data).hexdigest()


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-bin',type=Path,required=True);p.add_argument('--node',default='node')
    p.add_argument('--output',type=Path,default=ROOT/'build/shared-speech')
    p.add_argument('--proposals',type=int,default=3000);p.add_argument('--starts',type=int,default=4)
    p.add_argument('--seed',type=int,default=23120);p.add_argument('--reuse-search',action='store_true')
    p.add_argument('--noise-model',type=Path);p.add_argument('--noise-report',type=Path)
    args=p.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'build') or output==ROOT/'build':raise ValueError('Use ignored build storage')
    import soundfile as sf
    from scipy.signal import resample_poly
    source=ROOT/'web-player/audio/lpx-bread/original.wav'
    audio,rate=sf.read(source,dtype='float64')
    if rate!=8000 or audio.ndim!=1:raise ValueError('Unexpected public source format')
    reference=output/'tiny-bread/reference7500.wav';reference.parent.mkdir(parents=True,exist_ok=True)
    sf.write(reference,resample_poly(audio,15,16),7500,subtype='PCM_16')
    encoder=load('shared_tiny_encoder',ROOT/'tools/encode-new-tiny-speech.py')
    builder=load('shared_tiny_builder',ROOT/'tools/build-tiny-speech.py')
    candidates=[];searches=[]
    for mode in ('legacy','voice-priority'):
        folder=output/('tiny-fit-'+mode)
        if args.reuse_search:
            report=json.loads((folder/'quality.json').read_text(encoding='utf-8'))
            if (report['reference_sha256']!=sha(reference.read_bytes()) or report['proposals']!=args.proposals
                or report['starts']!=args.starts or report['seed']!=args.seed or report['pitch_mode']!=mode):
                raise ValueError('Cached search parameters/source differ')
        else:
            report=encoder.run(reference,folder,args.avr_bin.resolve(),proposals=args.proposals,
                               starts=args.starts,seed=args.seed,pitch_mode=mode)
        searches.append(dict(mode=mode,initialCandidates=report['candidates'],results=report['searches']))
        for kind,search in report['searches'].items():
            if not search['size_fits']:continue
            model=folder/(kind+'-model.json')
            build=builder.build(model,folder/(kind+'-avr'),args.avr_bin.resolve(),args.node,
                                play_once=True,maximize_output=True)
            if build['status']=='oversized':
                build=builder.build(model,folder/(kind+'-avr'),args.avr_bin.resolve(),args.node,
                                    play_once=True,maximize_output=False)
            if build['status']!='verified':raise ValueError('Candidate failed complete AVR verification')
            score=search['final'];energy=score['loss']+8*(1-score['stoi'])
            candidates.append(dict(mode=mode,kind=kind,model=model,folder=folder/(kind+'-avr'),
                rankingScore=energy,quality=score,build=build))
    if not candidates:raise ValueError('No verified firmware fits; keep the unavailable card')
    winner=min(candidates,key=lambda item:(item['rankingScore'],item['build']['flashBytes']))
    noise_report=None
    if args.noise_model:
        if not args.noise_report:raise ValueError('A spectral model requires its comparison report')
        noise_report=json.loads(args.noise_report.read_text(encoding='utf-8'))
        if noise_report['sourceSha256']!=sha(source.read_bytes()):raise ValueError('Spectral source differs')
        if noise_report.get('modelSha256')!=sha(args.noise_model.read_bytes()):raise ValueError('Spectral model/report differ')
        build=builder.build(args.noise_model.resolve(),output/'noise-refinement/avr',args.avr_bin.resolve(),args.node,
                            play_once=True,maximize_output=False)
        if build['status']!='verified':raise ValueError('Spectral model failed complete AVR verification')
        winner=dict(mode='spectrogram-noise',kind='fit',model=args.noise_model.resolve(),folder=output/'noise-refinement/avr',
                    quality=noise_report['selected'],rankingScore=noise_report['selected']['score'],build=build)
    retained=ROOT/'ATtiny13A/Sound/research/shared-speech'
    retained.mkdir(parents=True,exist_ok=True)
    model=retained/'bread-model.json';shutil.copyfile(winner['model'],model)
    if not noise_report:shutil.copyfile(winner['model'],retained/'bread-search-model.json')
    build=winner['build'];folder=winner['folder']
    receipt=dict(schema='micromusic-shared-tiny-selection-v1',source='web-player/audio/lpx-bread/original.wav',
        sourceSha256=sha(source.read_bytes()),inputSampleRate=8000,inputSamples=len(audio),
        resampler='scipy.signal.resample_poly up=15 down=16; PCM16',sampleHz=7500,
        referenceSamples=18000,encodedSamples=build['phraseSamples'],paddingSamples=build['phraseSamples']-18000,
        trimmedSamples=0,timeCompression=False,seed=args.seed,starts=args.starts,proposalsPerPitchMode=args.proposals,
        methods=['legacy and voice-priority pitch','1/2/4/8 word dictionaries','regional parameter holding','exact integer constrained refinement'],
        ranking='lowest loss + 8 * (1 - STOI) among fully verified images <= 1024 Flash / 64 EEPROM',
        subjectiveListeningVerified=False,selected=dict(mode=winner['mode'],kind=winner['kind'],
            modelSha256=sha(model.read_bytes()),flashBytes=build['flashBytes'],eepromBytes=build['eepromBytes']),
        selectedVerification=build['verification'],
        searches=searches,
        candidates=[dict(mode=c['mode'],kind=c['kind'],rankingScore=c['rankingScore'],quality=c['quality'],
            flashBytes=c['build']['flashBytes'],eepromBytes=c['build']['eepromBytes'],
            verification=c['build']['verification'],outputLevel=c['build'].get('outputLevel')) for c in candidates],
        sourceSha256NormalizedLF={str(path.relative_to(ROOT)).replace('\\','/'):sha(path.read_text(encoding='utf-8').encode())
            for path in (Path(__file__),ROOT/'tools/encode-new-tiny-speech.py',ROOT/'tools/build-tiny-speech.py',
                         ROOT/'ATtiny13A/Sound/codec/new_tiny_encoder.py')})
    if noise_report:
        receipt['ranking']='raw time-aligned multi-resolution spectral/noise objective with STOI floor; no level matching or playback-rate change'
        receipt['noiseRefinement']=noise_report['selected']
        receipt['noiseScriptSha256NormalizedLF']=sha((ROOT/'tools/refine-shared-tiny-noise.py').read_text(encoding='utf-8').encode())
        save(retained/'bread-noise-refinement.json',noise_report)
    save(retained/'bread-selection.json',receipt)
    binary=(folder/'firmware.bin').read_bytes();eeprom=(folder/'eeprom.bin').read_bytes()
    entry=dict(id='hq4-bread-tiny',kind='speech',codec='tiny-period',title='И того, и другого, и можно без хлеба',
        description=f"Tiny Speech · {build['phraseSamples']/7500:.3f} с",order='04',audioReferenceId='bread',
        flashBytes=len(binary),eepromBytes=len(eeprom),sampleHz=7500,pwmHz=7500,carrierHz=37500,
        voices=1,phraseSamples=build['phraseSamples'],playOnce=True,outputLevel=build.get('outputLevel'),
        flashHex=builder.intel_hex(binary),eepromHex=builder.intel_hex(eeprom),flashSha256=sha(binary),
        eepromSha256=sha(eeprom),originalAudioUrl='./audio/lpx-bread/original.wav',originalAudioSha256=sha(source.read_bytes()),
        research='../ATtiny13A/Sound/research/shared-speech/README.md',
        verification='../ATtiny13A/Sound/research/shared-speech/bread-selection.json',
        sourceInputs={**build['normalizedSourceSha256'],str(model.relative_to(ROOT)).replace('\\','/'):sha(model.read_bytes())})
    save(ROOT/'web-player/firmware-attiny13a-speech-extra.json',dict(schema=1,generator='tools/build-shared-tiny-speech.py',entries=[entry]))
    definitions=json.loads((ROOT/'web-player/speech-examples.json').read_text(encoding='utf-8'))
    definitions['unavailable']=[item for item in definitions['unavailable'] if (item['device'],item['phraseId'])!=('attiny13a','bread')]
    save(ROOT/'web-player/speech-examples.json',definitions)
    print(json.dumps(dict(selected=receipt['selected'],candidates=len(candidates))))


if __name__=='__main__':main()
