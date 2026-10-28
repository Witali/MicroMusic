"""Parameterized projection of the retained integer-inverse seed probe.

The original probe_seed.py remains ignored and its post-run hash is recorded.
This projection removes local paths and adds source/I/O/native-output guards.
"""
import inspect
import json
from pathlib import Path

from common import parser, prepare, reference, emit, save


def main(args):
    ctx = prepare(args)
    from numba import njit
    from q0_model import coefficient_trace, table
    from wav_lpc import pack_frames
    np = ctx.np

    @njit(cache=False)
    def inverse_force(source, co, pre):
        result = np.empty(len(source), np.float64)
        history = np.zeros(10, np.int64)
        dd = 0
        for at in range(len(source)):
            desired = np.int64(np.rint(source[at] / 2.))
            prediction = desired - ((pre * dd) >> 14)
            accumulated = 0
            for k in range(10):
                accumulated += (co[at, k] * history[k]) >> 12
            result[at] = prediction + accumulated
            for k in range(9, 0, -1):
                history[k] = history[k - 1]
            history[0] = prediction
            dd = desired
        return result

    source = inspect.getsource(ctx.v4.search.py_func)
    start = source.index('    emphasized=')
    end = source.index('    for bi in range(n//160):')
    changed = source[:start] + '    residual=inverse_force(reference,co,pre)\n' + source[end:]
    changed = changed.replace('@njit(cache=True)', '@njit(cache=False)')
    scope = dict(np=np, njit=njit, inverse_force=inverse_force, search_block=ctx.v4.search_block)
    exec(changed.replace('def search(', 'def fixed_search('), scope)
    centered = changed.replace(
        'center=max(1,min(31,center));lag=18;pitchscore=-1.;pitchgain=0',
        'center=max(1,min(31,center));lag=18;pitchscore=-1.;pitchgain=0\n        mu=np.mean(residual[max(0,start-145):end])')
    centered = centered.replace('dot+=v*residual[j];energy+=v*v',
                                'dot+=(v-mu)*(residual[j]-mu);energy+=(v-mu)*(v-mu)')
    if centered == changed:
        raise ValueError('Frozen legacy search replacement anchor changed')
    exec(centered.replace('def search(', 'def fixed_centered_search('), scope)
    original = args.incumbent.read_bytes()
    n, profile, spectra, params, pulses, pre, bright, extras = ctx.compact.unpack(original)
    source_pcm = reference(ctx, args.reference)
    if profile != 4 or n != len(source_pcm) or n % 320 or bright:
        raise ValueError('Original probe domain is profile 4, full 320-sample packets, brightness 0')
    vectors = [[(value << 5) + 16 for value in row] for row in spectra for _ in range(2)]
    coefficients = coefficient_trace(pack_frames(vectors[:(n + 159) // 160]), n)
    pitch = ctx.track_pitch(source_pcm)
    criterion = ctx.VoiceObjective(source_pcm, pitch.period)
    report = dict(status='running', family='frozen incumbent spectra; extra pulses omitted', rows=[])
    with ctx.BatchSession('batch', speech=True, speech_compact=True) as common, ctx.BatchSession(
            'batch', speech=True, speech_compact=True, compact_only=True) as only:
        for label, search in [('legacy', ctx.v4.search), ('integer-force', scope['fixed_search']),
                              ('integer-force-centered', scope['fixed_centered_search'])]:
            fitted_params, fitted_pulses, pcm = search(source_pcm.astype(np.int64), coefficients,
                                                       table('scale_table.inc'), pre, profile)
            blob, _ = ctx.compact.pack(n, profile, spectra, fitted_params, fitted_pulses, pre, bright)
            row = emit(ctx, label, blob, pcm, source_pcm, criterion, (common, only))
            row.update(old_bytes=len(original), fits_old_bytes=len(blob) <= len(original))
            report['rows'].append(row)
            save(ctx.output / 'results-private.json', report)
            print(json.dumps(dict(variant=label, bytes=len(blob))), flush=True)
    report['status'] = 'complete'
    save(ctx.output / 'results-private.json', report)


if __name__ == '__main__':
    cli = parser(__doc__)
    cli.add_argument('--reference', type=Path, required=True)
    cli.add_argument('--incumbent', type=Path, required=True)
    main(cli.parse_args())
