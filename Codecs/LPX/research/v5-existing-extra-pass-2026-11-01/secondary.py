"""Read closed prior whole rows as a secondary comparator, never new seeds."""
from __future__ import annotations

from pathlib import Path

from extra_runtime import PREFIX,VALUE_KEYS,sha
PRIOR_ARMS={'joint-rate-v1':('T-local-0','T-full-0','G-full-0','G-full-.1','G-full-1'),
    'anchor-order':('T-time-0','T-priority-0','G-time-0','G-priority-0')}


def same_context(base,prior):
    for key in ('source_ordinal','nonspeech','profile','mode','samples','reference','level',
            'target_reference_pcm16_sha256'):
        if base[key]!=prior[key]:raise ValueError('Saved evidence changed recording/profile/level/target context')
    geometry=lambda value:[(p['start'],p['samples'],p['profile']) for p in value['segments']]
    if geometry(base)!=geometry(prior):raise ValueError('Saved evidence changed reset boundaries')
    for key in ('pcm16_sha256','samples','sample_rate'):
        if base['prepared_target'][key]!=prior['prepared_target'][key]:
            raise ValueError('Saved evidence changed exact prepared target geometry or bytes')


def read_prior(export,study_name,current_bases,inputs):
    """Reopen only closed producer metadata and actually compared whole bytes."""
    export=Path(export);binding=inputs.json(export/'binding-private.json');summary=inputs.json(export/'summary.json')
    if study_name not in PRIOR_ARMS:raise ValueError('Unknown fixed prior study')
    if binding['status']!='PASS' or summary['status']!='PASS':raise ValueError('Prior export is not terminal PASS')
    expected_records=60 if study_name=='joint-rate-v1' else 48
    if summary['arm_records']!=expected_records:raise ValueError('Prior producer scope differs')
    def export_input(path):
        path=Path(path).resolve();digest=binding['input_files_sha256'].get(str(path))
        if digest is None:raise ValueError('Prior final export omitted a required input receipt')
        return inputs.json(path,digest)
    prior_manifest=export_input(binding['baselines_path'])
    prior_bases={b['id']:b for b in prior_manifest['baselines']}
    bases={b['id']:b for b in current_bases};rows=[];producer_bindings=[]
    for shard in binding['shard_paths']:
        shard=Path(shard)
        def closed(name):
            path=(shard/name).resolve();digest=binding['input_files_sha256'].get(str(path))
            if digest is None:raise ValueError('Prior final export omitted a required producer receipt')
            return inputs.json(path,digest)
        producer=closed('binding-private.json');attempt=closed('attempt-private.json');records=closed('results-private.json')
        if attempt['status']!='complete' or attempt['forbidden_fit_or_build_attempts']:
            raise ValueError('Prior producer did not close cleanly')
        producer_bindings.append(producer)
        for record in records:
            if record['baseline_id'] not in bases:continue
            base=bases[record['baseline_id']];same_context(base,prior_bases[base['id']])
            if record['profile']!=4:raise ValueError('Secondary comparison acquired another profile')
            if record['arm'] not in PRIOR_ARMS[study_name] or len(record['whole_rows'])!=len(record['whole_chains']):
                raise ValueError('Prior arm or ordered whole catalogue differs')
            for value,chain in zip(record['whole_rows'],record['whole_chains']):
                if value['id']!=chain['id']:raise ValueError('Prior whole row/byte IDs differ')
                # Re-derive these gates against the fresh anchor later. Include
                # prior eligible rows above B too, then filter actual current cap.
                if not value['automatic_quality_eligible']:continue
                parts=tuple(inputs.stream(meta) for meta in chain['segments'])
                if sum(map(len,parts))!=value['stream_bytes'] or len(parts)!=len(base['segments']):
                    raise ValueError('Prior actual ordered whole bytes differ')
                for meta,original in zip(chain['segments'],base['segments']):
                    if any(meta[key]!=original[key] for key in ('index','start','samples','profile')):
                        raise ValueError('Prior actual whole stream metadata changed reset geometry')
                rows.append(dict(study=study_name,baseline_id=base['id'],arm=record['arm'],job_id=record['id'],
                    candidate_id=value['id'],stream_bytes=value['stream_bytes'],segments=chain['segments'],
                    value={key:value[key] for key in VALUE_KEYS},prior_quality_eligible=True,
                    whole_bytes_key=[sha(blob) for blob in parts],
                    producer_binding_path=str((shard/'binding-private.json').resolve()),
                    producer_results_path=str((shard/'results-private.json').resolve()),
                    provenance='Saved prior whole measurement; not remeasured or a new helper input'))
    return rows,producer_bindings


def choose_secondary(rows,cap,admission,anchor):
    available=[]
    for row in rows:
        if row['stream_bytes']<=cap and all(admission(row['value'],anchor).values()):available.append(row)
    key=lambda r:(r['value']['score'],r['stream_bytes'],0 if r['study']=='joint-rate-v1' else 1,
        PRIOR_ARMS[r['study']].index(r['arm']),r['job_id'],r['candidate_id'])
    return None if not available else min(available,key=key)
