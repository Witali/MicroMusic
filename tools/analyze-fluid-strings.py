"""Compare FluidR3 bowed-string presets on the same seven notes."""
from pathlib import Path
import importlib.util
import json
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('analysis',ROOT/'tools/analyze-fluid-violin.py')
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
presets={}
for name in ['violin','fiddle','viola','strings','slow-strings']:
    data=analysis.analyze(ROOT/'build/fluid-comparison'/name)
    brightness=[];upper=[];third=[]
    for note in data['notes']:
        for frame in note['frames']:
            power=np.array(frame['amplitudes'])**2;power/=power.sum()
            hz=np.arange(1,16)*frame['f0Hz']
            brightness.append(float(sum(power*hz)))
            upper.append(float(sum(power[hz>=2000])))
            third.append(float(sum(power[2:])))
    summary=dict(program=data['capture']['program'],name=data['capture']['preset'],
        medianHarmonicCentroidHz=float(np.median(brightness)),medianPowerAbove2kHz=float(np.median(upper)),
        medianPowerH3toH15=float(np.median(third)),medianAttack85Ms=float(np.median([n['attack85PercentMs'] for n in data['notes']])))
    presets[name]=dict(summary=summary,measurement=data)
    print(name,json.dumps(summary))
out=ROOT/'ATtiny13A/Music/reference/fluidr3/strings-comparison.json'
out.write_text(json.dumps(dict(method='Same MIDI 52/55/59/62/66/69/74, velocity 100; stereo power, measured first 15 harmonics. Lower spectral centroid alone does not determine perceived realism.',presets=presets),separators=(',',':'))+'\n',encoding='utf-8',newline='\n')
