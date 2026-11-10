"""Measure a private ATmega328P v9 port against public, frozen Tiny88 inputs.

Requires Python stdlib, AVR-GCC, g++, simavr1.6 development files and libelf.
No production source is changed. Generated source/header/license copies and
all firmware remain under a fresh ignored build/ directory. This is a native
simavr prototype measurement, not admission of the production Nano player.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ACTIVE = Path(__file__).resolve().parents[1]
REPO = ACTIVE.parents[2]
RECEIPT = ACTIVE/'examples/ATTINY88_V5_PLAYER/v9-sparse80-measurements.json'
CASES = ('chego-2k', 'chego-compact', 'chego-quality',
         's80-changing-lag18-pre16383-bright11468')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def text_sha(data):
    return sha(data.replace(b'\r\n', b'\n'))


def replace(text, old, new, count=1):
    """Fail closed when the production source no longer matches this port."""
    if text.count(old) != count:
        raise ValueError('Private port source pattern changed')
    return text.replace(old, new)


def adapt_player(text):
    text = replace(text, '__AVR_ATtiny88__', '__AVR_ATmega328P__')
    text = replace(text, 'real ATtiny88 target', 'real ATmega328P target')
    text = replace(text, 'static void stop(){TCCR0A=0;TIMSK0=0;',
                   'static void stop(){TCCR0A=0;TCCR0B=0;TIMSK0=0;')
    return replace(text, 'TCCR0A=_BV(CTC0)|_BV(CS01);',
                   'TCCR0A=_BV(WGM01);TCCR0B=_BV(CS01);')


def adapt_observer(text):
    start = text.index('#define BIT(r,b)')
    end = text.index('static unsigned head,tail', start)
    text = text[:start]+'static avr_t *cpu;\n'+text[end:]
    text = text.replace('cpu.', 'cpu->').replace('&cpu', 'cpu')
    text = replace(text, 'if(avr_init(cpu)<0)return 2;',
        'cpu=avr_make_mcu_by_name("atmega328p");if(!cpu || avr_init(cpu)<0)return 2;')
    text = replace(text, 'decode_active=cpu->data[H_TCCR0A]!=0;',
                   'decode_active=cpu->data[H_TCCR0B]!=0;')
    text = replace(text, '!cpu->data[H_TCCR0A]&&!cpu->data[H_TIMSK0]',
                   '!cpu->data[H_TCCR0A]&&!cpu->data[H_TCCR0B]&&!cpu->data[H_TIMSK0]')
    text = replace(text, 'static FILE *out;', 'static FILE *out,*valid_out;')
    text = replace(text, 'static uint8_t expected;',
        'static uint8_t expected,entry_r0,entry_r1;\n'
        'static unsigned expected_valid;\n'
        'static uint64_t irq_r1_nonzero,irq_r0_nonzero;')
    text = replace(text, 'in_irq=1;ticks++;irq_start=cpu->cycle;',
        'in_irq=1;ticks++;irq_start=cpu->cycle;'
        'entry_r0=cpu->data[0];entry_r1=cpu->data[1];'
        'irq_r1_nonzero+=entry_r1!=0;irq_r0_nonzero+=entry_r0!=0;')
    text = replace(text, 'if(!count)underruns++;',
                   'expected_valid=count!=0;if(!count)underruns++;')
    text = replace(text, 'last=cpu->cycle;fputc(value&255,out);',
                   'last=cpu->cycle;fputc(value&255,out);'
                   'if(expected_valid)fputc(value&255,valid_out);')
    text = replace(text, 'out=fopen(argv[2],"wb");if(!out)return 2;',
        'out=fopen(argv[2],"wb");if(!out)return 2;'
        'char *valid_name=malloc(strlen(argv[2])+7);if(!valid_name)return 2;'
        'sprintf(valid_name,"%s.valid",argv[2]);'
        'valid_out=fopen(valid_name,"wb");free(valid_name);if(!valid_out)return 2;')
    text = replace(text, 'uint64_t duration=cpu->cycle-irq_start;irq_total+=duration;',
        'if(cpu->data[0]!=entry_r0 || cpu->data[1]!=entry_r1){'
        'fprintf(stderr,"IRQ failed to restore MUL scratch registers\\n");return 7;}\n'
        '   uint64_t duration=cpu->cycle-irq_start;irq_total+=duration;')
    text = replace(text, 'fclose(out);FILE *report=', 'fclose(out);fclose(valid_out);FILE *report=')
    text = replace(text, '\\"timer_stopped\\":%s}\\n',
        '\\"timer_stopped\\":%s,\\"irq_r1_nonzero\\":%llu,'
        '\\"irq_r0_nonzero\\":%llu,\\"irq_registers_preserved\\":true}\\n')
    return replace(text,
        '!cpu->data[H_TCCR0A]&&!cpu->data[H_TCCR0B]&&!cpu->data[H_TIMSK0]?"true":"false");',
        '!cpu->data[H_TCCR0A]&&!cpu->data[H_TCCR0B]&&!cpu->data[H_TIMSK0]?"true":"false",'
        '(unsigned long long)irq_r1_nonzero,(unsigned long long)irq_r0_nonzero);')


def adapt_builder(text):
    for old, new, count in (
        ("'-mmcu=attiny88'", "'-mmcu=atmega328p'", 1),
        ("raise ValueError('Hardware multiply in an AVR25 function')",
         "if reserved:raise ValueError('This port requires the ordinary C ISR')", 1),
        ('flash_limit=8192', 'flash_limit=32768', 1),
        ('flash_limit<=8192', 'flash_limit<=32768', 1),
        ("registers='TCCR0A TCNT0", "registers='TCCR0A TCCR0B TCNT0", 1),
        ("constants='CTC0 ", "constants='WGM01 ", 1),
        ("DFP/'avr/iotn88.h'", "DFP/'avr/iom328p.h'", 1),
        ("target='attiny88'", "target='atmega328p'", 1),
        ('bootloader_application_bytes=6012,fits_standard_bootloader=len(image)<=6012,',
         'bootloader_application_bytes=None,fits_standard_bootloader=None,', 1),
        ('requires_isp=len(image)>6012,', 'requires_isp=None,', 1),
        ('// Generated from the pinned vendor ATtiny88 header; observer only.',
         '// Generated from the compiler-selected ATmega328P header; observer only.', 1),
    ):
        text = replace(text, old, new, count)
    return text


def adapt_verifier(text):
    text = replace(text, 'from build_attiny88_player import', 'from build_mega_player import')
    text = replace(text, 'flash_limit=8192', 'flash_limit=32768')
    text = replace(text, "cost['static_ram_bytes']+timing['stack_bytes']<512",
                   "cost['static_ram_bytes']+timing['stack_bytes']<2048")
    return replace(text, "run('g++','-O2','-std=c++11',",
                   "run('g++','-O2','-std=c++11','-DLPX4_ENABLE_ASM=0',")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(output, *, wsl=None):
    output = Path(output).resolve()
    if not output.is_relative_to((REPO/'build').resolve()) or output == REPO/'build':
        raise ValueError('Use a fresh ignored build/ subdirectory')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    prefix = ['wsl', '-d', wsl, '--'] if wsl else []
    def command(*args, input=None):
        r = subprocess.run([*prefix, *map(str, args)], input=input, capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr.decode(errors='replace'))
        return r.stdout
    def target(path):
        path = Path(path).resolve()
        if wsl and path.drive:
            return '/mnt/'+path.drive[0].lower()+'/'+'/'.join(path.parts[1:])
        return str(path)
    private_repo = output/'source'
    port = private_repo/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
    device = private_repo/'device'
    source_paths = [Path(__file__), ACTIVE/'tools/build_attiny88_player.py',
        ACTIVE/'tools/verify_attiny88_player.py', ACTIVE/'tools/speech_v9.py',
        ACTIVE/'tests/test_speech_v9.py', ACTIVE/'tests/test_sram512_profile.py',
        ACTIVE/'examples/ATTINY88_V5_PLAYER/player.cpp', ACTIVE/'profiles/Lpx4Sram512.h',
        ACTIVE.parent/'validation/attiny88/sim_player.c',
        *sorted((ACTIVE/'src').glob('Lpx4*')), *sorted((REPO/'Codecs/common').rglob('*.h'))]
    source_hashes = {p.relative_to(REPO).as_posix():text_sha(p.read_bytes()) for p in source_paths}
    frozen = json.loads(RECEIPT.read_text())
    # Timing comparison is to the SAME frozen core, not a silently newer decoder.
    for name, digest in frozen['source_sha256'].items():
        if '/src/Lpx4' in name and text_sha((REPO/name).read_bytes()) != digest:
            raise ValueError('Core differs from the frozen Tiny88 comparison')
    for part in ('src', 'profiles', 'examples/ATTINY88_V5_PLAYER'):
        shutil.copytree(ACTIVE/part, port/part, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(REPO/'Codecs/common', private_repo/'Codecs/common')
    observer = port.parent/'validation/attiny88/sim_player.c'
    observer.parent.mkdir(parents=True)
    observer.write_text(adapt_observer((ACTIVE.parent/'validation/attiny88/sim_player.c').read_text()),
                        encoding='utf-8', newline='\n')
    player = port/'examples/ATTINY88_V5_PLAYER/player.cpp'
    player.write_text(adapt_player(player.read_text()), encoding='utf-8', newline='\n')
    # Compiler-selected avr-libc header: keep original license, no address copies.
    probe = subprocess.run([*prefix, 'avr-g++', '-mmcu=atmega328p', '-E', '-H', '-x', 'c++', '-'],
                           input=b'#include <avr/io.h>\n', capture_output=True)
    if probe.returncode:
        raise RuntimeError('Device header probe failed')
    header = next(line.split()[-1] for line in probe.stderr.decode().splitlines()
                  if line.strip().endswith('/avr/iom328p.h'))
    data = command('cat', header)
    (device/'avr').mkdir(parents=True)
    (device/'avr/iom328p.h').write_bytes(data)
    macros = command('avr-g++', '-mmcu=atmega328p', '-dM', '-E', '-x', 'c++', '-',
                     input=b'#include <avr/io.h>\n#include <avr/version.h>\n').decode()
    definitions = dict(re.findall(r'^#define (\S+) (.+)$', macros, re.M))
    if definitions['__AVR_ARCH__'] != '5' or '__AVR_HAVE_MUL__' not in definitions:
        raise ValueError('Expected real AVR5 hardware multiplication target')
    provenance = dict(header='avr/iom328p.h', header_sha256=sha(data),
        origin='Compiler-selected avr-libc header; original license retained in generated copy',
        upstream='https://avrdudes.github.io/avr-libc/',
        avr_libc_version=definitions.get('__AVR_LIBC_VERSION_STRING__'),
        architecture=definitions['__AVR_ARCH__'], hardware_mul_defined=True,
        sample_vector=int(definitions['TIMER0_COMPA_vect_num']))
    for name, transform, source in (
        ('build_mega_player', adapt_builder, 'build_attiny88_player'),
        ('verify_mega_player', adapt_verifier, 'verify_attiny88_player')):
        (output/(name+'.py')).write_text(transform((ACTIVE/'tools'/ (source+'.py')).read_text()),
                                         encoding='utf-8', newline='\n')
    sys.path[:0] = [str(output), str(ACTIVE/'tools'), str(ACTIVE/'tests')]
    from speech_v9 import repack
    from test_speech_v9 import sparse_fixture
    public = [ACTIVE/'tests/fixtures/chego-2k-v8.lpx',
              REPO/'web-player/audio/lpx-speech/chego/compact.lpx',
              REPO/'web-player/audio/lpx-speech/chego/quality.lpx']
    blobs = [repack(p.read_bytes())[0] for p in public]
    blobs.append(repack(sparse_fixture(12800, 'changing', 16383, 11468, 18)[0])[0])
    input_hashes = {p.relative_to(REPO).as_posix():sha(p.read_bytes()) for p in public}
    builder = load('build_mega_player', output/'build_mega_player.py')
    builder.ROOT, builder.REPO, builder.DFP = port, REPO, device
    verifier = load('verify_mega_player', output/'verify_mega_player.py')
    build_original = verifier.build
    # Match the ASM recipe's inlining option for the explicitly selected C control.
    def matched_build(*args, **kwargs):
        if not kwargs.get('assembly', False):
            kwargs['extra_flags'] = ('-finline-small-functions',)
        return build_original(*args, **kwargs)
    verifier.build = matched_build
    port_hashes = {p.relative_to(private_repo).as_posix():text_sha(p.read_bytes())
                   for p in private_repo.rglob('*') if p.is_file()}
    generated_hashes = {name:text_sha((output/name).read_bytes()) for name in
                        ('build_mega_player.py', 'verify_mega_player.py')}
    rows = []
    for backend, names in (('asm', CASES), ('c', CASES[:1])):
        for name in names:
            index = CASES.index(name)
            golden = next(r for r in frozen['cases'] if r['case'] == name)
            blob = blobs[index]
            if sha(blob) != golden['data_sha256']:
                raise ValueError('Public input no longer matches the frozen stream')
            folder = output/backend/name
            folder.mkdir(parents=True)
            source = folder/'stream.lpx'
            source.write_bytes(blob)
            result = verifier.verify(source, folder, wsl=wsl, assembly=backend=='asm',
                                     asm_isr=False, queue=32)
            expected = (folder/'expected.pwm').read_bytes()
            valid = (folder/'actual.pwm.valid').read_bytes()
            if sha(expected) != golden['pwm_sha256'] or valid != expected:
                raise AssertionError('Dequeued PWM differs from explicit native C / frozen oracle')
            if not (result['irq_registers_preserved'] and result['error']==0 and
                    result['eof']==result['stopped']==1 and result['queue_empty'] and
                    result['timer_stopped'] and result['stack_margin']>0 and
                    result['samples']==len(valid)+result['underruns'] and
                    result['decode_calls']==len(expected)):
                raise AssertionError('Playback completion / stack / IRQ preservation failed')
            if backend=='asm' and not result['accepted']:
                raise AssertionError('ASM playback failed its full real-time gate')
            cost = json.loads((folder/'build.json').read_text())
            options = [option.replace(target(output), '<output>') for option in cost['compiler_options']]
            # Verify real architecture and explicit backend using the exact build flags.
            backend_macros = command('avr-g++', *cost['compiler_options'], '-dM', '-E',
                '-x', 'c++', '-', input=b'#include "Lpx4Math.h"\n').decode()
            backend_defines = dict(re.findall(r'^#define (\S+) (.+)$', backend_macros, re.M))
            if backend_defines['LPX4_USE_AVR_ASM'] != str(int(backend=='asm')):
                raise AssertionError('Arithmetic backend selection differs from request')
            row = dict(case=name, backend=backend, samples=len(expected),
                embedded_audio_bytes=len(blob), program_excluding_audio_bytes=result['program_excluding_audio_bytes'],
                flash_bytes=result['flash_bytes'], static_ram_bytes=result['static_ram_bytes'],
                stack_bytes=result['stack_bytes'], stack_margin=result['stack_margin'],
                decode_active_cpu_mean=result['decode_active_cpu_mean'], irq_max=result['irq_max'],
                total_active_cycles_per_sample=result['decode_active_cpu_mean']+result['irq_max'],
                accepted_real_time=result['accepted'], underruns=result['underruns'],
                pwm_exact=result['pwm_exact'], dequeued_pwm_exact=True, input_sha256=sha(blob),
                pwm_sha256=sha(expected), irq_r1_nonzero=result['irq_r1_nonzero'],
                irq_registers_preserved=True, output_samples=result['samples'],
                output_gap_min=result['output_gap_min'], output_gap_max=result['output_gap_max'],
                compiler_options=options, compiler=cost['compiler'],
                backend_macro=int(backend_defines['LPX4_USE_AVR_ASM']),
                tiny_total_active_cycles_per_sample=golden['total_active_cycles_per_sample'],
                tiny_program_excluding_audio_bytes=golden['after']['program_excluding_audio_bytes'],
                outcome='real-time' if result['accepted'] else 'throughput rejected; decoded PWM exact')
            rows.append(row)
            (output/'progress.json').write_text(json.dumps(rows, indent=2)+'\n')
            print(json.dumps({k:row[k] for k in ('case','backend','program_excluding_audio_bytes',
                'total_active_cycles_per_sample','underruns','dequeued_pwm_exact','outcome')}), flush=True)
    for name, digest in source_hashes.items():
        if text_sha((REPO/name).read_bytes()) != digest:
            raise RuntimeError('Production source changed during measurement')
    if port_hashes != {p.relative_to(private_repo).as_posix():text_sha(p.read_bytes())
                      for p in private_repo.rglob('*') if p.is_file()}:
        raise RuntimeError('Private source changed during measurement')
    summary = dict(schema='lpx-atmega328p-v9-v1', source_hash_encoding='text-lf',
        production_source_sha256=source_hashes, generated_source_sha256=port_hashes,
        generated_tool_sha256=generated_hashes, public_input_sha256=input_hashes,
        frozen_tiny_receipt_sha256=text_sha(RECEIPT.read_bytes()),
        production_source_unchanged=True, physical_board_measured=False, private_port=True,
        target='atmega328p', clock_hz=16000000, sample_hz=8000, queue=32, prefill=24,
        lpc_segments=2, memory_profile='SRAM512', physical_ram_bytes=2048,
        device_provenance=provenance, simavr_version=command('pkg-config','--modversion','simavr').decode().strip(),
        cycle_accounting='active decoder CPU mean plus maximum complete ISR; queue management excluded',
        scope='Private Tiny-style one-shot port with native simavr ATmega328P and ordinary C ISR; not production Nano firmware',
        c_control='Same compiler options including -finline-small-functions; explicit C arithmetic. A throughput rejection is retained, not treated as an arithmetic failure.',
        cases=rows, complete=True)
    (output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n',
                                       encoding='utf-8', newline='\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--wsl')
    args = parser.parse_args()
    run(args.output, wsl=args.wsl)


if __name__ == '__main__':
    main()
