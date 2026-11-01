"""Parameterized projection of the completed original-level pre-grid runs.

No allow_zero_scale option is used: exact 9ad encoder sources are required.
This projection is syntax/help-checked only; exporting it did not refit audio.
"""
import json

from common import parser, prepare, reference, measure, emit, save


def main(args):
    if args.mode == 'target' and (args.reference is None or args.incumbent is None):
        raise ValueError('Target mode needs --reference and --incumbent')
    if args.mode == 'tuning' and args.manifest is None:
        raise ValueError('Tuning mode needs the frozen 98-group private manifest')
    ctx = prepare(args)
    if args.mode == 'target':
        source = reference(ctx, args.reference)
        cases = [(0, source, {4: args.incumbent.read_bytes(), 6: args.incumbent.read_bytes()})]
    else:
        document = json.loads(args.manifest.read_text())
        if len(document['records']) != 98:
            raise ValueError('Expected the frozen 98-profile-group manifest')
        candidates = []
        for index, record in enumerate(document['records']):
            if record['split'] == 'tuning' and record['profile'] == 4:
                source = reference(ctx, record['reference']['path'])
                rms = float(ctx.np.sqrt(ctx.np.mean(source.astype(float) ** 2)))
                candidates.append((rms, index, record, source))
        if len(candidates) != 20:
            raise ValueError('Expected 20 original tuning references')
        candidates.sort(key=lambda row: (row[0], row[1]))
        chosen = [row for row in candidates if row[0] < 256] + [candidates[len(candidates) // 2]]
        if len(chosen) != 3:
            raise ValueError('Frozen level-only selection must have two quiet sources and one median control')
        cases = []
        for number, (_, _, record, source) in enumerate(chosen):
            baselines = {}
            for profile in (4, 6):
                matching = [item for item in document['records'] if item['profile'] == profile
                            and item['reference']['pcm16_sha256'] == record['reference']['pcm16_sha256']]
                if len(matching) != 1 or len(matching[0]['segments']) != 1:
                    raise ValueError('Expected the original one-reset source/profile controls')
                from pathlib import Path
                baselines[profile] = Path(matching[0]['segments'][0]['path']).read_bytes()
            cases.append((number, source, baselines))
    report = dict(status='running', zero_scale_option=False, source_gain=1,
                  pre_grid=[13926, 8192, 0], rows=[], baselines=[])
    with ctx.BatchSession('batch', speech=True, speech_compact=True) as common, ctx.BatchSession(
            'batch', speech=True, speech_compact=True, compact_only=True) as only:
        for number, source, baseline_blobs in cases:
            track = ctx.track_pitch(source)
            criterion = ctx.VoiceObjective(source, track.period)
            for profile in (4, 6):
                baseline = baseline_blobs[profile]
                before = measure(ctx, source, ctx.compact.decode_model(baseline), criterion)
                report['baselines'].append(dict(case=number, profile=profile, bytes=len(baseline), **before))
                for pre in report['pre_grid']:
                    blob4, pcm, details = ctx.v4.encode(source, profile, common, pre=pre, bandwidth=.97)
                    blob, _ = ctx.compact.repack(blob4)
                    row = emit(ctx, f'case{number}-p{profile}-pre{pre}', blob, pcm, source, criterion, (common, only))
                    row.update(case=number, profile=profile, pre=pre, old_bytes=len(baseline),
                               fits_old_bytes=len(blob) <= len(baseline),
                               old_floors_pass=ctx.floors(row['metrics'], before['metrics']),
                               seconds=details['seconds'])
                    report['rows'].append(row)
                    save(ctx.output / 'results-private.json', report)
                    print(json.dumps({key: row[key] for key in ('case', 'profile', 'pre', 'bytes', 'fits_old_bytes', 'old_floors_pass')}), flush=True)
    report['status'] = 'complete'
    save(ctx.output / 'results-private.json', report)


if __name__ == '__main__':
    cli = parser(__doc__)
    cli.add_argument('--mode', choices=('target', 'tuning'), required=True)
    from pathlib import Path
    for name in ('reference', 'incumbent', 'manifest'):
        cli.add_argument('--' + name, type=Path)
    main(cli.parse_args())
