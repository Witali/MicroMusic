"""Compile the real host/AVR backend-selection table, without faking CPU macros."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--avr-gcc', required=True)
    args = parser.parse_args()
    output = Path(tempfile.mkdtemp(prefix='backend-selection-', dir=ROOT / 'build'))
    source = output / 'select.c'
    source.write_text('#include "speex_platform.h"\n'
        '#include "speex_wb1.h"\n'
        '_Static_assert(SPEEX_ENABLE_WB1 == EXPECT_WB, "WB feature selection");\n'
        '_Static_assert(SPEEX_ENABLE_NB4 == EXPECT_NB4, "NB4 feature selection");\n'
        '_Static_assert(SPEEX_NB3_ARCH == EXPECT_ARCH, "Architecture selection");\n'
        '_Static_assert(SPEEX_NB3_USE_AVR_ASM == EXPECT_ASM, "Backend selection");\n')
    port = output / 'test_port.h'
    port.write_text('#define SPEEX_NB3_ARCH SPEEX_NB3_ARCH_ARM\n'
                    '#define SPEEX_NB3_ENABLE_ASM 1\n')
    rows = []
    cases = [
        ('host-default', False, [], 'GENERIC', 0),
        ('host-asm-requested', False, ['SPEEX_NB3_ENABLE_ASM=1'], 'GENERIC', 0),
        ('host-arm', False, ['SPEEX_NB3_ARCH=SPEEX_NB3_ARCH_ARM', 'SPEEX_NB3_ENABLE_ASM=1'], 'ARM', 0),
        ('host-avr-without-avr-abi', False, ['SPEEX_NB3_ARCH=SPEEX_NB3_ARCH_AVR', 'SPEEX_NB3_ENABLE_ASM=1'], 'AVR', 0),
        ('host-unknown', False, ['SPEEX_NB3_ARCH=99', 'SPEEX_NB3_ENABLE_ASM=1'], '99', 0),
        ('avr-default', True, [], 'AVR', 0),
        ('avr-enabled', True, ['SPEEX_NB3_ENABLE_ASM=1'], 'AVR', 1),
        ('avr-disabled', True, ['SPEEX_NB3_ENABLE_ASM=0'], 'AVR', 0),
        ('avr-unknown', True, ['SPEEX_NB3_ARCH=99', 'SPEEX_NB3_ENABLE_ASM=1'], '99', 0),
        ('host-platform-header', False, ['SPEEX_NB3_PLATFORM_HEADER="test_port.h"'], 'ARM', 0),
        ('avr-platform-header', True, ['SPEEX_NB3_PLATFORM_HEADER="test_port.h"'], 'ARM', 0),
    ]
    cases=[(name+'-wb'+str(wb),avr,definitions+['SPEEX_ENABLE_WB1='+str(wb),
        'EXPECT_WB='+str(wb)],architecture,asm) for name,avr,definitions,architecture,asm in cases for wb in (0,1)]
    cases=[(name+'-nb4'+str(high),avr,definitions+(['SPEEX_ENABLE_NB4=1'] if high else [])+
        ['EXPECT_NB4='+str(high)],architecture,asm) for name,avr,definitions,architecture,asm in cases for high in (0,1)]
    for name, avr, definitions, architecture, asm in cases:
        compiler = args.avr_gcc if avr else args.cc
        expected_arch = architecture if architecture.isdigit() else 'SPEEX_NB3_ARCH_' + architecture
        subprocess.run([compiler, '-std=c11', *(['-mmcu=atmega328p'] if avr else []),
            '-I' + str(ROOT / 'src'), '-I' + str(output),
            '-DEXPECT_ARCH=' + expected_arch, '-DEXPECT_ASM=' + str(asm),
            *['-D' + d for d in definitions], '-c', str(source), '-o', str(output / (name + '.o'))],
            check=True, capture_output=True)
        rows.append({'case': name, 'architecture': architecture, 'avrAsmSelected': bool(asm)})
    # A real AVR without hardware MUL must also fall back to C despite opt-in.
    subprocess.run([args.avr_gcc, '-std=c11', '-mmcu=attiny85', '-I' + str(ROOT / 'src'),
        '-DSPEEX_NB3_ENABLE_ASM=1', '-DEXPECT_ARCH=SPEEX_NB3_ARCH_AVR', '-DEXPECT_ASM=0', '-DEXPECT_WB=0', '-DEXPECT_NB4=0',
        '-c', str(source), '-o', str(output / 'avr-no-mul.o')], check=True, capture_output=True)
    rows.append({'case': 'attiny85-no-hardware-mul', 'architecture': 'AVR', 'avrAsmSelected': False})
    for avr in (False,True):
        invalid=subprocess.run([args.avr_gcc if avr else args.cc,'-std=c11',*(['-mmcu=atmega328p'] if avr else []),
            '-I'+str(ROOT/'src'),'-DSPEEX_ENABLE_NB4=2','-DEXPECT_ARCH=SPEEX_NB3_ARCH_'+('AVR' if avr else 'GENERIC'),
            '-DEXPECT_ASM=0','-DEXPECT_WB=0','-DEXPECT_NB4=2','-c',str(source),'-o',str(output/'invalid.o')],capture_output=True)
        assert invalid.returncode and b'SPEEX_ENABLE_NB4' in invalid.stderr
    report = {'compilers': [args.cc, args.avr_gcc],
              'defaultIsC': True, 'unsupportedArchitectureFallsBackToC': True,
              'platformHeaderOverrideVerified': True, 'invalidFeatureRejectedHostAndAvr': True, 'cases': rows}
    (ROOT / 'build/backend-selection.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS:', len(rows), 'backend configurations; real compiler CPU macros retained')
