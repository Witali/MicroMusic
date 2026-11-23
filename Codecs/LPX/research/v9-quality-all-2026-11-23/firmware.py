#!/usr/bin/env python3
"""Source-pinned AVR firmware validation in separate prepare/build/run stages.

Use a fresh ignored build/ folder for every stream revision and final core SHA.
Preparation never compiles or simulates. Builds never execute an audio decoder.
Keep all inputs, hashes, firmware, raw logs and receipts private under build/.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[4]
CODEC = Path('Codecs/LPX/01_ACTIVE_Q0_CODEC')
TINY_FLAGS = ('-fno-gcse', '-fno-code-hoisting', '-fno-move-loop-invariants',
              '-morder2', '-fno-tree-loop-im', '-fno-tree-ccp')
SOURCE_PATHS = [str(CODEC / suffix).replace('\\', '/') for suffix in (
    'src', 'profiles', 'examples/ATTINY88_V5_PLAYER',
    'tools/build_attiny88_player.py', 'tools/verify_attiny88_player.py')]
SOURCE_PATHS += ['Codecs/common/pwm_gain.h', 'Codecs/LPX/validation/attiny88/sim_player.c',
    'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include']
PUBLIC_FIELDS = ('label', 'stream', 'target', 'backend', 'accepted', 'pwm_exact',
    'portable_matches_host', 'samples', 'ticks', 'underruns', 'min_queue',
    'flash_bytes', 'static_ram_bytes', 'program_excluding_audio_bytes',
    'embedded_audio_bytes', 'fits_standard_bootloader', 'stack_bytes', 'stack_margin',
    'output_gap_min', 'output_gap_max', 'irq_mean', 'irq_max',
    'producer_active_cpu_mean', 'decode_active_cpu_mean', 'simulation_exit', 'failure')

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_json(path, value):
    pending = path.with_suffix(path.suffix + '.partial')
    pending.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    pending.replace(path)
def private(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / 'build') or path == ROOT / 'build':
        raise ValueError('Use a private ignored build/ subdirectory')
    return path
def linux(path):
    path = str(Path(path).resolve()).replace('\\', '/')
    return '/mnt/' + path[0].lower() + path[2:] if os.name == 'nt' else path
def command(args, distro, folder, name, timeout=600):
    prefix = ['wsl', '-d', distro, '--'] if os.name == 'nt' else []
    result = subprocess.run([*prefix, *args], capture_output=True, timeout=timeout)
    (folder / (name + '-private.log')).write_bytes(result.stdout + result.stderr)
    return result
def checked(args, distro, folder, name):
    result = command(args, distro, folder, name)
    if result.returncode: raise RuntimeError(name + ' failed; private log retained')
    return result.stdout
def bindings(folder):
    return {str(p.relative_to(folder)).replace('\\', '/'): digest(p)
            for p in sorted(folder.rglob('*')) if p.is_file()}
def check_bindings(folder, expected):
    for name, value in expected.items():
        if digest(folder / name) != value: raise ValueError('Frozen source/input binding changed')

def prepare(args):
    out = private(args.output)
    if out.exists(): raise ValueError('Preserve prior evidence; prepare requires a fresh folder')
    sha = subprocess.check_output(['git', 'rev-parse', '--verify', args.core_sha + '^{commit}'], cwd=ROOT).decode().strip()
    archive = subprocess.check_output(['git', 'archive', '--format=tar', sha, *SOURCE_PATHS], cwd=ROOT)
    source = out / 'source'; source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as package:
        for member in package.getmembers():
            target = (source / member.name).resolve()
            if not target.is_relative_to(source) or member.issym() or member.islnk():
                raise ValueError('Unsafe source archive member')
            if member.isdir(): target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.extractfile(member).read())
    inputs = out / 'inputs'; inputs.mkdir()
    cases, labels = [], set()
    requested = [(label, [('baseline', old), ('candidate', new)])
                 for label, old, new in (args.case or [])]
    requested += [(label, [('candidate', candidate)]) for label, candidate in (args.candidate or [])]
    if not requested: raise ValueError('Supply a paired case or a final candidate')
    for label, streams in requested:
        if not re.fullmatch(r'[a-z0-9_-]+', label) or label in labels:
            raise ValueError('Use unique anonymous case labels')
        labels.add(label)
        for stream, original in streams:
            original = private(original); data = original.read_bytes()
            if len(data) < 13 or data[:2] != b'L9' or data[2] & (32 | 64):
                raise ValueError('Primary firmware cases need ordinary unmarked V9 without gain/Long metadata')
            samples = int.from_bytes(data[5:7], 'little')
            if int.from_bytes(data[3:5], 'little') != 8000 or not 1 <= samples <= 64000:
                raise ValueError('This actual firmware admission is limited to 8 kHz ordinary streams')
            if len(data) != 13 + int.from_bytes(data[11:13], 'little'):
                raise ValueError('Incomplete V9 input')
            saved = inputs / f'{label}-{stream}.lpx'; saved.write_bytes(data)
            case = dict(label=label, stream=stream, source=str(saved.relative_to(out)),
                input_sha256=digest(saved), samples=samples, bytes=len(data))
            expected = original.with_suffix('.u8')
            if expected.exists():
                payload = expected.read_bytes()
                if len(payload) != samples: raise ValueError('Host PWM length differs from declared samples')
                oracle = saved.with_suffix('.host.u8'); oracle.write_bytes(payload)
                case.update(host_pwm=str(oracle.relative_to(out)), host_pwm_sha256=digest(oracle))
            cases.append(case)
    historical = []
    if args.prior_tiny_c:
        prior = private(args.prior_tiny_c)
        for record in json.loads(prior.read_text()):
            if record['target'] == 'attiny88' and record['backend'] == 'c':
                historical.append({k: record[k] for k in PUBLIC_FIELDS if k in record})
        historical = dict(historical_only=True, original_receipt_sha256=digest(prior),
            source_revision_note='Bound to the original receipt; not relabeled with this run core/stream',
            current_source_admission=False, cases=historical)
    plan = dict(schema='lpx-final-firmware-validation-v1', core_commit=sha, cases=cases,
        source_sha256=bindings(source), input_bindings=bindings(inputs),
        configurations=[dict(target=t, backend=b) for t, b in
            ([('attiny88', 'asm'), ('atmega328p', 'asm'), ('atmega328p', 'c')]
            + ([('attiny88', 'c')] if args.include_tiny_c else []))],
        prior_tiny_c=historical, distro=args.wsl, cpu_hz=16000000, sample_rate=8000,
        physical_board_measured=False,
        level_policy='No gain metadata; encoder input-level planning is external to this firmware validation')
    write_json(out / 'plan-private.json', plan)
    print(json.dumps(dict(prepared_cases=len(cases), configurations=len(plan['configurations']),
        compiled_images=0, simulations_run=0)))

def load(out):
    plan = json.loads((out / 'plan-private.json').read_text())
    check_bindings(out / 'source', plan['source_sha256'])
    check_bindings(out / 'inputs', plan['input_bindings'])
    return plan
def build(args):
    out = private(args.output); plan = load(out)
    if (out / 'built-private.json').exists(): raise ValueError('Do not overwrite compiled evidence')
    snapshot = out / 'source'; codec = snapshot / CODEC
    spec = importlib.util.spec_from_file_location('frozen_avr_builder', codec / 'tools/build_attiny88_player.py')
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    builder.ROOT, builder.REPO = codec, ROOT
    builder.DFP = snapshot / 'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'
    tree = ast.parse((codec / 'tools/verify_attiny88_player.py').read_text())
    reference = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(name, ast.Name) and name.id == 'REFERENCE' for name in node.targets))
    rows = []
    for case in plan['cases']:
        for config in plan['configurations']:
            target, assembly = config['target'], config['backend'] == 'asm'
            folder = out / f"{case['label']}-{case['stream']}-{target}-{config['backend']}"
            folder.mkdir(exist_ok=False)
            cost = builder.build(out / case['source'], folder, assembly=assembly, asm_isr=assembly,
                queue=32, repeat=1, wsl=plan['distro'] if os.name == 'nt' else None,
                lpc_segments=2, flash_limit=8192 if target == 'attiny88' else 30720,
                sparse80=False, mul16_unroll=2, universal=True, rom_output_gain=True,
                extra_flags=TINY_FLAGS if target == 'attiny88' else (), target=target,
                nano_pwm=target != 'attiny88', sample_rate=8000)
            (folder / 'reference.cpp').write_text(reference, encoding='ascii')
            checked(['g++', '-O2', '-std=c++11', '-DLPX3_LPC_SEGMENTS=2', '-DLPX4_ENABLE_ASM=0',
                '-DLPX4_COMPACT_VERSION=9', '-DLPX4_SAMPLE_RATE=8000', '-include', linux(codec / 'profiles/Lpx4Sram512.h'),
                '-I' + linux(codec / 'src'), linux(folder / 'reference.cpp'),
                linux(codec / 'src/Lpx4HybridCore.cpp'), '-o', linux(folder / 'reference')], plan['distro'], folder, 'reference-compile')
            checked(['gcc', '-O2', '-std=c11', '-I' + linux(folder), '-I/usr/include/simavr',
                linux(snapshot / 'Codecs/LPX/validation/attiny88/sim_player.c'),
                '-lsimavr', '-lelf', '-o', linux(folder / 'sim_player')], plan['distro'], folder, 'observer-compile')
            row = dict(case=case, config=config, folder=folder.name, cost=cost,
                reference_sha256=digest(folder / 'reference'), observer_sha256=digest(folder / 'sim_player'))
            rows.append(row); write_json(out / 'built-progress-private.json', rows)
            print(json.dumps({k: case[k] for k in ('label', 'stream')} | config |
                {k: cost[k] for k in ('flash_bytes', 'static_ram_bytes', 'fits_standard_bootloader')}), flush=True)
    write_json(out / 'built-private.json', rows)

def run(args):
    out = private(args.output); plan = load(out)
    if (out / 'verification-private.json').exists(): raise ValueError('Do not relabel prior simulation evidence')
    if checked(['pkg-config', '--modversion', 'simavr'], plan['distro'], out, 'simavr-version').decode().strip() != '1.6':
        raise ValueError('Calibrated interrupt adapter requires simavr 1.6')
    results = []
    for row in json.loads((out / 'built-private.json').read_text()):
        case, config, cost = row['case'], row['config'], row['cost']; folder = out / row['folder']
        if digest(folder / 'player.bin') != cost['image_sha256'] or digest(folder / 'reference') != row['reference_sha256'] \
            or digest(folder / 'sim_player') != row['observer_sha256']:
            raise ValueError('Compiled firmware/reference/observer binding changed')
        expected = checked([linux(folder / 'reference')], plan['distro'], folder, 'reference-runtime')
        if len(expected) != case['samples']: raise ValueError('Portable reference did not finish completely')
        matches = 'host_pwm' not in case or expected == (out / case['host_pwm']).read_bytes()
        if not matches: raise ValueError('Pinned core reference differs from frozen host PWM; stop affected admission')
        (folder / 'expected.pwm').write_bytes(expected)
        start = time.monotonic()
        observer = command([linux(folder / 'sim_player'), linux(folder / 'player.elf'),
            linux(folder / 'actual.pwm'), linux(folder / 'timing.json')], plan['distro'], folder, 'observer')
        result = {k: case[k] for k in ('label', 'stream')} | config
        result.update({k: cost[k] for k in ('flash_bytes', 'static_ram_bytes', 'embedded_audio_bytes',
            'program_excluding_audio_bytes', 'fits_standard_bootloader')})
        result.update(core_commit=plan['core_commit'], portable_matches_host=matches,
            simulation_exit=observer.returncode, simulation_seconds=time.monotonic() - start,
            physical_board_measured=False, input_gain_metadata=False)
        if observer.returncode or not (folder / 'timing.json').exists():
            result.update(accepted=False, pwm_exact=False, failure='observer-failure-private-log')
        else:
            timing = json.loads((folder / 'timing.json').read_text()); result.update(timing)
            exact = (folder / 'actual.pwm').read_bytes() == expected
            period, ram = cost['sample_period_cycles'], 512 if config['target'] == 'attiny88' else 2048
            result['pwm_exact'] = exact
            result['accepted'] = bool(exact and timing['samples'] == timing['ticks'] == timing['timer_events'] == case['samples']
                and not timing['underruns'] and not timing['error'] and timing['eof'] == timing['stopped'] == 1
                and timing['queue_empty'] and timing['timer_stopped'] and timing['stack_margin'] > 0
                and timing['irq_entry_cycles'] == 4 and timing['irq_reti_complete']
                and timing['output_gap_min'] >= period - 20 and timing['output_gap_max'] <= period + 20
                and cost['flash_bytes'] <= cost['flash_limit'] and cost['static_ram_bytes'] + timing['stack_bytes'] < ram)
        write_json(folder / 'verification-private.json', result); results.append(result)
        write_json(out / 'verification-progress-private.json', results)
        print(json.dumps({k: result[k] for k in PUBLIC_FIELDS if k in result}), flush=True)
    write_json(out / 'verification-private.json', dict(schema='lpx-final-firmware-validation-v1',
        core_commit=plan['core_commit'], current_cases=results, prior_tiny_c=plan['prior_tiny_c']))

def main():
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare'); prep.add_argument('--output', required=True); prep.add_argument('--core-sha', required=True)
    prep.add_argument('--case', nargs=3, action='append', metavar=('LABEL', 'BASELINE', 'CANDIDATE'))
    prep.add_argument('--candidate', nargs=2, action='append', metavar=('LABEL', 'CANDIDATE'))
    prep.add_argument('--wsl', default='Ubuntu'); prep.add_argument('--include-tiny-c', action='store_true')
    prep.add_argument('--prior-tiny-c')
    for name in ('build', 'run'): commands.add_parser(name).add_argument('--output', required=True)
    args = parser.parse_args()
    try: globals()[args.command](args)
    except Exception as error:
        out = private(args.output)
        if out.exists():
            write_json(out / 'failure-private.json', dict(stage=args.command,
                type=type(error).__name__, message=str(error)))
        raise
if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps(dict(failed=type(error).__name__, details='Stop affected stage; inspect private receipts locally')))
        raise SystemExit(1)
