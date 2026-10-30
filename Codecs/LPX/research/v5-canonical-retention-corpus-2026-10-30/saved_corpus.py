"""Private saved-input binding and anonymous result contracts; no codec imports."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

PHASES = ('speech-screen', 'speech-default', 'nonspeech-default')
VALUE_KEYS = ('metrics', 'voice', 'pwm_voice', 'noise', 'pwm_noise',
              'domain_scores', 'score', 'clipped_samples',
              'voice_components', 'pwm_voice_components')
FLAG_KEYS = ('old_pcm_pwm_floors_passed', 'clipped_sample_floor_passed',
             'pcm_period_coverage_floor_passed', 'pwm_period_coverage_floor_passed',
             'joint_objective_nonregression')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class Inputs:
    def __init__(self):
        self.pins = {}

    def read(self, path, digest=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        actual = sha(raw)
        if digest is not None and digest != actual:
            raise ValueError('An immutable saved input changed')
        if str(path) in self.pins and self.pins[str(path)] != actual:
            raise ValueError('An input changed after it was bound')
        self.pins[str(path)] = actual
        return raw

    def stream(self, meta):
        blob = self.read(meta['path'], meta['stream_sha256'])
        if len(blob) != meta['file_bytes']:
            raise ValueError('Saved byte length differs')
        return blob

    def chain(self, entry, record):
        blobs, position = [], 0
        if len(entry['segments']) != len(record['segments']):
            raise ValueError('Whole reset count differs')
        for index, (part, segment) in enumerate(zip(entry['segments'], record['segments'])):
            if (part['index'] != index or part['start'] != position
                    or part['samples'] != segment['samples'] or part['profile'] != record['profile']):
                raise ValueError('Ordered whole reset geometry differs')
            blobs.append(self.stream(part))
            position += segment['samples']
        if (not blobs or position != record['samples'] or entry['samples'] != position
                or sum(map(len, blobs)) != entry['stream_bytes']):
            raise ValueError('Whole source length or actual byte cost differs')
        return tuple(blobs)

    def verify(self):
        for path, digest in self.pins.items():
            if sha(Path(path).read_bytes()) != digest:
                raise ValueError('A pinned replay input changed')


def load_saved(study, inputs):
    study = Path(study).resolve()
    binding = json.loads(inputs.read(study/'binding-private.json'))
    if binding['identity'] != sha(canonical({k:v for k,v in binding.items() if k != 'identity'})):
        raise ValueError('Prepared binding identity changed')
    counts = Counter(job['phase'] for job in binding['jobs'])
    if dict(counts) != dict(zip(PHASES, (98,14,6))):
        raise ValueError('The full 118-record scope changed')
    rows = []
    for job in binding['jobs']:
        record = binding['speech_records' if job['speech'] else 'nonspeech_records'][job['record_index']]
        folder = study/'records'/job['phase']/('source-%03d'%job['source_ordinal'])/('profile-%d'%record['profile'])
        marker = json.loads(inputs.read(folder/'complete-private.json'))
        row = json.loads(inputs.read(folder/'record-private.json', marker['report_sha256']))
        if marker['identity'] != row['identity'] or row['identity'] != sha(canonical([binding['identity'],job])):
            raise ValueError('A saved record belongs to another binding')
        for name, value in job.items():
            if row[name] != value:
                raise ValueError('A saved record differs from the declared job')
        for relative, digest in marker['artifacts_sha256'].items():
            path = (folder/relative).resolve()
            if not path.is_relative_to(folder):
                raise ValueError('A saved artifact escapes its record')
            inputs.read(path,digest)
        if ([h['index'] for h in row['segment_searches']] != job['edited_segments']
                or row['profile'] != record['profile'] or row['samples'] != record['samples']):
            raise ValueError('Saved reset history geometry differs')
        for history in row['segment_searches']:
            segment = record['segments'][history['index']]
            if any(history[k] != segment[k] for k in ('start','samples')):
                raise ValueError('Saved local target geometry differs')
        rows.append(dict(job=job,record=record,saved=row))
    keys = [key(item['saved']) for item in rows]
    if len(set(keys)) != 118:
        raise ValueError('Duplicate corpus phase/source/profile record')
    return binding,rows


def key(saved):
    return saved['phase'],saved['source_ordinal'],saved['profile']


def histories(item, inputs, ranker, equal):
    """Bind every sink row and independently reproduce static final ranking."""
    result = []
    for history in item['saved']['segment_searches']:
        report = history['report']
        pool = [inputs.stream(meta) for meta in history['pool']]
        if len(pool) != len(report['candidates']) or len(set(pool)) != len(pool):
            raise ValueError('Saved pool is incomplete or not byte-deduplicated')
        for index,(blob,meta,row) in enumerate(zip(pool,history['pool'],report['candidates'])):
            if meta['id'] != index or row['id'] != index or row['file_bytes'] != len(blob):
                raise ValueError('Saved pool order or actual cost differs')
        ranked,allowed = ranker(report['candidates'],report['complete_byte_cap'])
        for name in ('selected_id','raw_id','frontier'):
            equal(ranked[name],report[name],'saved-final-'+name)
        for flag,row in zip(allowed,report['candidates']):
            equal(flag,row['admissible'],'saved-static-admission')
        if len(report['stages']) != report['refinement_calls'] or len(report['stages']) > item['job']['max_refinement_calls']:
            raise ValueError('Saved bounded stage history differs')
        result.append(dict(index=history['index'],pool=pool,report=report))
    return result


def old_chains(item, inputs):
    return {chain['role']:(inputs.chain(chain,item['record']),chain)
            for chain in item['saved']['chains'] if chain is not None}


def paired_screen(item, indexed):
    row = item['saved']
    return indexed.get(('speech-screen',row['source_ordinal'],row['profile'])) if row['phase']=='speech-default' else None


def incumbent_views(item, indexed, inputs):
    """Old three choices plus exactly actual paired-screen budget fallbacks."""
    own = old_chains(item,inputs)
    result = [('old-'+role,blobs) for role,(blobs,_) in own.items()]
    shallow = paired_screen(item,indexed)
    if shallow is not None:
        if item['saved']['target_reference_pcm16_sha256'] != shallow['saved']['target_reference_pcm16_sha256']:
            raise ValueError('Paired screen/default target differs')
        screen = old_chains(shallow,inputs)
        if own['control'][0] != screen['control'][0]:
            raise ValueError('Paired screen/default admission anchor differs')
        for budget in shallow['saved']['budgets']:
            for field in ('selected','raw_tradeoff'):
                role = budget[field]
                if role is not None:
                    result.append(('screen-%d-%s'%(budget['percent'],field),screen[role][0]))
    return result


def known_rows(item,indexed,inputs):
    result = {}
    for source in (item,paired_screen(item,indexed)):
        if source is not None:
            for blobs,row in old_chains(source,inputs).values():
                result.setdefault(blobs,[]).append(row)
    return result


def player_union(rows,inputs):
    """Reconstruct only original changed automatic choices plus their anchors."""
    union = set()
    for item in rows:
        chains = old_chains(item,inputs)
        baseline = chains['control'][0]
        for decision in item['saved']['budgets']:
            role = decision['selected']
            if role is None:
                continue
            blobs,row = chains[role]
            if not row['automatic_quality_eligible'] or row['stream_bytes'] > decision['cap']:
                raise ValueError('Original automatic incumbent is no longer eligible')
            if blobs != baseline:
                union.update((baseline,blobs))
    if len(union) != 75:
        raise ValueError('The original fixed player union differs')
    return union


def assert_incumbent(chosen, old, cap):
    if old is None or not old['automatic_quality_eligible'] or old['stream_bytes'] > cap:
        return
    if chosen is None or (chosen['score'],chosen['stream_bytes']) > (old['score'],old['stream_bytes']):
        raise AssertionError('A known feasible admitted incumbent was lost')


def player_status(blobs,baseline,union):
    if blobs == baseline:
        return 'unchanged-baseline'
    return 'old-union' if blobs in union else 'requires-new-proof'
