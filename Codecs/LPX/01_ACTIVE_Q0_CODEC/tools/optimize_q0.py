#!/usr/bin/env python3
"""Alternating LSF/excitation/header search for existing Q0 speech streams.

The Q0 waveform arithmetic and L4HY v2 format stay unchanged. Two to four rounds
revisit coupled parameters; all accepted phases satisfy the ORIGINAL global
SER/STOI floor and exact byte cap. A native instrumented decoder verifies
read-bit proxies before writing output. Those counters are not CPU cycles.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import wave
import numpy as np
from batch_decoder import BatchSession
from beam_excitation_pcm16 import optimize as beam_opt
from refine_lsf_pcm16 import optimize as lsf_opt
from tune_pcm16 import read_wav16, tune
from wav_to_lpx4 import quality
from output_paths import protect_outputs

ROOT = Path(__file__).resolve().parents[1]


def cost_probe():
    """Compile a host-only instrumented executable from the portable C backend."""
    sources = [ROOT / 'src/Lpx4HybridCore.cpp', ROOT / 'src/Lpx4HybridCore.h', ROOT / 'src/Lpx4Math.h',
               ROOT / 'src/cos_table.inc', ROOT / 'src/scale_table.inc', ROOT / 'tests/decode_metrics.cpp']
    compiler = shutil.which('g++')
    if compiler is None:
        raise FileNotFoundError('g++ required for native decode-cost checks')
    key = hashlib.sha256((compiler + os.name).encode() + b''.join(p.read_bytes() for p in sources)).hexdigest()[:24]
    cache = Path(tempfile.gettempdir()) / 'micromusic_lpx4_host_cache'
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / ('cost-' + key + ('.exe' if os.name == 'nt' else ''))
    if not path.exists():
        subprocess.run([compiler, '-O3', '-std=c++11', '-DLPX3_COST_INSTRUMENT=1',
                        '-I' + str(ROOT / 'src'), str(sources[0]), str(sources[-1]), '-o', str(path)],
                       check=True, capture_output=True)
    return path


def probe(blob, executable):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'stream.l4hy';path.write_bytes(blob)
        result = subprocess.run([str(executable), str(path)], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def optimize(blob, ref, decoder, rounds=2, lsf_trials=500, beam_trials=2500,
             header_trials=80, beam_width=4, window=20, probe_executable=None,
             global_candidates=0, global_states=1024, kind='speech', timing_gate=None):
    if not 1 <= rounds <= 4 or min(lsf_trials, beam_trials, header_trials,global_candidates) < 0 or global_states<2:
        raise ValueError('Expected 1..4 rounds and nonnegative trial counts')
    if not 20 <= len(blob) <= 65535 or len(ref) > 64000:
        raise ValueError('Optimize independently decoded segments of <=64000 samples')
    if kind not in ('speech','music'):raise ValueError('Invalid content kind')
    if len(ref) < 4000 and (kind=='speech' or lsf_trials or header_trials):
        raise ValueError('Joint speech optimization requires at least 0.5 s for its STOI gate')
    first = decoder.decode_one_s16(blob, len(ref))
    if first is None:
        raise ValueError('Native decoder rejected baseline')
    initial = quality(ref, first,kind)
    executable = Path(probe_executable) if probe_executable else cost_probe()
    old_cost=probe(blob,executable)
    cost_fields=('bit_calls','rom_reads','lsf_converts','max_bit_calls_sample','max_bit_calls_80','max_bit_calls_160')
    cur, pcm = blob, first
    target = ref.astype(np.float64)
    def error(p):
        d = target - p
        return float(np.dot(d, d))
    best = error(pcm)
    stages = []
    for iteration in range(rounds):
        begin = cur
        for name, budget in (('LSF', lsf_trials), ('beam', beam_trials), ('header', header_trials),('global',global_candidates)):
            if not budget:
                continue
            if name == 'LSF':
                candidate, pp, r = lsf_opt(cur, ref, decoder, max_trials=budget,
                    step_sizes=(16, 8, 4, 2, 1), min_stoi_delta=0., passes=1)
                count = r['meta']['trials']
            elif name == 'beam':
                candidate, pp, r = beam_opt(cur, ref, decoder, beam_width=beam_width,
                    window=window, tail=80, max_trials=budget, stoi_drop=0.,kind=kind)
                count = r['trials']
            elif name=='global':
                from global_rate_pcm16 import optimize as global_opt
                candidate,pp,r=global_opt(cur,ref,decoder,rounds=1,max_states=global_states,
                    max_candidates=budget,kind=kind,probe_executable=executable,timing_gate=timing_gate)
                count=len(r['trials'])
            else:
                candidate, pp, r = tune(cur, ref, decoder, trial_limit=budget, stoi_tolerance=0.)
                count = r['trials']
            met = quality(ref, pp,kind)
            accepted = (len(candidate) <= len(blob) and (error(pp),len(candidate)) < (best,len(cur)) and
                        (initial['stoi'] is None or met['stoi'] >= initial['stoi'] - 1e-12))
            candidate_cost=None;timing=None
            if accepted:
                candidate_cost=probe(candidate,executable)
                if timing_gate:
                    timing=timing_gate(candidate);accepted=timing['accepted']
                else:accepted=all(candidate_cost[k]<=old_cost[k] for k in cost_fields)
            if accepted:
                cur, pcm, best = candidate, pp, error(pp)
            stages.append({'round': iteration + 1, 'stage': name, 'trials': count,
                           'accepted': accepted,'candidate_cost':candidate_cost,'timing':timing, 'quality': quality(ref, pcm,kind)})
        if cur == begin:
            break
    new_cost = probe(cur, executable)
    # Cached polynomial work may depend on LSF values even with fixed syntax.
    if not timing_gate and any(new_cost[k]>old_cost[k] for k in cost_fields):
        raise AssertionError('Native read-bit/ROM/LSF proxy changed; output rejected')
    check = decoder.decode_one_s16(cur, len(ref))
    if check is None or not np.array_equal(pcm, check):
        raise AssertionError('Independent native decode mismatch')
    return cur, pcm, {'before': initial, 'after': quality(ref, pcm,kind), 'stages': stages,
                     'input_bytes': len(blob), 'output_bytes': len(cur),
                     'input_sha256': hashlib.sha256(blob).hexdigest(),
                     'output_sha256': hashlib.sha256(cur).hexdigest(),
                     'decoder_cost_before': old_cost, 'decoder_cost_after': new_cost,
                     'decoder_source_sha256': hashlib.sha256((ROOT / 'src/Lpx4HybridCore.cpp').read_bytes()).hexdigest(),
                     'avr_cycles_measured':bool(getattr(timing_gate,'avr_cycles_measured',False)),
                     'timing':timing_gate(cur) if timing_gate else None}


def run(source, reference_wav, output, avr_config=None,**kwargs):
    source, reference_wav, output = Path(source), Path(reference_wav), Path(output)
    protect_outputs([source, reference_wav],
        [output, output.with_suffix('.wav'), output.with_suffix('.json')], replace=(source, output))
    ref = read_wav16(reference_wav)
    t0 = time.perf_counter()
    if avr_config:
        from avr_timing_gate import AvrTimingGate
        kwargs['timing_gate']=AvrTimingGate(source.read_bytes(),**avr_config)
    with BatchSession('batch') as decoder:
        blob, pcm, report = optimize(source.read_bytes(), ref, decoder, **kwargs)
    report['elapsed_seconds'] = time.perf_counter() - t0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(blob)
    with wave.open(str(output.with_suffix('.wav')), 'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(pcm.astype('<i2').tobytes())
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path);ap.add_argument('reference_wav', type=Path);ap.add_argument('output', type=Path)
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--global-candidates',type=int,default=32)
    ap.add_argument('--global-states',type=int,default=1024)
    ap.add_argument('--kind',choices=('speech','music'),default='speech')
    ap.add_argument('--avr-bin',type=Path);ap.add_argument('--sim-runner',type=Path)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl');ap.add_argument('--timing-work',type=Path)
    ap.add_argument('--lsf-trials', type=int, default=500)
    ap.add_argument('--beam-trials', type=int, default=2500)
    ap.add_argument('--header-trials', type=int, default=80)
    ap.add_argument('--beam', type=int, choices=(1, 4, 8, 16), default=4)
    ap.add_argument('--window', type=int, choices=(20, 40), default=20)
    a = ap.parse_args()
    if a.avr_bin and (not a.sim_runner or not a.timing_work):
        ap.error('--avr-bin requires --sim-runner and --timing-work in an ignored build directory')
    avr_config=None if not a.avr_bin else dict(output=a.timing_work,avr_bin=a.avr_bin,
        runner=a.sim_runner,lib=a.sim_lib_dir,wsl=a.wsl)
    print(json.dumps(run(a.input, a.reference_wav, a.output, rounds=a.rounds,
        lsf_trials=a.lsf_trials, beam_trials=a.beam_trials, header_trials=a.header_trials,
        beam_width=a.beam, window=a.window,global_candidates=a.global_candidates,
        global_states=a.global_states,kind=a.kind,avr_config=avr_config), indent=2))


if __name__ == '__main__':
    main()
