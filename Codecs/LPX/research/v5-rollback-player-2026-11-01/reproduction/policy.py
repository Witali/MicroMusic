"""Pure finite-scope/header/report checks; imports no numerical codec modules."""
from __future__ import annotations

import hashlib
import json

PRODUCTION = '806d0c4931c95075d7ea1bffec1ce870d1d06631'
SAMPLES, RESETS, BYTES = 281632, 5, 16141
sha = lambda raw: hashlib.sha256(raw).hexdigest()
normalize = lambda value: json.loads(json.dumps(value, allow_nan=False))


def require(condition, message):
    if not condition: raise ValueError(message)


def rows():
    return [dict(id='%s-%03d' % (role, irq), role=role, assembly=True,
                 extra_irq_cycles=irq, storage='rom')
            for role in ('baseline', 'candidate') for irq in (0, 100)]


def geometry(parts, blobs):
    require(len(parts) == len(blobs) == RESETS, 'The complete reset count changed')
    at = total = 0
    for index, (part, blob) in enumerate(zip(parts, blobs)):
        require(part['index'] == index and part['start'] == at and part['profile'] == 4,
                'Original reset order/profile changed')
        require(22 <= len(blob) <= 65535 and len(blob) == part['file_bytes']
                and sha(blob) == part['stream_sha256'], 'Stored stream identity/size changed')
        require(blob[:5] == b'L4HY\x05' and blob[5] & 127 == 4
                and blob[5] == part.get('flags', blob[5]), 'Expected the exact V5 flags')
        require(int.from_bytes(blob[6:8], 'little') == 8000
                and int.from_bytes(blob[8:12], 'little') == part['samples']
                and 1 <= part['samples'] <= 64000
                and int.from_bytes(blob[12:14], 'little') <= 16384
                and int.from_bytes(blob[14:16], 'little') <= 11469
                and int.from_bytes(blob[16:18], 'little') == 320
                and int.from_bytes(blob[18:20], 'little') == 160
                and len(blob) == 22 + int.from_bytes(blob[20:22], 'little'),
                'Header/sample/payload geometry changed')
        at += part['samples']; total += len(blob)
    require(at == SAMPLES and total == BYTES, 'The complete whole-context size changed')


def report_ok(report):
    require(all(type(report.get(k)) is int for k in ('produced', 'played', 'timer_ticks', 'timer_events',
        'underruns', 'decoder_error', 'observer_errors', 'observer_exit_code', 'queued_at_stop',
        'eof', 'stopped', 'timer_started', 'stack_margin_all_bytes')), 'Malformed observer counters')
    require(all(report[k] == SAMPLES for k in ('produced', 'played', 'timer_ticks', 'timer_events')),
            'Incomplete physical sample/tick coverage')
    require(all(report[k] == 0 for k in ('underruns', 'decoder_error', 'observer_errors',
        'observer_exit_code', 'queued_at_stop')), 'Physical playback failed')
    require(all(report[k] == 1 for k in ('eof', 'stopped', 'timer_started'))
            and report['stack_margin_all_bytes'] > 0, 'Final queue/EOF/stack failed')
    require(report['cpu_hz'] == 16000000 and report['audio_hz'] == 8000, 'Clock profile changed')
    require(1996 <= report['tick_interval_min_cycles'] <= report['tick_interval_max_cycles'] <= 2004
            and 1936 <= report['pwm_interval_min_cycles'] <= report['pwm_interval_max_cycles'] <= 2064,
            'Observed timing bounds failed')
