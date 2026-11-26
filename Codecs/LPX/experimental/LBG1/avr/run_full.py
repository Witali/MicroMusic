"""Full LPX/LG1 AVR playback using the production FIFO/timer/ISR/observer.

Run inside Linux/WSL with AVR-GCC, g++, simavr1.6 development files and libelf.
The experimental adapter stages source copies under ignored build/, accepts
actual LG bytes with L9-like metadata offsets, and swaps only the decoder.
No production source or device register definition is modified.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ACTIVE = REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
EXPERIMENT = HERE.parent
TOOLS = ACTIVE / 'tools'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Production source pattern changed: ' + old[:100])
    return text.replace(old, new)


def load(name, source, text=None):
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location(name, source))
    sys.modules[name] = module
    if text is None:
        module.__spec__.loader.exec_module(module)
    else:
        exec(compile(text, str(source), 'exec'), module.__dict__)
    return module


def safe_build(path):
    path, build = Path(path).resolve(), (REPO / 'build').resolve()
    if path == build or build not in path.parents:
        raise ValueError('Use a fresh subdirectory below ignored build/')
    return path


def prepare_stage(output):
    """Snapshot all decoder inputs; every later build uses the same snapshot."""
    stage = safe_build(output / 'stage')
    root = stage / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
    for directory in ('src', 'profiles'):
        shutil.copytree(ACTIVE / directory, root / directory)
    player = root / 'examples/ATTINY88_V5_PLAYER'
    player.mkdir(parents=True)
    original_player = ACTIVE / 'examples/ATTINY88_V5_PLAYER/player.cpp'
    text = original_player.read_text()
    # Original ROM-only shortcuts access Lpx4HybridCore private members.
    # LG uses the public begin/next/finished API; hardware and IRQ stay intact.
    text = replace_once(text, '#define LPX25_V9_RUNTIME 1', '#define LPX25_V9_RUNTIME 0')
    text = replace_once(text, '#define LPX25_V9_ROM_PLAYER 1', '#define LPX25_V9_ROM_PLAYER 0')
    (player / 'player.cpp').write_text(text, encoding='utf-8', newline='\n')
    shutil.copy2(original_player.with_name('irq_registers.inc'), player / 'irq_registers.inc')
    common = stage / 'Codecs/common'
    common.mkdir(parents=True)
    shutil.copy2(REPO / 'Codecs/common/pwm_gain.h', common / 'pwm_gain.h')
    observer = root.parent / 'validation/attiny88'
    observer.mkdir(parents=True)
    shutil.copy2(ACTIVE.parent / 'validation/attiny88/sim_player.c', observer / 'sim_player.c')
    original_header = (root / 'src/Lpx4HybridCore.h').read_text()
    (root / 'src/Lpx4BaselineDeclarations.h').write_text(original_header, encoding='utf-8', newline='\n')
    # Renaming declarations retains production compile-time math configuration
    # without instantiating or linking the original class or its ROM decoder.
    (root / 'src/Lpx4HybridCore.h').write_text(
        '#pragma once\n#define Lpx4HybridCore Lpx4BaselineDeclarations\n'
        '#include "Lpx4BaselineDeclarations.h"\n#undef Lpx4HybridCore\n'
        '#include "decoder.h"\nusing Lpx4HybridCore=lbg1::Decoder;\n',
        encoding='ascii', newline='\n')
    decoder_before = {name: sha(EXPERIMENT / name) for name in ('decoder.h', 'decoder.cpp')}
    for name in ('decoder.h', 'decoder.cpp'):
        shutil.copy2(EXPERIMENT / name, root / 'src' / name)
    if decoder_before != {name: sha(EXPERIMENT / name) for name in decoder_before} or any(
            sha(root / 'src' / name) != digest for name, digest in decoder_before.items()):
        raise ValueError('Decoder changed during snapshot; use a fresh run')
    (root / 'src/Lpx4HybridCore.cpp').write_text(
        '#include "Lpx4HybridCore.h"\n#include "decoder.cpp"\n', encoding='ascii', newline='\n')
    snapshot = {path.relative_to(REPO).as_posix(): sha(path)
                for path in sorted(stage.rglob('*')) if path.is_file()}
    write_json(output / 'stage.json', dict(
        original_player_sha256=sha(original_player),
        original_builder_sha256=sha(TOOLS / 'build_attiny88_player.py'),
        original_verifier_sha256=sha(TOOLS / 'verify_attiny88_player.py'),
        original_observer_sha256=sha(ACTIVE.parent / 'validation/attiny88/sim_player.c'),
        decoder_inputs=decoder_before,
        modifications=['Accept LG as a metadata-offset class only; preserve actual LG bytes.',
                       'Alias the public production decoder name to lbg1::Decoder.',
                       'Disable original private ROM-player shortcuts; preserve hardware/FIFO/ISR source.',
                       'Compile the snapshotted LG implementation instead of original core.cpp.'],
        files=snapshot))
    return root


def prepare_observer(output):
    """Add valid-only Tiny PWM output without changing timing/model logic."""
    source = ACTIVE.parent / 'validation/attiny88/sim_player.c'
    text = source.read_text()
    text = replace_once(text, '#include "hardware.h"', '#include "hardware.h"\n#ifndef H_LPX_NATIVE_TARGET\nstatic FILE *valid_out;\nstatic unsigned expected_valid;\n#endif')
    text = replace_once(text, 'expected=count?cpu.data[queue+cpu.data[tail]]:128;',
                        'expected_valid=count!=0;expected=count?cpu.data[queue+cpu.data[tail]]:128;')
    text = replace_once(text, 'last=cpu.cycle;fputc(value&255,out);',
                        'last=cpu.cycle;fputc(value&255,out);\n#ifndef H_LPX_NATIVE_TARGET\n if(expected_valid)fputc(value&255,valid_out);\n#endif')
    text = replace_once(text, '#ifdef H_LPX_NATIVE_TARGET\n char *valid_name=', ' char *valid_name=')
    text = replace_once(text, 'valid_out=fopen(valid_name,"wb");free(valid_name);if(!valid_out)return 2;\n#endif',
                        'valid_out=fopen(valid_name,"wb");free(valid_name);if(!valid_out)return 2;')
    text = replace_once(text, '#ifdef H_LPX_NATIVE_TARGET\n fclose(valid_out);\n#endif', ' fclose(valid_out);')
    target = output / 'observer-valid.c'
    target.write_text(text, encoding='utf-8', newline='\n')
    return target


def modules(codec, stage_root=None, observer_source=None):
    name = 'build_attiny88_player'
    if codec == 'baseline':
        builder = load(name, TOOLS / 'build_attiny88_player.py')
    else:
        text = (TOOLS / 'build_attiny88_player.py').read_text()
        text = replace_once(text, "version=9 if blob[:2]==b'L9' else", "version=9 if blob[:2] in (b'L9',b'LG') else")
        text = replace_once(text, "any(data[:2]!=b'L9' for data in blobs)", "any(data[:2] not in (b'L9',b'LG') for data in blobs)")
        builder = load(name, TOOLS / 'build_attiny88_player.py', text)
        builder.ROOT = Path(stage_root)
        builder.REPO = REPO
        builder.DFP = REPO / 'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'
    text = (TOOLS / 'verify_attiny88_player.py').read_text()
    if observer_source:
        text = replace_once(text, "path(ROOT.parent/'validation/attiny88/sim_player.c')", 'path(OBSERVER_SOURCE)')
    verifier = load('lbg1_verify_' + codec, TOOLS / 'verify_attiny88_player.py', text)
    if observer_source:
        verifier.OBSERVER_SOURCE = Path(observer_source)
    return builder, verifier


def normalized(message):
    return str(message).replace(str(REPO), '<repo>')[:4000]


def run_one(job):
    name, variant, source, expected_pcm, target, backend, output, stage_root, nano_pwm, observer_source = job
    output, source = Path(output), Path(source)
    codec = 'baseline' if source.read_bytes()[:2] == b'L9' else 'lg1'
    if source.read_bytes()[:2] not in (b'L9', b'LG'):
        raise ValueError('Expected genuine L9 or LG stream')
    output.mkdir(parents=True)
    record = dict(case=name, variant=variant, codec=codec, target=target, backend=backend,
                  source=source.relative_to(REPO).as_posix(), source_sha256=sha(source),
                  output=output.relative_to(REPO).as_posix(), physical_board_measured=False,
                  complete_file_requested=True)
    try:
        builder, verifier = modules(codec, stage_root, observer_source)
        result = verifier.verify(
            source, output, assembly=backend == 'asm', asm_isr=True, queue=32, repeat=1,
            flash_limit=8192 if target == 'attiny88' else 32768, universal=True,
            normalize_output=False, target=target, nano_pwm=nano_pwm, sample_rate=8000)
        expected = (output / 'expected.pwm').read_bytes()
        actual = (output / 'actual.pwm').read_bytes()
        # Underruns insert output bytes but do not alter the sequence of valid
        # FIFO bytes. Keep both admission equality and diagnostic FIFO equality.
        valid_file = output / 'actual.pwm.valid'
        if valid_file.exists():
            valid = valid_file.read_bytes()
        elif not result['underruns']:
            valid = actual
        else:
            valid = None
        result['valid_pwm_exact_when_available'] = None if valid is None else valid == expected
        result['portable_expected_pwm_sha256'] = hashlib.sha256(expected).hexdigest()
        if expected_pcm:
            data = Path(expected_pcm).read_bytes()
            if len(data) % 2:
                raise ValueError('Odd expected PCM length')
            reference_pwm = bytearray()
            for at in range(0, len(data), 2):
                pcm = int.from_bytes(data[at:at + 2], 'little', signed=True)
                q14 = (pcm + 1) >> 1
                reference_pwm.append(max(0, min(255, 128 + ((q14 * 130 + 8192) >> 14))))
            result['provided_pcm_pwm_exact'] = bytes(reference_pwm) == expected
            if not result['provided_pcm_pwm_exact']:
                raise AssertionError('Provided PCM and portable decoder PWM differ')
        result['hard_flash_fit'] = result['flash_bytes'] <= (8192 if target == 'attiny88' else 32768)
        result['tiny_standard_bootloader_fit'] = result['flash_bytes'] <= 6012 if target == 'attiny88' else None
        result['total_static_and_observed_stack_bytes'] = result['static_ram_bytes'] + result['stack_bytes']
        result['physical_sram_margin_bytes'] = (512 if target == 'attiny88' else 2048) - result['total_static_and_observed_stack_bytes']
        record.update(status='measured', result=result)
    except Exception as error:
        message = normalized(error)
        (output / 'failure.txt').write_text(message + '\n', encoding='utf-8', newline='\n')
        record.update(status='failed', failure=message)
        build = output / 'build.json'
        if build.exists():
            record['build'] = json.loads(build.read_text())
        if 'will not fit' in message or 'overflowed by' in message or 'Complete image is' in message:
            record['failure_kind'] = 'physical_flash_fit'
        elif 'Stack collision' in message:
            record['failure_kind'] = 'sram_stack_collision'
        else:
            record['failure_kind'] = 'build_or_reference_or_observer'
    write_json(output / 'case-result.json', record)
    return record


def cases_from_manifest(path):
    manifest = json.loads(Path(path).read_text())
    rows = manifest.get('cases', manifest.get('rows', manifest if isinstance(manifest, list) else [])) if isinstance(manifest, dict) else manifest
    cases = []
    for row in rows:
        name = row.get('name', row.get('case', row.get('clip', '') + '-p' + str(row.get('level', row.get('profile', '')))))
        variants = row.get('variants', {'baseline': row.get('lpx')})
        for variant, item in variants.items():
            if item is None:
                continue
            source = item.get('path', item.get('lpx')) if isinstance(item, dict) else item
            pcm = item.get('pcm') if isinstance(item, dict) else row.get('pcm') if variant == 'baseline' else None
            if not re.fullmatch(r'[A-Za-z0-9_-]+', name) or not re.fullmatch(r'[A-Za-z0-9_-]+', variant):
                raise ValueError('Use simple stable case and variant names')
            cases.append((name, variant, str((REPO / source).resolve()), str((REPO / pcm).resolve()) if pcm else None))
    return cases


def freeze_inputs(cases, output):
    """Freeze bytes/PCM once, so concurrent encoder work cannot alter a run."""
    frozen, rows = [], []
    for name, variant, source_name, pcm_name in cases:
        source = Path(source_name)
        data = source.read_bytes()
        if data[:2] not in (b'L9', b'LG'):
            raise ValueError('Expected genuine L9 or LG bytes')
        directory = output / 'inputs' / name
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (variant + ('.lg1' if data[:2] == b'LG' else '.lpx'))
        target.write_bytes(data)
        pcm = None
        if pcm_name:
            pcm = directory / (variant + '.pcm')
            pcm.write_bytes(Path(pcm_name).read_bytes())
        rows.append(dict(case=name, variant=variant, original=source.relative_to(REPO).as_posix(),
                         frozen=target.relative_to(REPO).as_posix(), sha256=sha(target),
                         pcm_sha256=sha(pcm) if pcm else None))
        frozen.append((name, variant, str(target), str(pcm) if pcm else None))
    write_json(output / 'inputs.json', dict(files=rows))
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--targets', nargs='+', choices=('attiny88', 'atmega328p'), default=['attiny88', 'atmega328p'])
    parser.add_argument('--backends', nargs='+', choices=('asm', 'c'), default=['asm', 'c'])
    parser.add_argument('--variants', nargs='+')
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--nano-pwm', action='store_true')
    parser.add_argument('--jobs', type=int, choices=(1, 2, 3, 4), default=1)
    args = parser.parse_args()
    output = safe_build(args.output)
    if output.exists():
        raise ValueError('Use a fresh run output directory')
    output.mkdir(parents=True)
    observer = prepare_observer(output)
    cases = [case for case in cases_from_manifest(args.manifest)
             if (not args.variants or case[1] in args.variants) and (not args.cases or case[0] in args.cases)]
    if not cases:
        raise ValueError('No requested cases')
    cases = freeze_inputs(cases, output)
    stage = prepare_stage(output) if any(Path(case[2]).read_bytes()[:2] == b'LG' for case in cases) else None
    jobs = [(name, variant, source, pcm, target, backend, str(output / name / variant / target / backend), str(stage) if stage else None, args.nano_pwm, str(observer))
            for name, variant, source, pcm in cases for target in args.targets for backend in args.backends]
    report = dict(schema='lbg1-full-avr-playback-v1', manifest_sha256=sha(args.manifest),
                  method='Complete actual files, 16 MHz/8 kHz, production FIFO32/prefill24, gain128 and assembly ISR on both arithmetic backends. Same hardware/observer source; LG replaces only decoder and original private ROM API shortcuts. No physical board measurement.',
                  runner_sha256=sha(Path(__file__)), original_observer_sha256=sha(ACTIVE.parent / 'validation/attiny88/sim_player.c'),
                  valid_only_observer_sha256=sha(observer),
                  observer_adaptation='Add Tiny valid-only PWM output as already provided for native Mega; timing/register/timer logic unchanged.', rows=[])
    if args.jobs == 1:
        completed = map(run_one, jobs)
        for record in completed:
            report['rows'].append(record)
            write_json(output / 'results.json', report)
            print(json.dumps({key: record.get(key) for key in ('case', 'variant', 'target', 'backend', 'status')}), flush=True)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as executor:
            futures = [executor.submit(run_one, job) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                record = future.result()
                report['rows'].append(record)
                write_json(output / 'results.json', report)
                print(json.dumps({key: record.get(key) for key in ('case', 'variant', 'target', 'backend', 'status')}), flush=True)
    report['rows'].sort(key=lambda row: (row['case'], row['variant'], row['target'], row['backend']))
    report['summary'] = dict(requested=len(jobs), measured=sum(row['status'] == 'measured' for row in report['rows']),
                           admitted=sum(row.get('result', {}).get('accepted', False) for row in report['rows']),
                           failed=sum(row['status'] == 'failed' for row in report['rows']))
    write_json(output / 'results.json', report)
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
