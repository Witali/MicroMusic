"""Build a separately tagged eight-form Q3 image and verify real AVR output."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
CODEC=ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from q3_pulsebook8 import SCHEMA,validate,unpack_stream,render,storage
from q3_pulsebook import SCHEMA as OLD_SCHEMA

spec=importlib.util.spec_from_file_location('eight_form_short_helpers',ROOT/'tools/probe-q3-short-eeprom.py')
short=importlib.util.module_from_spec(spec);spec.loader.exec_module(short)
helpers,replace_once,sha=short.helpers,short.replace_once,short.sha


def load_model(path):
    value=json.loads(Path(path).read_text(encoding='utf-8'))
    if (value.get('schema') not in (SCHEMA,OLD_SCHEMA) or value.get('nearest') is not False
            or value.get('tilt_shift')!=1 or value.get('sample_rate')!=7500):
        raise ValueError('Expected an explicitly tagged floor Q3/T1 model')
    f,d,b=np.asarray(value['frames']),np.asarray(value['durations']),np.asarray(value['pulsebook'])
    if value['schema']==OLD_SCHEMA:
        if b.shape!=(4,16) or np.any(f[:,1]>63):raise ValueError('Invalid four-form conversion')
        b=np.vstack((b,b))
    payload=validate(f,d,b,samples=value['samples'])
    return f.astype(np.uint8),d.astype(np.uint16),b.astype(np.int8),payload


def source_for(layout):
    source=short.source_for(layout)
    source=replace_once(source,'vbr_pitch:\n','vbr_pitch:\n clr r13 /* upper waveform address, zero for compact headers */\n')
    stride=layout['width'] if layout['packing']=='raw' else layout['width']//2
    capture=' mov r23,r16\n andi r23,4\n'+' lsl r23\n'*(stride.bit_length()-1)+' mov r13,r23\n'
    source=replace_once(source,'vbr_extended:\n','vbr_extended:\n'+capture)
    source=replace_once(source,'pulse_address_ready:\n or r16,r18',
        'pulse_address_ready:\n or r16,r18\n or r16,r13')
    return source


def build(frames,durations,book,output,avr_bin,node,*,width=4,packing='nibble',prefix=None):
    payload=validate(frames,durations,book)
    layout=storage(book,payload,width,packing,prefix)
    code=layout['code_bytes'];flash=(code+len(layout['flash_suffix'])+2)&~1
    if flash>1024:raise ValueError('Complete eight-form image exceeds 1024 Flash bytes')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('build.json','verification.json','actual.raw','firmware.bin','firmware.elf','firmware.hex','eeprom.hex'):
        (output/name).unlink(missing_ok=True)
    source=source_for(layout)
    (output/'firmware.S').write_text(source,encoding='utf-8',newline='\n')
    (output/'speech.hq8').write_bytes(payload)
    (output/'flash-suffix.hq').write_bytes(layout['flash_suffix'])
    (output/'eeprom.bin').write_bytes(layout['eeprom'])
    (output/'eeprom.hex').write_text(helpers.intel_hex(layout['eeprom']),encoding='ascii',newline='\n')
    phrase,counts=render(np.asarray(frames,np.uint8),np.asarray(durations,np.uint16),np.asarray(book,np.int8))
    expected=np.r_[phrase,np.full(len(phrase)*2,128,np.uint8)]
    (output/'expected.raw').write_bytes(expected.tobytes())
    suffix='.exe' if os.name=='nt' else ''
    executable=lambda name:Path(avr_bin)/(name+suffix)
    helpers.run([executable('avr-gcc'),'-mmcu=attiny13','-nostdlib',
        '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024','-Wl,-Ttext=0','-x','assembler','firmware.S','-o','firmware.elf'],output)
    symbols=helpers.parse_symbols(helpers.run([executable('avr-nm'),'-n','firmware.elf'],output).stdout)
    helpers.run([executable('avr-objcopy'),'-O','binary','firmware.elf','firmware.bin'],output)
    image=(output/'firmware.bin').read_bytes()
    assert symbols['code_end']==symbols['voice_data']==code
    assert len(image)==flash and image[code:code+len(layout['flash_suffix'])+1]==layout['flash_suffix']+b'\xff'
    (output/'firmware.hex').write_text(helpers.intel_hex(image),encoding='ascii',newline='\n')
    check=helpers.run([node,ROOT/'tools/verify-tiny-speech.mjs',output/'firmware.bin',output/'expected.raw',
        output/'verification.json','--eeprom',output/'eeprom.bin','--phrase-samples',len(phrase),
        '--loops',3,'--playback','once','--minimum-sp',symbols['STACK_FLOOR'],
        '--wait-pc',symbols['wait_slot'],'--actual-raw',output/'actual.raw'],ROOT,check=False)
    verification=json.loads((output/'verification.json').read_text())
    report=dict(schema='q3-pulsebook8-build-v1',status='verified' if verification['pass'] else 'failed',
        hardware_tested=False,forms=8,gain_levels=16,width=width,packing=packing,code_bytes=code,
        flash_bytes=flash,eeprom_bytes=64,waveform_bytes=layout['book_bytes'],
        speech_prefix_bytes=layout['prefix_bytes'],prefix_start=layout['prefix_start'],prefix_end=layout['prefix_end'],
        maximum_stream_bytes=layout['maximum_stream_bytes'],stream_bytes=len(payload),phrase_samples=len(phrase),
        phrase_pcm_sha256=sha(phrase.tobytes()),stream_sha256=sha(payload),firmware_sha256=sha(image),
        eeprom_sha256=sha(layout['eeprom']),asm_sha256_normalized_lf=sha(source.encode()),
        intermediate_wraps=counts.tolist(),symbols=symbols,verification=verification)
    (output/'build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    if check.returncode:raise RuntimeError(str(verification.get('error')))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--avr-bin',required=True,type=Path);p.add_argument('--node',required=True,type=Path)
    p.add_argument('--width',type=int,choices=(4,8,16),default=4)
    p.add_argument('--packing',choices=('raw','nibble'),default='nibble')
    a=p.parse_args();f,d,b,_=load_model(a.model)
    result=build(f,d,b,a.output,a.avr_bin,a.node,width=a.width,packing=a.packing)
    print(json.dumps({key:result[key] for key in ('status','code_bytes','flash_bytes','waveform_bytes','speech_prefix_bytes','maximum_stream_bytes')}))


if __name__=='__main__':main()
