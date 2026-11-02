"""Shared whole-output admission and recoverable checkpoints for quality rounds.

All media, fingerprints and detailed journals belong in ignored build/. A
single atomic best pointer references immutable candidate/metric files. The
selected.lpx convenience copy is not the crash-recovery authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
ACTIVE = ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0, str(ACTIVE/'tools'))

import numpy as np
import speech_compact as compact
import speech_sparse80 as sparse
from refine_speech_compact import quality, no_regression
from speech_noise_objective import NoiseObjective
from standard_metrics import pwm_duties, pwm_pcm16
from voice_character import compare_voice, track_pitch


def atomic_bytes(path, data):
    pending = path.with_name(path.name+'.partial')
    pending.write_bytes(data)
    pending.replace(path)


def save(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, allow_nan=False)+'\n').encode('utf-8'))


def fields(blob):
    if blob[4:6] == bytes((8, 15)):
        n, spectra, params, pulses, pre, bright = sparse.unpack(blob)
        return n, True, spectra, params, pulses, pre, bright
    n, profile, spectra, params, pulses, pre, bright, extras = compact.unpack(blob)
    if profile != 4 or any(amplitude for _, amplitude in extras):
        raise ValueError('Expected sparse80 or v5/P4 without extra innovations')
    return n, False, spectra, params, pulses, pre, bright


def recover_best(directory):
    """Resolve the committed pointer; ignore incomplete/orphan convenience files."""
    directory = Path(directory)
    pointer = json.loads((directory/'best-private.json').read_text(encoding='utf-8'))
    filename = pointer['candidate_file']
    if filename != f"candidate-{pointer['selected_id']:03d}.lpx":
        raise ValueError('Invalid checkpoint filename')
    blob = (directory/filename).read_bytes()
    if hashlib.sha256(blob).hexdigest() != pointer['candidate_sha256']:
        raise ValueError('Checkpoint stream changed')
    row = json.loads((directory/f"candidate-{pointer['selected_id']:03d}-private.json").read_text(encoding='utf-8'))
    if row['id'] != pointer['selected_id'] or not row['admissible']:
        raise ValueError('Checkpoint metadata is not an admitted candidate')
    return blob, row


class RoundAdmission:
    def __init__(self, reference, incumbent, output, common, only, *, speech=True):
        self.output = Path(output).resolve()
        self.output.relative_to((ROOT/'build').resolve())
        if self.output.exists():
            raise ValueError('Use a fresh ignored round directory')
        self.incumbent = bytes(incumbent)
        n, self.sparse80, *_ = fields(self.incumbent)
        reference = np.asarray(reference)
        if (reference.shape != (n,) or reference.dtype.kind not in 'iu'
                or int(reference.min()) < -32768 or int(reference.max()) > 32767):
            raise ValueError('Expected the exact declared PCM16 target')
        self.reference = reference.astype(np.int16, copy=True)
        self.reference.flags.writeable = False
        self.cap = n*(2 if self.sparse80 else 3)//64
        if len(self.incumbent) > self.cap:
            raise ValueError('Incumbent exceeds complete-file cap')
        self.common, self.only, self.speech = common, only, bool(speech)
        self.track = track_pitch(self.reference)
        self.objective = NoiseObjective(self.reference, self.track.period)
        self.rows, self.attempts, self.candidates, self.seen = [], [], [], {}
        self.output.mkdir(parents=True)
        self.add(self.incumbent, origin='protected_incumbent')

    def add(self, blob, expected=None, *, origin=None, work=None):
        blob = bytes(blob)
        work = {} if work is None else dict(work)
        if any(isinstance(value, bool) or not isinstance(value, (int, np.integer))
               or value < 0 for value in work.values()):
            raise ValueError('Expected nonnegative integer work counters')
        n, sparse80, *_ = fields(blob)
        if n != len(self.reference) or sparse80 != self.sparse80 or len(blob) > self.cap:
            raise ValueError('Candidate changed geometry, format or complete-file cap')
        modeled = sparse.decode_model(blob) if sparse80 else compact.decode_model(blob)
        if expected is not None and not np.array_equal(np.asarray(expected)[:n], modeled):
            raise AssertionError('Search output differs from independent model')
        attempt = dict(id=len(self.attempts), origin=origin,
                       work={key: int(value) for key, value in work.items()})
        if blob in self.seen:
            attempt['duplicate_of'] = self.seen[blob]
            self.attempts.append(attempt)
            save(self.output/f"attempt-{attempt['id']:03d}-private.json", attempt)
            return self.rows[self.seen[blob]]
        bridge = sparse.expand(blob) if sparse80 else blob
        for receiver in (self.common, self.only):
            if (not np.array_equal(receiver.decode_one_s16(bridge, n), modeled)
                    or not np.array_equal(receiver.decode_one(bridge, n), pwm_duties(modeled))):
                raise AssertionError('Native common/v5-only PCM/PWM differs')
        pwm = pwm_pcm16(modeled)
        voice = [compare_voice(self.reference, output, reference_track=self.track)
                 for output in (modeled, pwm)]
        score = float(np.mean([self.objective.voice_objective(output)+self.objective(output)
                               for output in (modeled, pwm)]))
        row = dict(id=len(self.rows), origin=origin, file_bytes=len(blob), score=score,
                   metrics=quality(self.reference, modeled, self.speech),
                   voice=voice[0], pwm_voice=voice[1],
                   clipped_samples=int(np.count_nonzero((modeled <= -32768) | (modeled >= 32767))),
                   differs_from_incumbent=blob != self.incumbent,
                   native_common_and_v5_only_pcm_pwm_exact=True)
        baseline = self.rows[0] if self.rows else row
        row['admissible'] = bool(no_regression(row['metrics'], baseline['metrics'])
            and row['clipped_samples'] <= baseline['clipped_samples']
            and all(row[key]['within_tolerance_frames'] >= baseline[key]['within_tolerance_frames']
                    for key in ('voice', 'pwm_voice')))
        filename = f"candidate-{row['id']:03d}.lpx"
        # These files are immutable after successful creation. Commit only the
        # small pointer after both exist, so an interrupted write keeps the
        # previous best recoverable without a multi-file transaction.
        atomic_bytes(self.output/filename, blob)
        save(self.output/f"candidate-{row['id']:03d}-private.json", row)
        self.rows.append(row)
        self.candidates.append((blob, modeled))
        self.seen[blob] = row['id']
        attempt['candidate_id'] = row['id']
        self.attempts.append(attempt)
        save(self.output/f"attempt-{attempt['id']:03d}-private.json", attempt)
        selected = self.best_row()
        best = self.candidates[selected['id']][0]
        save(self.output/'best-private.json', dict(selected_id=selected['id'],
             candidate_file=f"candidate-{selected['id']:03d}.lpx",
             candidate_sha256=hashlib.sha256(best).hexdigest()))
        atomic_bytes(self.output/'selected.lpx', best)
        return row

    def best_row(self):
        return min((row for row in self.rows if row['admissible']),
                   key=lambda row: (row['score'], row['file_bytes'], row['id']))

    def finish(self, **metadata):
        selected = self.best_row()
        blob, pcm = self.candidates[selected['id']]
        recovered, _ = recover_best(self.output)
        if recovered != blob:
            raise AssertionError('Durable checkpoint differs from final selection')
        totals = {}
        for attempt in self.attempts:
            for key, value in attempt['work'].items():
                totals[key] = totals.get(key, 0)+value
        report = dict(schema='lpx-whole-output-round-v1', selected_id=selected['id'],
                      selected_differs_from_incumbent=blob != self.incumbent,
                      candidates=self.rows, attempts=self.attempts, actual_work_totals=totals,
                      complete_byte_cap=self.cap, **metadata)
        save(self.output/'report-private.json', report)
        return blob, pcm, report
