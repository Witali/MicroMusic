"""Prepare anonymous LPX inputs from the local shared collection, without encoding.

References retain original levels. Conversion is a channel average, rational
resampling to 8 kHz when needed, then one nearest-even rounding and PCM16 clamp.
Generated audio and source provenance must remain in an ignored build directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import wave

import numpy as np
from scipy.signal import resample_poly
import soundfile as sf

COHORTS = ('speech', 'regression', 'independent', 'phrases', 'music', 'instruments')
TUNING = frozenset(('ru_pushkin', 'ru_square', 'en_sense', 'en_portrait'))
EVALUATION = frozenset(('ru_slutskaya', 'ru_russia', 'en_letter', 'en_normcore'))
AUDIO = frozenset(('.wav', '.ogg', '.flac', '.mp3'))
RATE = 8000


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _safe(root, relative):
    relative = Path(relative)
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root):
        raise ValueError('Declared input escapes the collection root')
    return path


def _split(source):
    if source in TUNING:
        return 'tuning'
    if source in EVALUATION:
        return 'evaluation'
    return 'unknown'


def _language(source):
    return source[:2] if source.startswith(('ru_', 'en_')) else 'und'


def _source_id(identifier):
    return next((s for s in sorted(TUNING | EVALUATION) if identifier.startswith(s)), identifier)


def balanced_segments(samples, max_segment_samples=64000):
    """Cover every sample with balanced, nonempty spans no longer than the limit."""
    if samples <= 0 or not 0 < max_segment_samples <= 64000:
        raise ValueError('Sample count must be positive and segment limit in 1..64000')
    count = (samples + max_segment_samples - 1) // max_segment_samples
    size, extra = divmod(samples, count)
    result, start = [], 0
    for index in range(count):
        length = size + (index < extra)
        result.append({'index': index, 'start': start, 'samples': length})
        start += length
    return result


def _ignored_output(output):
    ancestor = output
    while not ancestor.exists():
        ancestor = ancestor.parent
    result = subprocess.run(['git', '-C', str(ancestor), 'check-ignore', '--quiet',
                             str(output / '.lpx-corpus-output')], capture_output=True)
    if result.returncode != 0:
        raise ValueError('Output must be inside an ignored Git build directory')


def _candidates(root, index, cohorts):
    result, manifests = [], {}

    def manifest(cohort, relative):
        path = _safe(root, relative)
        content = path.read_bytes()
        if relative not in index or _sha(content) != index[relative]['sha256'] or (
                'bytes' in index[relative] and len(content) != index[relative]['bytes']):
            raise ValueError('Indexed cohort manifest hash/size mismatch')
        manifests[cohort] = _sha(content)
        return _json(path)

    def add(cohort, relative, *, source='', language='und', condition='natural',
            split='additional', kind='speech', file_hash=None, pcm_hash=None,
            samples=None, primary_8k=False, upstream=None):
        result.append(dict(cohort=cohort, relative=str(relative).replace('\\', '/'),
            source=source, language=language, condition=condition, split=split,
            kind=kind, expected_file_hash=file_hash, expected_pcm_hash=pcm_hash,
            expected_samples=samples, primary_8k=primary_8k, upstream=upstream))

    if 'speech' in cohorts:
        data = manifest('speech', 'speech-ru-en-originals/corpus.json')
        for row in data['clips']:
            source = row['source']
            add('speech', f"speech-ru-en-originals/clips/{row['id']}/input.wav",
                source=row['id'], language=row.get('language', _language(source)),
                condition=row.get('condition', 'natural'), split=_split(source),
                # Upstream `frames` counts Speex packets, not WAV samples.
                # The checked WAV header supplies the complete sample length.
                file_hash=row['input_sha256'], primary_8k=True)

    if 'regression' in cohorts:
        data = manifest('regression', 'speech-music-tests-8000/corpus.json')
        for row in data['cases']:
            provenance = row.get('provenance', {})
            source = _source_id(provenance.get('source', provenance.get('source_case', row['id'])))
            add('regression', f"speech-music-tests-8000/{row['id']}/reference.wav",
                source=row['id'], language=_language(source), condition=row['group'],
                split=_split(source) if row['kind'] == 'speech' else 'non_speech', kind=row['kind'],
                pcm_hash=row['reference_sha256'], samples=row['samples'], primary_8k=True)

    for cohort, folder in [('independent', 'independent-speech-originals'), ('music', 'music-originals')]:
        if cohort not in cohorts:
            continue
        data = manifest(cohort, folder + '/sources.json')
        for row in data:
            # Upstream filenames/local paths can differ from the collected copy.
            matches = sorted(name for name, rec in index.items() if name.startswith(folder + '/')
                             and Path(name).suffix.lower() in AUDIO and rec['sha256'] == row['sha256'])
            if not matches:
                raise ValueError('Declared original is absent from the indexed collection')
            add(cohort, matches[0], source=row['id'], file_hash=row['sha256'],
                language=_language(row['id']) if cohort == 'independent' else 'und',
                split='additional' if cohort == 'independent' else 'non_speech',
                kind='speech' if cohort == 'independent' else 'music')

    if 'phrases' in cohorts:
        data = manifest('phrases', 'new-phrases-7500/manifest.json')
        for row in data['clips']:
            add('phrases', f"new-phrases-7500/{row['id']}/{row['reference_file']}",
                source=row['id'], language='ru', condition='prepared',
                file_hash=row['reference_sha256'],
                upstream={k: row.get(k) for k in ('source_sha256', 'source_mono_dc_removed',
                    'normalization_gain', 'trailing_zero_padding_samples')})

    if 'instruments' in cohorts:
        for name in sorted(index):
            if name.startswith('instrument-samples/') and Path(name).suffix.lower() == '.wav':
                add('instruments', name, condition='isolated_instrument', split='non_speech', kind='music')
    return result, manifests


def _read_audio(path):
    try:
        values, rate = sf.read(path, dtype='float64', always_2d=True)
    except (OSError, sf.LibsndfileError):
        raise ValueError('Cannot read an indexed audio input') from None
    if not len(values) or rate <= 0 or not np.all(np.isfinite(values)):
        raise ValueError('Input audio must be nonempty and finite')
    channels = values.shape[1]
    mono = values[:, 0] if channels == 1 else values.mean(axis=1)
    original_samples = len(mono)
    if rate != RATE:
        divisor = math.gcd(rate, RATE)
        mono = resample_poly(mono, RATE // divisor, rate // divisor)
    if not np.all(np.isfinite(mono)):
        raise ValueError('Converted input audio must remain finite')
    scaled = np.rint(mono * 32768.)
    clipped = int(np.count_nonzero((scaled < -32768) | (scaled > 32767)))
    pcm = np.clip(scaled, -32768, 32767).astype('<i2')
    return pcm, dict(source_rate=int(rate), source_channels=channels,
        source_samples=original_samples, channel_average=channels != 1, resampled=rate != RATE,
        rounding='nearest-even once after channel average/resampling', clipped_samples=clipped,
        gain_normalization=False, dc_removal=False,
        peak_before_pcm16_clamp=float(np.max(np.abs(mono))))


def _write_wav(path, pcm):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(pcm.astype('<i2', copy=False).tobytes())


def prepare(collection, output, cohorts=None, max_segment_samples=64000):
    """Return/write a safe JSON manifest and complete anonymous PCM16 references.

    Actual source names, paths and deduplication aliases are written only to
    private-manifest.json inside the ignored output. No encoding occurs here.
    Exact complete PCM duplicates retain their first canonical cohort instance.
    """
    root, output = Path(collection).resolve(), Path(output).resolve()
    if root == output or root in output.parents or output in root.parents:
        raise ValueError('Collection and output trees must not overlap')
    _ignored_output(output)
    selected = tuple(COHORTS if cohorts is None else cohorts)
    if not selected or len(set(selected)) != len(selected) or set(selected) - set(COHORTS):
        raise ValueError('Expected a nonempty unique selection of known cohorts')
    # Canonical ordering makes IDs and duplicate ownership independent of CLI order.
    selected = tuple(c for c in COHORTS if c in selected)
    index_path = root / 'INDEX.json'
    inventory = _json(index_path)
    if inventory.get('schema') != 'micromusic-local-audio-collection-v1':
        raise ValueError('Unsupported shared collection schema')
    index = {}
    for record in inventory['files']:
        name = record['file']
        _safe(root, name)
        if name in index:
            raise ValueError('Duplicate indexed path')
        index[name] = record
    inputs, manifests = _candidates(root, index, selected)
    if not inputs:
        raise ValueError('Selected cohorts contain no inputs')
    prepared, private, seen, duplicates = [], [], {}, 0
    # Validate and convert everything before writing any output reference.
    for entry in inputs:
        name = entry['relative']
        path = _safe(root, name)
        if name not in index:
            raise ValueError('Selected input has no indexed file hash')
        content = path.read_bytes()
        file_hash = _sha(content)
        if file_hash != index[name]['sha256'] or ('bytes' in index[name] and len(content) != index[name]['bytes']):
            raise ValueError('Indexed input file hash/size mismatch')
        if entry['expected_file_hash'] and file_hash != entry['expected_file_hash']:
            raise ValueError('Declared original/input file hash mismatch')
        pcm, conversion = _read_audio(path)
        if entry['primary_8k'] and (conversion['source_rate'] != RATE or conversion['source_channels'] != 1):
            raise ValueError('Primary reference must already be mono 8 kHz')
        if entry['expected_samples'] is not None and len(pcm) != entry['expected_samples']:
            raise ValueError('Declared reference sample count mismatch')
        pcm_hash = _sha(pcm.tobytes())
        if entry['expected_pcm_hash'] and pcm_hash != entry['expected_pcm_hash']:
            raise ValueError('Declared reference PCM16 sample hash mismatch')
        identifier = 'case-' + _sha((entry['cohort'] + ':' + file_hash + ':' + pcm_hash).encode())[:16]
        duplicate = seen.get(pcm_hash)
        private.append(dict(id=duplicate or identifier, source_relative=name, source_id=entry['source'],
            cohort=entry['cohort'], input_file_sha256=file_hash, duplicate=duplicate is not None,
            upstream_preparation=entry['upstream']))
        if duplicate is not None:
            duplicates += 1
            continue
        seen[pcm_hash] = identifier
        reference = f'references/{identifier}/reference.wav'
        spans = balanced_segments(len(pcm), max_segment_samples)
        for span in spans:
            start, size = span['start'], span['samples']
            span['pcm16_sha256'] = _sha(pcm[start:start + size].tobytes())
            span['reference'] = reference if len(spans) == 1 else f"references/{identifier}/segment-{span['index']:03d}.wav"
        public = {k: entry[k] for k in ('cohort', 'language', 'condition', 'split', 'kind')}
        public.update(id=identifier, samples=len(pcm), reference_pcm16_sha256=pcm_hash,
            input_file_sha256=file_hash, reference=reference, segments=spans, conversion=conversion)
        prepared.append((public, pcm))

    output.mkdir(parents=True, exist_ok=True)
    for case, pcm in prepared:
        _write_wav(output / case['reference'], pcm)
        for span in case['segments']:
            if span['reference'] != case['reference']:
                _write_wav(output / span['reference'], pcm[span['start']:span['start'] + span['samples']])
    manifest = dict(schema='lpx-shared-corpus-v1', sample_rate=RATE, cohorts=list(selected),
        collection_index_sha256=_sha(index_path.read_bytes()), input_manifests_sha256=manifests,
        signal_policy='Preserve levels/DC; mono channel average; rational resample only when necessary; one nearest-even PCM16 round/clamp with counts.',
        max_segment_samples=max_segment_samples, source_inputs=len(inputs), duplicates_removed=duplicates,
        cohort_counts=dict(Counter(case['cohort'] for case, pcm in prepared)),
        cases=[case for case, pcm in prepared])
    for name, value in [('manifest.json', manifest), ('private-manifest.json', dict(
            policy='PRIVATE local provenance; do not commit or upload.', inputs=private))]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',
                                   encoding='utf-8', newline='\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('collection', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cohorts', choices=COHORTS, nargs='+')
    parser.add_argument('--max-segment-samples', type=int, default=64000)
    args = parser.parse_args()
    result = prepare(args.collection, args.output, args.cohorts, args.max_segment_samples)
    print(json.dumps({k: result[k] for k in ('schema', 'source_inputs', 'duplicates_removed', 'cohort_counts')}))


if __name__ == '__main__':
    main()
