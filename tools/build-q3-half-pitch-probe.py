"""Research-only half-sample pitch probe; real AVR and exact integer oracle.

The pitch byte's high bit selects alternating P+1/P cycles. Every frame resets
the alternation. Arithmetic and the historical final-sample convention persist.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('half_pitch_base_builder',ROOT/'tools/build-q3-pulsebook8.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
from q3_adaptive import select


def oracle(output):
    original=(ROOT/'ATtiny13A/Sound/codec/q3_pulsebook8.py').read_text(encoding='utf-8')
    source=original[original.index('@njit(cache=True)'):]
    for before,after in [
        ('def render(frames, durations, pulsebook, tilt_shift=1, nearest=False):',
         'def render(frames, durations, pulsebook, fractions, tilt_shift=1, nearest=False):'),
        ('period = gain = mode = previous = 0','period = gain = mode = previous = cycle_extra = half = 0'),
        ('period = int(frames[frame,0])','period = int(frames[frame,0])\n            half = int(fractions[frame]);cycle_extra = 0'),
        ('phase = period\n                ex =','cycle_extra ^= half\n                phase = period+cycle_extra\n                ex ='),
        ('lag = period-phase','lag = period+cycle_extra-phase')]:
        source=base.replace_once(source,before,after)
    path=output/'half_oracle.py'
    path.write_text('import numpy as np\nfrom numba import njit\nfrom q3_pulsebook import signed,multiply\n'+source,encoding='utf-8',newline='\n')
    spec=importlib.util.spec_from_file_location('half_oracle_'+base.sha(str(output).encode())[:12],path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module.render


def pack(frames,durations,book,fractions):
    base.validate(frames,durations,book)
    halves=np.asarray(fractions)
    if halves.dtype.kind not in 'iu' or halves.shape!=(len(frames),) or not np.all(np.isin(halves,[0,1])) or np.any((halves>0)&(frames[:,0]==0)):
        raise ValueError('Half-pitch flags must be 0/1, one per frame, voiced only')
    payload=bytearray();old=None
    for f,d,half in zip(frames,durations,halves):
        p,h,d,half=int(f[0]),int(f[1]),int(d),int(half);upper=h>>6
        if p<=63 and d!=192 and not upper and not half:payload.append((d&192)|p)
        else:payload.extend((192|((d//64)&3)|(upper<<2),p|(half<<7)))
        k=list(map(int,f[2:]));kind=(0 if old is None or (k[:2]!=old[:2] and k[2:]!=old[2:])
            else 1 if k==old else 2 if k[:2]!=old[:2] else 3)
        payload.append((kind<<6)|(h&63))
        if kind==0:payload.extend(k)
        elif kind==2:payload.extend(k[:2])
        elif kind==3:payload.extend(k[2:])
        old=k
    return bytes(payload)


def build(model_path,output,avr_bin,node,*,zero_flags=False):
    value=json.loads(model_path.read_text(encoding='utf-8'))
    if value.get('schema')!='q3-half-pitch-probe-v1':raise ValueError('Expected tagged research half-pitch model')
    raw_f,raw_d,raw_b,raw_flags=(np.asarray(value[k]) for k in ('frames','durations','pulsebook','fractions'))
    pack(raw_f,raw_d,raw_b,raw_flags)
    f,d,b,flags=raw_f.astype(np.uint8),raw_d.astype(np.uint16),raw_b.astype(np.int8),raw_flags.astype(np.uint8)
    if zero_flags:flags[:]=0
    layout=select(f,d,b);f,b=layout['frames'],layout['book']
    payload=pack(f,d,b,flags);prefix=min(64-layout['book_bytes'],len(payload))
    code=layout['code_bytes']+24;flash=(code+len(payload)-prefix+2)&~1
    if flash>1024:raise ValueError('Half-pitch complete image exceeds 1024 bytes')
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    render=oracle(output);pcm,counts=render(f,d,b,flags)
    if np.any(counts):raise ValueError('Half-pitch model wraps internally')
    plain,plain_counts=render(f,d,b,np.zeros_like(flags))
    old,old_counts=base.render(f,d,b)
    np.testing.assert_array_equal(plain,old);np.testing.assert_array_equal(plain_counts,old_counts)
    layout.update(prefix_bytes=prefix,prefix_end=layout['book_bytes']+prefix)
    source=base.source_for(layout)
    source=base.replace_once(source,'vbr_setpitch:\n mov r4,r16\n mov r2,r16',
        'vbr_setpitch:\n lsl r16\n clr r9\n rol r9\n lsr r16\n mov r4,r16\n mov r2,r16')
    source=base.replace_once(source,' mov r2,r4\n clr r18',
        ' mov r2,r4\n sbrs r9,0\n rjmp half_period_ready\n ldi r16,2\n eor r9,r16\n sbrc r9,1\n inc r2\nhalf_period_ready:\n clr r18')
    source=base.replace_once(source,' sub r18,r2\n cpi r18,',
        ' sub r18,r2\n sbrc r9,1\n inc r18\n cpi r18,')
    eeprom=layout['eeprom'][:layout['book_bytes']]+payload[:prefix]
    eeprom=eeprom.ljust(64,b'\xff')
    (output/'firmware.S').write_text(source,encoding='utf-8',newline='\n')
    (output/'flash-suffix.hq').write_bytes(payload[prefix:]);(output/'eeprom.bin').write_bytes(eeprom)
    (output/'expected.raw').write_bytes(np.r_[pcm,np.full(2*len(pcm),128,np.uint8)].tobytes())
    exe=lambda name:avr_bin/(name+'.exe')
    base.helpers.run([exe('avr-gcc'),'-mmcu=attiny13','-nostdlib','-Wl,--defsym=__TEXT_REGION_LENGTH__=1024','-Wl,-Ttext=0','-x','assembler','firmware.S','-o','firmware.elf'],output)
    symbols=base.helpers.parse_symbols(base.helpers.run([exe('avr-nm'),'-n','firmware.elf'],output).stdout)
    base.helpers.run([exe('avr-objcopy'),'-O','binary','firmware.elf','firmware.bin'],output)
    image=(output/'firmware.bin').read_bytes()
    assert symbols['code_end']==code and len(image)==flash
    for name,data in [('firmware',image),('eeprom',eeprom)]:
        (output/(name+'.hex')).write_text(base.helpers.intel_hex(data),encoding='ascii',newline='\n')
    base.helpers.run([node,ROOT/'tools/verify-tiny-speech.mjs',output/'firmware.bin',output/'expected.raw',output/'verification.json',
        '--eeprom',output/'eeprom.bin','--phrase-samples',len(pcm),'--loops',3,'--playback','once',
        '--minimum-sp',symbols['STACK_FLOOR'],'--wait-pc',symbols['wait_slot'],'--actual-raw',output/'actual.raw'],ROOT)
    v=json.loads((output/'verification.json').read_text());assert v['pass']
    report=dict(schema='q3-half-pitch-probe-build-v1',status='verified',hardware_tested=False,
        flash_bytes=flash,code_bytes=code,eeprom_bytes=64,stream_bytes=len(payload),waveform_bytes=layout['book_bytes'],
        speech_prefix_bytes=prefix,phrase_samples=len(pcm),half_frames=int(flags.sum()),active_forms=layout['active_forms'],
        phrase_pcm_sha256=base.sha(pcm.tobytes()),firmware_sha256=base.sha(image),eeprom_sha256=base.sha(eeprom),
        asm_sha256_normalized_lf=base.sha(source.encode()),zero_flag_pcm_exact=True,verification=v)
    (output/'build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:report[k] for k in ('status','code_bytes','flash_bytes','stream_bytes','half_frames')}),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('model','output','avr-bin','node'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--zero-flags',action='store_true')
    a=p.parse_args();build(a.model,a.output,a.avr_bin,a.node,zero_flags=a.zero_flags)
