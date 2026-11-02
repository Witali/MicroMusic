"""Reproduce the initial, unrefined speech dictionary and assembled size probe."""
import argparse
import importlib.util
import json
from math import gcd
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,default=ROOT/'web-player/audio/lpx-bread/original.wav')
    p.add_argument('--output',type=Path,default=ROOT/'build/shared-speech/tiny-initial-probe')
    p.add_argument('--avr-bin',type=Path,required=True);p.add_argument('--node',default='node')
    args=p.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'build'):raise ValueError('Use ignored build storage')
    import soundfile as sf
    from scipy.signal import resample_poly
    from new_tiny_encoder import analyze_reference,initialize_model
    audio,rate=sf.read(args.reference,dtype='float64');factor=gcd(rate,7500)
    reference,base,analysis=analyze_reference(resample_poly(audio,7500//factor,rate//factor),starts=2)
    model=initialize_model(reference,base,analysis,8,starts=2)
    output.mkdir(parents=True,exist_ok=True);path=output/'model.json'
    path.write_text(json.dumps(model)+'\n',encoding='utf-8',newline='\n')
    spec=importlib.util.spec_from_file_location('tiny_budget_builder',ROOT/'tools/build-tiny-speech.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    report=builder.build(path,output/'avr',args.avr_bin.resolve(),args.node,play_once=True,maximize_output=True)
    print(json.dumps({key:report[key] for key in ('status','flashBytes','eepromBytes','phraseSamples','modelSha256')}))


if __name__=='__main__':main()
