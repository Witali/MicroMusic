"""Read and attest the fixed two-profile saved-output diagnostic."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from prefixes import ranked_prefix_ids


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_record(study, phase, profile):
    folder = Path(study)/'records'/phase/'source-042'/('profile-%d'%profile)
    marker = json.loads((folder/'complete-private.json').read_text())
    raw = (folder/'record-private.json').read_bytes()
    if marker['report_sha256'] != sha(raw):
        raise ValueError('An immutable record changed')
    row = json.loads(raw)
    if row['identity'] != marker['identity']:
        raise ValueError('A saved record identity changed')
    for name, digest in marker['artifacts_sha256'].items():
        path = folder/name
        if not path.resolve().is_relative_to(folder.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError('A saved pool or attempt artifact changed')
    if (row['phase'] != phase or row['source_ordinal'] != 42 or row['profile'] != profile
            or len(row['segment_searches']) != 5 or row['mode'] != 'preserve'):
        raise ValueError('The fixed targeted geometry changed')
    return row


def stream(meta):
    blob = Path(meta['path']).read_bytes()
    if len(blob) != meta['file_bytes'] or sha(blob) != meta['stream_sha256']:
        raise ValueError('An exact saved stream changed')
    return blob


def actual_saved_contract(study):
    """Require depth1 to reproduce actual one-call local outputs byte-for-byte."""
    binding = json.loads((Path(study)/'binding-private.json').read_text())
    canonical = json.dumps({k:v for k,v in binding.items() if k != 'identity'},
                           sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if sha(canonical) != binding['identity']:
        raise ValueError('The prepared binding changed')
    multi = {(job['source_ordinal'],binding['speech_records'][job['record_index']]['profile'])
             for job in binding['jobs'] if job['phase'] == 'speech-default'
             and len(binding['speech_records'][job['record_index']]['segments']) > 1}
    if multi != {(42,4),(42,6)}:
        raise ValueError('The targeted multi-reset paired subset changed')
    rows, comparisons, final_ranks = {}, 0, 0
    for profile in (4,6):
        default = load_record(study,'speech-default',profile)
        screen = load_record(study,'speech-screen',profile)
        if default['target_reference_pcm16_sha256'] != screen['target_reference_pcm16_sha256']:
            raise ValueError('The screen/default target changed')
        for deep, shallow in zip(default['segment_searches'],screen['segment_searches']):
            if (deep['index'],deep['start'],deep['samples']) != (shallow['index'],shallow['start'],shallow['samples']):
                raise ValueError('Actual reset geometry changed')
            prefix = ranked_prefix_ids(deep['report'],1)
            final = ranked_prefix_ids(deep['report'],4)
            for label in ('selected','raw'):
                identifier = prefix[label]
                original = shallow['report'][label+'_id']
                if (identifier is None) != (original is None):
                    raise AssertionError('Prefix1 local presence differs from actual screen')
                if identifier is not None and stream(deep['pool'][identifier]) != stream(shallow['pool'][original]):
                    raise AssertionError('Prefix1 bytes differ from actual screen local output')
                comparisons += 1
                if final[label] != deep['report'][label+'_id']:
                    raise AssertionError('Full-prefix ranking differs from saved default')
                final_ranks += 1
        rows[profile] = dict(default=default,screen=screen)
    return rows, dict(status='PASS',profiles=2,resets=10,
        prefix1_local_byte_comparisons=comparisons,final_prefix_rank_checks=final_ranks,
        new_fits=0,new_refinements=0)
