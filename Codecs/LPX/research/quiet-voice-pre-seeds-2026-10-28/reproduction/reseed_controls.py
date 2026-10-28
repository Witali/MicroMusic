"""Explicit invocation reconstruction of the saved pitch-reseed controls.

Earlier incumbent-runner versions were overwritten before archival. The
published 41f57496 component reconstructs the recorded settings; this file is
not represented as the lost exact executed source or as a rerun of those fits.
"""
import inspect
import json
from pathlib import Path

from common import parser, prepare, reference, emit, save


def main(args):
    ctx = prepare(args, reseed=True)
    import reseed_speech_excitation as component
    source = reference(ctx, args.reference)
    blob = args.incumbent.read_bytes()
    if ctx.compact.unpack(blob)[0] != len(source):
        raise ValueError('Source/stream count mismatch')
    pitch = ctx.track_pitch(source)
    if not len(pitch.sample_center):
        raise ValueError('Original controls require complete 80-ms source windows')
    lags = ctx.np.zeros((len(source) + 159) // 160, ctx.np.int64)
    for block in range(len(lags)):
        index = int(ctx.np.argmin(abs(pitch.sample_center - (block * 160 + 80))))
        if pitch.voiced[index]:
            lag = int(ctx.np.rint(pitch.period[index]))
            if 18 <= lag <= 145:
                lags[block] = lag
    criterion = ctx.VoiceObjective(source, pitch.period)
    if args.case == 'original':
        configurations = [('gain-original', None, 160, 0.), ('gain14', 14, 160, 0.),
                          ('gain14-periodic8-h320', 14, 320, 8.)]
    else:
        if int.from_bytes(blob[12:14], 'little') != 0:
            raise ValueError('Pre0 controls need the already generated consistent pre-0 seed')
        configurations = [('gain-original-periodic8-h320', None, 320, 8.),
                          ('gain14-periodic8-h320', 14, 320, 8.)]
    if args.case == 'pre0-pitched':
        # This retained negative prototype changes only the local experiment's
        # component binding. Exact source hashes guard the textual anchor.
        function = inspect.getsource(component._fit.py_func).replace('@njit(cache=True)', '@njit(cache=False)')
        old = '        stop = min(len(reference), at + horizon)'
        new = '''        if not source_lags[at // 160]:
            _, history, dd, cc, ring = advance(
                co, parameters, innovations, extras, steps, pre, bright,
                at, min(len(reference), at + 20), history, dd, cc, ring)
            continue
        stop = min(len(reference), at + horizon)'''
        if function.count(old) != 1:
            raise ValueError('Frozen experimental source anchor changed')
        namespace = dict(component.__dict__)
        exec(function.replace(old, new), namespace)
        component._fit = namespace['_fit']
        configurations = configurations[:1]
    report = dict(status='running', invocation_reconstruction=True,
                  mapping='nearest source 80-ms center to each 160-sample block; 0 for unknown/out-of-range',
                  source_gain=1, supplied_pitch_blocks=int(ctx.np.count_nonzero(lags)), rows=[])
    with ctx.BatchSession('batch', speech=True, speech_compact=True) as common, ctx.BatchSession(
            'batch', speech=True, speech_compact=True, compact_only=True) as only:
        for label, gain, horizon, weight in configurations:
            candidate, pcm, details = component.reseed(source, blob, common, source_lags=lags,
                gain=gain, horizon=horizon, periodicity_weight=weight)
            row = emit(ctx, label, candidate, pcm, source, criterion, (common, only))
            row.update(settings=details, old_bytes=len(blob), fits_old_bytes=len(candidate) <= len(blob))
            report['rows'].append(row)
            save(ctx.output / 'results-private.json', report)
            print(json.dumps(dict(variant=label, bytes=len(candidate))), flush=True)
    report['status'] = 'complete'
    save(ctx.output / 'results-private.json', report)


if __name__ == '__main__':
    cli = parser(__doc__, reseed=True)
    cli.add_argument('--case', choices=('original', 'pre0', 'pre0-pitched'), required=True)
    cli.add_argument('--reference', type=Path, required=True)
    cli.add_argument('--incumbent', type=Path, required=True)
    main(cli.parse_args())
