"""Retain a measured GM50 Synth Strings 1 sidecar; never change the main bank."""
from pathlib import Path
import hashlib
import importlib.util
import json
import statistics

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / 'build/children-four/synth-strings-capture'
OUTPUT = ROOT / 'ATtiny13A/Music/instruments/children-synth-strings-profile.json'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    analyzer = module('children_strings_analyzer', ROOT / 'tools/analyze-fluid-violin.py')
    bank = module('children_strings_bank', ROOT / 'tools/instrument-bank.py')
    source = analyzer.analyze(CAPTURE)
    assert source['capture']['program'] == 50
    source['measurement']['reference']='FluidR3 GM50 Synth Strings 1 sample-bank synthesis; no acoustic-instrument identity is inferred'
    notes = []
    for note in source['notes']:
        frames = [{key:value[:7] if isinstance(value,list) else value for key,value in frame.items()}
                  for frame in note['frames']]
        ages = [20,50,100,200,400,600,800]
        rms = [note['envelopeRms'][min(range(len(note['envelopeTimesMs'])),
                key=lambda index:abs(note['envelopeTimesMs'][index] - age))] for age in ages]
        notes.append(dict(midi=note['midi'], sourcePcmSha256=note['sha256'],
            frames=frames, attack85PercentMs=note['attack85PercentMs'],
            envelopeAgesMs=ages, envelopeRms=rms, releaseThresholdMs=note['releaseThresholdMs']))
    output = dict(schema=1,id='synth-strings-1',program=50,
        soundfont=source['capture']['soundfont'],renderer=source['capture']['renderer'],
        captureSha256=hashlib.sha256((CAPTURE/'capture.json').read_bytes()).hexdigest(),
        measurement=source['measurement'],notes=notes,
        captureCommand='node tools/render-fluid-violin.mjs --soundfont ORIGINAL_SF2 --engine SPESSASYNTH_JS --output build/children-four/synth-strings-capture --profile violin --program 50 --notes 53,60,65,72,75,79,84,87 --gate 4 --tail 1.2',
        reproduction='Run the pinned capture command, then python tools/fit-children-synth-strings.py. The profile name violin only selects output filenames; program50 is explicitly set and verified.')
    OUTPUT.write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8',newline='\n')
    # The existing AVR selector changes banks at DDS step-high 4 (MIDI62).
    fit=bank.fit_measurements(OUTPUT,cutoff=3.2,peak=4,split_midi=62)
    output['profile']=dict(label='Синтезированные струнные 1',gmProgram=50,
        waves={register:fit['registers'][register]['waveform'] for register in ('low','high')},
        envelope=dict(model='sustain',defaultLevel=4,retrigger='half',attackStep=1,
                      attackMask=1,releaseStep=1,releaseMask=7),
        fit=fit,
        note='GM50 matches the original Children track5. The native arrangement uses a source-inspired one-note harmonic pad, not its literal chord notes. Generic cap4 attack every2 ticks is ~109ms, release every8ticks ~437ms; native Children uses cap7 at half output gain (~191ms/~765ms). Low MIDI53/60 source attacks are slower and cannot be modeled exactly by one compact envelope.')
    output['dynamicsSummary']=dict(attack85MedianMs=statistics.median(n['attack85PercentMs'] for n in notes),
        release50MedianMs=statistics.median(n['releaseThresholdMs']['0.5'] for n in notes),
        release10MedianMs=statistics.median(n['releaseThresholdMs']['0.1'] for n in notes))
    OUTPUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    assert bank.fit_measurements(OUTPUT,cutoff=3.2,peak=4,split_midi=62)==fit
    print(json.dumps(dict(profile=output['profile'],dynamics=output['dynamicsSummary']),ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
