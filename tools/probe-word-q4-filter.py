"""Measure an assembled word lattice on complete retained PC speech streams.

Excitation and coefficient transport are supplied by the fixture host. This
qualifies the actual arithmetic chain, not a playable 1 KB firmware image.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('word_filter_product_api',ROOT/'tools/fit-q4-product233.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


def run(avr_bin,node,output,state_bits=4,profile='compact',coefficient_memory='flash',model_path=None):
    if state_bits not in (4,6):raise ValueError('Expected four or six fractional state bits')
    if profile not in ('compact','factored','adaptive','unrolled'):raise ValueError('Unknown word multiply profile')
    if coefficient_memory not in ('flash','ram'):raise ValueError('Expected Flash or SRAM coefficients')
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    source=ROOT/'ATtiny13A/Sound/codec/word-q4/filter.S'
    multiply=source.with_name('multiply.S' if profile in ('compact','unrolled') else 'multiply-factored.S')
    fixture='''.section .text
.global __vectors
__vectors:
 rjmp halt
.org 6
 rjmp irq
halt:
 rjmp halt
'''+f'.equ WORD_STATE_BITS,{state_bits}\n'+('.equ WORD_COEFFICIENTS_IN_RAM,1\n' if coefficient_memory=='ram' else '')+('.equ WORD_MUL_ADAPTIVE,1\n' if profile=='adaptive' else '.equ WORD_MUL_UNROLLED,1\n' if profile=='unrolled' else '')+''.join('.include '+json.dumps(p.as_posix())+'\n' for p in (source,multiply))+'''
irq:
 push r16
 in r16,0x3f
 push r16
 ldi r16,0xa5
 eor r16,r16
 sec
 clt
 pop r16
 out 0x3f,r16
 pop r16
 reti
.global coefficient_data
'''+('.equ coefficient_data,0x72\n' if coefficient_memory=='ram' else 'coefficient_data:\n .space 8,0\n')
    (output/'fixture.S').write_text(fixture,encoding='utf-8',newline='\n')
    suffix='.exe' if sys.platform=='win32' else ''
    execute=lambda c:subprocess.run(list(map(str,c)),cwd=output,capture_output=True,text=True,check=True,timeout=300).stdout
    execute([avr_bin/('avr-gcc'+suffix),'-mmcu=attiny13a','-nostdlib','-Wl,--defsym=__TEXT_REGION_LENGTH__=1024','-x','assembler','fixture.S','-o','fixture.elf'])
    execute([avr_bin/('avr-objcopy'+suffix),'-O','binary','fixture.elf','fixture.bin'])
    symbols={}
    for line in execute([avr_bin/('avr-nm'+suffix),'-n','fixture.elf']).splitlines():
        fields=line.split()
        if len(fields)==3:symbols[fields[2]]=int(fields[0],16)
    cases=[]
    model_paths=(
        ('nearest',ROOT/'ATtiny13A/Sound/research/q4-lattice/followups/nearest/model.json'),
        ('product-four',ROOT/'ATtiny13A/Sound/research/q4-pattern-precision/product/four-form-fit/model.json')) if state_bits==4 else (
        ('mixed-q8',ROOT/'ATtiny13A/Sound/research/q4-pattern-precision/mixed/q8/model.json'),)
    if model_path is not None:model_paths=(('custom',model_path),)
    for name,path in model_paths:
        meta=json.loads(path.read_text(encoding='utf-8'))
        excitation_bits=2
        if meta['state_bits']!=state_bits or not meta['nearest']:raise ValueError('Expected matching word states and nearest rounding')
        if meta['schema'].startswith('q4-product233'):
            state=fit.from_model(meta);expanded=fit.expand(state)
            flags=(state.attack_flags[state.indices[:,1]]<<1)|state.hold_flags[state.indices[:,2]]
            modes=flags^(flags>>1)
            rows,excitation=fit.fit.codec.legacy_excitation(expanded.pitches,expanded.gains_q1,expanded.durations,expanded.modes,expanded.waves_q1,expanded.halves,phase_modes=modes)
            excitation[expanded.pitches[rows]==0]*=2
            expected,counts=fit.render(state,4,True)
        elif meta['schema'] in ('mixed-lattice-v1','mixed-lattice-pulse-v1','mixed-lattice-balanced-v1'):
            if meta['coefficient_bits']!=[4]*8:raise ValueError('This kernel requires Q4 in all eight stages')
            s=importlib.util.spec_from_file_location('word_filter_mixed_api',ROOT/'tools/fit-mixed-lattice.py')
            mixed=importlib.util.module_from_spec(s);sys.modules[s.name]=mixed;s.loader.exec_module(mixed)
            expanded,bits,_,mode,_,_,_=mixed.load(path)
            rows,excitation=fit.fit.codec.legacy_excitation(expanded.pitches,expanded.gains_q1,expanded.durations,
                expanded.modes,expanded.waves_q1,expanded.quarters,pitch_bits=2,phase_mode=mode,
                phase_modes=expanded.phase_modes,pulse_width=expanded.waves_q1.shape[1])
            excitation[expanded.pitches[rows]==0]*=1<<expanded.wave_fraction_bits
            excitation_bits=expanded.wave_fraction_bits+1
            expected,counts=mixed.render(expanded,bits,state_bits,mode)
        else:
            expanded=fit.fit.load(path)
            rows,excitation=fit.fit.codec.legacy_excitation(expanded.pitches,expanded.gains_q1,expanded.durations,expanded.modes,expanded.waves_q1,expanded.halves)
            excitation[expanded.pitches[rows]==0]*=2
            expected,counts=fit.fit.render(expanded,state_bits,True)
        if np.any(counts):raise ValueError('Starting stream wraps')
        inputs=np.column_stack((excitation.astype(np.int16)*(1<<(state_bits-excitation_bits)),expanded.coefficients[rows]))
        input_path=output/(name+'-input.json');input_path.write_text(json.dumps(inputs.tolist()),encoding='utf-8')
        expected.tofile(output/(name+'-expected.raw'))
        cases.append(dict(name=name,input=str(input_path),expected=str(output/(name+'-expected.raw')),model_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    specification=dict(image=str(output/'fixture.bin'),symbols=symbols,cases=cases,stateBits=state_bits,coefficientMemory=coefficient_memory,
        filterBytes=symbols['word_filter_end']-symbols['filter_word_q4'],multiplyBytes=symbols['word_mul_end']-symbols['mul_word_q4'])
    (output/'spec.json').write_text(json.dumps(specification),encoding='utf-8')
    execute([node,ROOT/'tools/verify-word-q4-filter.mjs',output/'spec.json',output/'verification.json'])
    report=json.loads((output/'verification.json').read_text())
    report.update(profile=profile,fixture_bytes=(output/'fixture.bin').stat().st_size,source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
        for p in (Path(__file__),source,multiply,ROOT/'tools/verify-word-q4-filter.mjs')})
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('avr-bin','node','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--state-bits',type=int,choices=(4,6),default=4)
    p.add_argument('--profile',choices=('compact','factored','adaptive','unrolled'),default='compact')
    p.add_argument('--coefficients',choices=('flash','ram'),default='flash');p.add_argument('--model',type=Path)
    a=p.parse_args();run(a.avr_bin,a.node,a.output,a.state_bits,a.profile,a.coefficients,a.model)
