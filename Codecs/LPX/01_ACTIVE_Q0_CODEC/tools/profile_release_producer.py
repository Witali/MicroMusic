"""Measure real production producer work and full PWM/IRQ/Flash costs.

The external sim_producer observer changes no AVR instructions. Its useful
body intervals include queue publication and RET4, exclude caller CALL and
subtract complete live interrupt-notification intervals. It excludes calls
without actual head publication and refuses missing/ambiguous boundaries.
This is a CPU-work measure; nominal 8kHz playback duration is not its proxy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import build_release_player as player
import speech_compact
import speech_sparse80
from standard_metrics import pwm_duties


def run(stream, output, avr_bin, runner, *, lib=None, wsl=None, meta320=False,
        sparse80=False, scale_ramp=False, source=None, queue=256, prefill=None, irq=0, assembly=True):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Use a fresh ignored profiling output directory')
    blob = Path(stream).read_bytes()
    if scale_ramp:
        from speech_scale_ramp import decode_model
        modeled = decode_model(blob)
    elif meta320:
        from speech_meta320 import expand
        reference = expand(blob)
    elif sparse80:
        reference = speech_sparse80.expand(blob)
    else:
        reference = blob
    if not scale_ramp:modeled = speech_compact.decode_model(reference)
    expected = pwm_duties(modeled).tobytes()
    verification = player.simulate([blob], output, avr_bin, runner,
        source=source, queue=queue, prefill=prefill, irq=irq, assembly=assembly,
        sparse80=sparse80, meta320=meta320, scale_ramp=scale_ramp, lib=lib, wsl=wsl, expected_pwm=expected)
    work_file = output/'observer.json.producer.json'
    work = json.loads(work_file.read_text(encoding='utf-8'))
    if (not work['passed'] or work['published_calls'] != len(expected)
            or work['preload_calls']+work['playback_calls'] != len(expected)
            or work['boundary_errors'] or work['failed_calls']
            or work['calls'] != work['published_calls']+work['unpublished_calls']+work['failed_calls']):
        raise ValueError('Producer boundaries or useful sample-call counts failed verification')
    trace = np.loadtxt(output/'observer.json.producer-cycles.csv', delimiter=',', dtype=np.int64, ndmin=2)
    if (trace.shape != (len(expected), 4) or not np.array_equal(trace[:, 0], np.arange(1,len(expected)+1))
            or np.any(trace[:, 1] < trace[:, 2]) or np.any(trace[:, 2] < 0)
            or np.count_nonzero(trace[:, 3]) != work['playback_calls']):
        raise ValueError('Per-call producer timing trace is inconsistent')
    durations = trace[:, 1]-trace[:, 2]
    # Independent array sums/convolutions verify the host observer's streaming
    # ring statistics rather than trusting its rolling-window implementation.
    if int(durations.sum()) != work['producer_work_cycles_total'] or int(durations.max()) != work['producer_work_cycles_max']:
        raise ValueError('Producer totals differ from individual measured calls')
    for width in (160, 320):
        maximum = int(np.convolve(durations,np.ones(width,np.int64),'valid').max()) if len(durations)>=width else 0
        if maximum != work['producer_work_cycles_max'+str(width)]:
            raise ValueError('Producer window maximum differs from the independent trace audit')
    work['mean_producer_work_cycles'] = work['producer_work_cycles_total']/work['published_calls']
    work['preload_work_cycles'] = int(durations[trace[:,3]==0].sum())
    work['playback_work_cycles'] = int(durations[trace[:,3]!=0].sum())
    work['amortized_setup_and_producer_work_cycles'] = (work['producer_work_cycles_total']+work['cycles_before_first_producer_entry'])/work['published_calls']
    work['worst160_cycles_per_sample'] = work['producer_work_cycles_max160']/160
    work['worst320_cycles_per_sample'] = work['producer_work_cycles_max320']/320
    result = dict(schema='lpx-production-work-admission-v1', passed=True, work=work,
        firmware=verification, profiler_sources={name:player.digest(player.VALIDATION/name)
            for name in ('sim_producer.c','sim_player.c')}, profiler_python_sha256=player.digest(Path(__file__)),
            per_call_trace_sha256=player.digest(output/'observer.json.producer-cycles.csv'),
            perCallTraceVerified=True, physicalBoardTested=False)
    player.save(output/'producer-verification-private.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stream', type=Path)
    parser.add_argument('output', type=Path)
    for name in ['avr-bin','runner','lib']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--wsl')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--meta320', action='store_true')
    parser.add_argument('--sparse80', action='store_true')
    parser.add_argument('--scale-ramp', action='store_true')
    parser.add_argument('--c-backend', action='store_true')
    parser.add_argument('--irq', type=int, default=0)
    args = parser.parse_args()
    result = run(args.stream,args.output,args.avr_bin,args.runner,lib=args.lib,wsl=args.wsl,
        source=args.source,meta320=args.meta320,sparse80=args.sparse80,scale_ramp=args.scale_ramp,
        assembly=not args.c_backend,irq=args.irq)
    print(json.dumps({key:result['work'][key] for key in
        ['published_calls','mean_producer_work_cycles','worst160_cycles_per_sample','worst320_cycles_per_sample']}))


if __name__ == '__main__':
    main()
