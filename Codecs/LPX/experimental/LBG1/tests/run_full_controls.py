"""Full LG player controls: real curves, partial packets, reset and C override.

Uses the same staged production player/FIFO/ISR and complete-stream observer
as avr/run_full.py. Run inside the installed Linux/WSL toolchain. A control
manifest has cases[{name,path,pcm?,repeat?:1|2,backends?:[asm,c,generic]}].
Generic explicitly sets LPX4_ENABLE_ASM=1 and LPX4_ARCH=0, while retaining
real __AVR__ memory/device macros. It is a C arithmetic override control.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'avr'))
import run_full as full


def run(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout


def layout(output, cost):
    text = '#include "Lpx4HybridCore.h"\nextern "C" const unsigned short metadata[] __attribute__((used,section(".lg_meta")))={'
    text += 'sizeof(Lpx4HybridCore),LPX4_ENABLE_ASM,LPX4_ARCH,LPX4_USE_AVR_ASM,LPX4_USE_AVR_NOMUL_ASM,__AVR_ARCH__};\n'
    (output / 'layout.cpp').write_text(text, encoding='ascii', newline='\n')
    flags = [flag for flag in cost['compiler_options'] if flag != '-flto']
    run('avr-g++', *flags, '-c', output / 'layout.cpp', '-o', output / 'layout.o')
    run('avr-objcopy', '-O', 'binary', '-j', '.lg_meta', output / 'layout.o', output / 'layout.bin')
    data = (output / 'layout.bin').read_bytes()
    if len(data) != 12:
        raise AssertionError('Unexpected decoder metadata size')
    names = ('decoder_bytes', 'explicit_assembly_enable', 'selected_architecture',
             'hardware_asm_selected', 'software_asm_selected', 'real_avr_architecture')
    return {name: int.from_bytes(data[i * 2:i * 2 + 2], 'little') for i, name in enumerate(names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = full.safe_build(args.output)
    if output.exists():
        raise ValueError('Use a fresh control output directory')
    output.mkdir(parents=True)
    observer = full.prepare_observer(output)
    stage = full.prepare_stage(output)
    cases = json.loads(args.manifest.read_text())['cases']
    report = dict(schema='lbg1-full-avr-controls-v1', manifest_sha256=full.sha(args.manifest),
                  source_sha256=full.sha(Path(__file__)), parent_runner_sha256=full.sha(full.__file__),
                  physical_board_measured=False, rows=[])
    for case in cases:
        source = (full.REPO / case['path']).resolve()
        if source.read_bytes()[:2] != b'LG':
            raise ValueError('Controls require actual LG bytes')
        inputs = full.freeze_inputs([(case['name'], 'control', str(source),
                                      str((full.REPO / case['pcm']).resolve()) if case.get('pcm') else None)],
                                    output / case['name'])
        _, _, frozen, pcm = inputs[0]
        repeat = case.get('repeat', 1)
        if repeat not in (1, 2):
            raise ValueError('Use one or two complete reset playbacks')
        for target in ('attiny88', 'atmega328p'):
            for backend in case.get('backends', ('asm', 'c')):
                directory = output / case['name'] / target / backend
                directory.mkdir(parents=True)
                row = dict(case=case['name'], target=target, backend=backend, repeat=repeat,
                           source_sha256=full.sha(frozen), source_bytes=Path(frozen).stat().st_size)
                try:
                    builder, verifier = full.modules('lg1', stage, observer)
                    metrics = verifier.verify(frozen, directory, assembly=backend != 'c', asm_isr=True,
                                              queue=32, repeat=repeat, universal=True, target=target,
                                              flash_limit=8192 if target == 'attiny88' else 32768,
                                              normalize_output=False, sample_rate=8000,
                                              extra_flags=('-DLPX4_ARCH=0',) if backend == 'generic' else ())
                    expected = (directory / 'expected.pwm').read_bytes()
                    valid = (directory / 'actual.pwm.valid').read_bytes()
                    metrics['valid_pwm_exact'] = valid == expected
                    if not metrics['valid_pwm_exact']:
                        raise AssertionError('Control valid PWM differs from portable C')
                    if pcm:
                        data = Path(pcm).read_bytes()
                        provided = bytearray()
                        for at in range(0, len(data), 2):
                            value = int.from_bytes(data[at:at + 2], 'little', signed=True)
                            provided.append(max(0, min(255, 128 + ((((value + 1) >> 1) * 130 + 8192) >> 14))))
                        metrics['provided_pcm_exact'] = bytes(provided) * repeat == expected
                        if not metrics['provided_pcm_exact']:
                            raise AssertionError('Control portable PWM differs from provided PCM')
                    cost = json.loads((directory / 'build.json').read_text())
                    selection = layout(directory, cost)
                    if backend == 'generic' and (selection['explicit_assembly_enable'] != 1 or selection['selected_architecture'] != 0
                                                 or selection['hardware_asm_selected'] or selection['software_asm_selected']):
                        raise AssertionError('Generic override selected assembly arithmetic')
                    row.update(status='measured', result=metrics, layout=selection)
                except Exception as error:
                    row.update(status='failed', failure=full.normalized(error))
                report['rows'].append(row)
                full.write_json(directory / 'control-result.json', row)
                full.write_json(output / 'results.json', report)
                print(json.dumps({key: row[key] for key in ('case', 'target', 'backend', 'status')}), flush=True)
    report['summary'] = dict(requested=len(report['rows']), measured=sum(row['status'] == 'measured' for row in report['rows']),
                           admitted=sum(row.get('result', {}).get('accepted', False) for row in report['rows']))
    full.write_json(output / 'results.json', report)
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
