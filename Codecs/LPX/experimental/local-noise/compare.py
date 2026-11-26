"""Paired native-only local-noise experiment; no production format or WASM edits.

Default: build and run only two pilot cases. Use --phase matrix after pilot review.
The fixed held-out signals are defined here before any corpus measurements.
All media/binaries remain under ignored build/local-noise; retained JSON has hashes.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ACTIVE = REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
BUILD = REPO / 'build/local-noise'
SOURCE = BUILD / 'sources'
CLIPS = ('chego', 'otvechaesh', 'vinni', 'bread')
PWM_REFERENCE = REPO / 'Codecs/LPX/research/lbg1-2026-11-26/results.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(REPO).as_posix()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def git(*args):
    try:
        return subprocess.check_output(['git', *args], cwd=REPO, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        if str(REPO).startswith('/mnt/'):
            windows = str(REPO)[5].upper() + ':/' + str(REPO)[7:]
            return subprocess.check_output(['git.exe', '-C', windows, *args], stderr=subprocess.DEVNULL)
        raise


def git_revision():
    return git('rev-parse', 'HEAD').decode().strip()


def verify_baseline(inputs):
    revision = git('rev-parse', '644e19d0').decode().strip()
    verified = {}
    for path in inputs:
        name = relative(path)
        if not (name.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/host/') or
                name.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/') or
                name == 'web-player/scripts/lib/lpx-build.mjs'):
            continue
        original = git('show', revision + ':' + name)
        current = path.read_bytes().replace(b'\r\n', b'\n')
        if current != original.replace(b'\r\n', b'\n'):
            raise RuntimeError('Production baseline differs from pinned 644e19d0: ' + name)
        verified[name] = hashlib.sha256(current).hexdigest()
    return revision, verified


def build():
    config = REPO / 'web-player/scripts/lib/lpx-build.mjs'
    text = config.read_text(encoding='utf-8')
    names = re.findall(r"'([^']+\.cpp)'", text.split('export const hostSources=host([')[1].split(']);')[0])
    defines = re.findall(r"'([^']+)'", text.split('export const portableDefines=[')[1].split('];')[0])
    sources = [ACTIVE / 'src/Lpx4HybridCore.cpp', ACTIVE / 'host/LpxEncoder.cpp',
               *(ACTIVE / 'host' / name for name in names), HERE / 'LocalNoise.cpp', HERE / 'benchmark.cpp']
    inputs = sorted(set(sources + list((ACTIVE / 'host').glob('*.h')) + list((ACTIVE / 'host').glob('*.inc'))
                        + list((ACTIVE / 'src').glob('*.h')) + list((ACTIVE / 'src').glob('*.inc'))
                        + [config, HERE / 'LocalNoise.h', Path(__file__).resolve()]))
    baseline_revision, baseline_sources = verify_baseline(inputs)
    hashes = {relative(path): sha(path) for path in inputs}
    binary = BUILD / 'benchmark'
    command = ['g++', '-O3', '-std=c++11', '-ffp-contract=off', '-DNDEBUG',
               *('-D' + define for define in defines), '-include', relative(ACTIVE / 'host/LpxHostWorkspace.h'),
               '-I' + relative(ACTIVE / 'src'), '-I' + relative(ACTIVE / 'host'), '-I' + relative(HERE),
               *(relative(path) for path in sources), '-o', relative(binary)]
    BUILD.mkdir(parents=True, exist_ok=True)
    receipt = BUILD / 'build.json'
    if receipt.exists():
        old = json.loads(receipt.read_text())
        if old.get('sources') == hashes and binary.exists() and old.get('binary_sha256') == sha(binary):
            return old
    subprocess.run(command, cwd=REPO, check=True)
    if hashes != {relative(path): sha(path) for path in inputs}:
        raise RuntimeError('An experiment input changed during compilation')
    result = dict(compiler=subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
                  command=command, sources=hashes, binary_sha256=sha(binary), baseline_revision=baseline_revision,
                  baseline_sources_normalized_sha256=baseline_sources, experiment_head=git_revision())
    write_json(receipt, result)
    return result


def heldout_sources():
    """Fixed deterministic voiced/noisy/transient high-band controls, not listening evidence."""
    rows = []
    for rate in (12000, 16000):
        n = rate  # one second; retains enough supported 80 ms windows for diagnostics
        state = 0x4C50584E
        samples = []
        for i in range(n):
            t = i / rate
            state = (1664525 * state + 1013904223) & 0xffffffff
            noise = ((state >> 8) / 16777216.0 - .5) * 2
            f0 = 137.0 if t < .5 else 193.0
            voiced = sum(math.sin(2 * math.pi * f0 * k * t) / k for k in range(1, 11))
            envelope = min(1.0, t / .04, (1.0 - t) / .05)
            high = 280 * math.sin(2 * math.pi * (rate * .32) * t)
            value = envelope * (2200 * voiced + high + (80 if t < .7 else 1000) * noise)
            if .48 < t < .485:
                value += 5500 * math.sin(2 * math.pi * 1700 * t)
            samples.append(max(-30000, min(30000, round(value))))
        data = struct.pack('<' + 'h' * len(samples), *samples)
        path = BUILD / 'heldout' / f'synthetic-{rate}.source.pcm'
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != data:
            raise RuntimeError('Held-out synthesis definition changed')
        path.write_bytes(data)
        rows.append(dict(clip=f'synthetic-{rate}', rate=rate, path=path, level=6))
    return rows


def mean(values):
    finite = [x for x in values if x is not None and math.isfinite(x)]
    return sum(finite) / len(finite) if finite else None


def summary(rows):
    result = {}
    for target in ('pcm', 'pwm'):
        cases = [r for r in rows if r['quality_target'] == target]
        if not cases:
            continue
        outputs = {}
        for variant in cases[0]['outputs']:
            records = [row['outputs'][variant] for row in cases]
            outputs[variant] = dict(bytes=sum(x['bytes'] for x in records),
                changed_cases=sum(row['artifacts'][variant]['lpx_sha256'] != row['artifacts']['baseline']['lpx_sha256'] for row in cases),
                changed_positions=sum(x['changed_positions'] for x in records),
                changed_amplitudes=sum(x['changed_amplitudes'] for x in records),
                pcm_sse=sum(x['pcm_sse'] for x in records), pwm_sse=sum(x['pwm_sse'] for x in records),
                mean_stoi=[mean([x['stoi'][p] for x in records]) for p in (0,1)],
                mean_selected_target_local_score=mean([x['local_noise_selected_target']['score'] for x in records]))
        result[target] = dict(cases=len(cases), baseline_seconds=sum(x['baseline_seconds'] for x in cases),
                              refinement_seconds=sum(x['refinement_seconds'] for x in cases), outputs=outputs)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('pilot', 'matrix', 'heldout'), default='pilot')
    parser.add_argument('--run', default='frozen-v1', help='Immutable artifact directory label')
    parser.add_argument('--case', action='append', dest='cases')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--output', type=Path, help='Retained JSON under experimental/local-noise')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', args.run):
        parser.error('--run must be a short path-free label')
    known = {f'{clip}-p{level}-{target}' for clip in CLIPS for level in (4, 6) for target in ('pcm', 'pwm')}
    if args.cases and (args.phase == 'heldout' or set(args.cases) - known):
        parser.error('Unknown or incompatible --case selection')
    if args.phase == 'pilot' and args.cases and set(args.cases) - {'chego-p4-pcm', 'chego-p4-pwm'}:
        parser.error('Pilot is restricted to chego-p4-pcm and chego-p4-pwm')
    build_receipt = build()
    if args.build_only:
        print('Built build/local-noise/benchmark', flush=True)
        return
    pinned_pwm = {row['name']: row['baseline'] for row in json.loads(PWM_REFERENCE.read_text(encoding='utf-8'))['cases']}
    source_manifest = SOURCE / 'sources.json'
    if args.phase != 'heldout' and not source_manifest.exists():
        raise RuntimeError('Prepared public source manifest is required')
    source_receipt = json.loads(source_manifest.read_text(encoding='utf-8')) if source_manifest.exists() else None
    specifications = heldout_sources() if args.phase == 'heldout' else [dict(clip=clip,rate=8000,path=SOURCE / f'{clip}.source.pcm',level=level) for clip in CLIPS for level in (4,6)]
    rows = []
    output = args.output or HERE / f'results-{args.phase}.json'
    if not output.is_absolute():
        output = REPO / output
    if output.parent.resolve() != HERE or output.suffix != '.json':
        parser.error('--output must be JSON directly under experimental/local-noise')
    before = build_receipt['sources']
    verified_sources = {row['clip']: row for row in (source_receipt or {}).get('sources', [])}
    if args.phase != 'heldout':
        for clip in CLIPS:
            entry = verified_sources.get(clip)
            path = SOURCE / f'{clip}.source.pcm'
            if not entry or entry.get('rate') != 8000 or entry.get('pcm_sha256') != sha(path) or path.stat().st_size != entry.get('samples', -1) * 2:
                raise RuntimeError('Prepared source does not match its verified manifest')
    for spec in specifications:
        for target in ('pcm', 'pwm'):
            name = f"{spec['clip']}-p{spec['level']}-{target}"
            if args.cases and name not in args.cases:
                continue
            if args.phase == 'pilot' and name not in ('chego-p4-pcm', 'chego-p4-pwm'):
                continue
            prefix = BUILD / 'runs' / args.run / args.phase / name
            prefix.parent.mkdir(parents=True, exist_ok=True)
            source_sha = sha(spec['path'])
            command = [str(BUILD / 'benchmark'), str(spec['path']), str(prefix), str(spec['level']), str(spec['rate']), target, '4']
            started = time.monotonic()
            done = subprocess.run(command, cwd=REPO, check=True, capture_output=True, text=True)
            measured = json.loads(done.stdout)
            if before != {p: sha(REPO / p) for p in before} or source_sha != sha(spec['path']):
                raise RuntimeError('Sources changed during a measured run')
            measured.update(name=name, source=relative(spec['path']), source_sha256=source_sha,
                            command=[relative(Path(x)) if str(x).startswith(str(REPO)) else x for x in command],
                            harness_wall_seconds=time.monotonic()-started)
            artifacts = {}
            for variant in measured['outputs']:
                artifacts[variant] = {}
                for extension in ('lpx', 'pcm', 'model'):
                    artifact = Path(str(prefix) + f'.{variant}.{extension}')
                    artifacts[variant][extension] = relative(artifact)
                    artifacts[variant][extension + '_sha256'] = sha(artifact)
            measured['artifacts'] = artifacts
            if target == 'pwm' and args.phase != 'heldout':
                retained = pinned_pwm[f"{spec['clip']}-p{spec['level']}"]
                if artifacts['baseline']['lpx_sha256'] != retained['sha256'] or artifacts['baseline']['pcm_sha256'] != retained['pcm_sha256'] or measured['outputs']['baseline']['bytes'] != retained['bytes']:
                    raise RuntimeError('Fresh current PWM baseline differs from retained public baseline')
                measured['baseline_matches_retained_pwm'] = True
            rows.append(measured)
            result = dict(schema='lpx-local-noise-paired-v1', phase=args.phase, run=args.run, experiment_head=git_revision(), build=build_receipt,
                retained_pwm_reference=relative(PWM_REFERENCE), retained_pwm_reference_sha256=sha(PWM_REFERENCE),
                source_manifest=source_receipt, source_manifest_sha256=sha(source_manifest) if source_manifest.exists() else None,
                method='Each case encodes its own fresh calls4 baseline for the selected quality target. Raw proposals are not admitted gains. The independently admitted active-SSE selection control uses the same shared trial pool and frozen baseline; this is a paired ranking ablation, not a wholly noise-free encoder. Both output paths are reported post hoc; PWM diagnostics are inactive for PCM admission. Refinement time includes the shared search and both independent admissions. No decoder, format, coefficient, pitch, scale or extra pulse change.',
                complete=False, cases=rows, summary=summary(rows))
            write_json(output, result)
            print(f"{name}: {measured['outputs']['baseline']['bytes']} bytes; accepted={measured['search']['accepted']}; {measured['refinement_seconds']:.3f}s refinement", flush=True)
    if not rows:
        raise RuntimeError('Case selection produced no measured cases')
    result['complete'] = True
    write_json(output, result)
    print(relative(output), flush=True)


if __name__ == '__main__':
    main()
