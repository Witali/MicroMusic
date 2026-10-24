"""Reuse the local credited RU/EN Speex corpus as unchanged-level 7.5-kHz tests.

No download, gain normalization, DC removal or clipping occurs. Audio remains
under ignored build output. Natural cases use the existing 48-kHz originals;
modified quiet/noisy cases use their existing 8-kHz modified originals.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np
import scipy
from scipy.signal import resample_poly
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
RATE = 7500
SHORT_SAMPLES = 15360  # exactly 2.048 seconds and 240 complete 64-sample blocks
TUNING = frozenset(('ru_pushkin', 'ru_square', 'en_sense', 'en_portrait'))
EVALUATION = frozenset(('ru_slutskaya', 'ru_russia', 'en_letter', 'en_normcore'))
UPSTREAM_PROJECT = 'Codecs/Speex/AVR'
UPSTREAM_COMMIT = '8edb481'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest():
    """Fingerprint the actual tool without platform-dependent CRLF changes."""
    return hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def write_float_wav(path, values):
    """Write deterministic mono IEEE-float WAV, without timestamp metadata.

    libsndfile's normal FLOAT writer adds a PEAK chunk with the current time.
    Store the same float32 samples in standard fmt/fact/data chunks instead.
    """
    data = np.asarray(values, dtype='<f4').tobytes()
    fmt = struct.pack('<HHIIHH', 3, 1, RATE, RATE*4, 4, 32)
    chunks = b'fmt '+struct.pack('<I', len(fmt))+fmt
    chunks += b'fact'+struct.pack('<II', 4, len(values))
    chunks += b'data'+struct.pack('<I', len(data))+data
    Path(path).write_bytes(b'RIFF'+struct.pack('<I', len(chunks)+4)+b'WAVE'+chunks)


def checked_file(root, relative, expected_hash=None):
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Source file escapes the declared local corpus root')
    if not path.is_file():
        raise FileNotFoundError(f'Required local corpus file is missing: {relative}; no download is attempted')
    actual = digest(path)
    if expected_hash is not None and actual != expected_hash:
        raise ValueError(f'SHA-256 mismatch: {relative}')
    return path, actual


def speaker_split(source_id):
    if source_id in TUNING:
        return 'tuning'
    if source_id in EVALUATION:
        return 'evaluation'
    raise ValueError(f'Corpus source has no declared speaker split: {source_id}')


def attributed_text(sources):
    lines = ['# Local speech corpus source credits', '',
        'Original audio is reused from the existing Speex evaluation corpus. No TTS or new download is used.',
        'Derived 7.5-kHz references retain the source attribution and license.', '']
    for source in sources:
        lines += [f"## {source['id']}: {source.get('title', source['id'])}", '',
            f"Language: {source['language']}. Speaker: {source['speaker']}. Voice label: {source['voice']}.",
            f"Source page and article author credits: {source.get('page', '')}",
            f"Recording: {source.get('url', '')}",
            f"License: {source.get('license', '')} ({source.get('license_url', '')})",]
        if source.get('additional_credits'):
            lines.append(source['additional_credits'])
        lines += [f"Original OGG SHA-256: {source['sha256']}", '']
    return '\n'.join(lines)+'\n'


def prepare(source_root, output, source_manifest=None, source_inventory=None):
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    manifest_path = Path(source_manifest).resolve() if source_manifest else source_root/'corpus.json'
    corpus = json.loads(manifest_path.read_text(encoding='utf-8'))
    inventory_path = Path(source_inventory).resolve() if source_inventory else source_root.parent.parent/'tests/real-speech-sources.json'
    inventory = json.loads(inventory_path.read_text(encoding='utf-8')) if inventory_path.is_file() else None
    sources = corpus['sources']
    source_map = {s['id']:s for s in sources}
    if len(source_map) != len(sources) or len({c['id'] for c in corpus['clips']}) != len(corpus['clips']):
        raise ValueError('Corpus source/clip IDs must be unique')
    for source in sources:
        speaker_split(source['id'])
        checked_file(source_root, 'originals/'+source['id']+'.ogg', source['sha256'])
    if inventory is not None:
        entries = {s['id']:s for s in inventory['sources']}
        if set(entries) != set(source_map):
            raise ValueError('Source inventory and corpus report identify different recordings')
        for source_id, source in source_map.items():
            for key in ('language', 'voice', 'speaker', 'file', 'license'):
                if entries[source_id].get(key) != source.get(key):
                    raise ValueError(f'Source inventory disagrees with report: {source_id}/{key}')
    # Verify every expected 8-kHz input before producing any derived reference.
    for clip in corpus['clips']:
        path, _ = checked_file(source_root, 'clips/'+clip['id']+'/input.wav', clip['input_sha256'])
        info = sf.info(path)
        if info.samplerate != 8000 or info.channels != 1:
            raise ValueError('Expected the original mono 8-kHz Speex encoder input')
    output.mkdir(parents=True, exist_ok=True)
    records = []
    natural = [c for c in corpus['clips'] if c['condition'] == 'natural']
    for clip in corpus['clips']:
        source = source_map[clip['source']]
        if any(clip[key] != source[key] for key in ('language', 'voice', 'speaker')):
            raise ValueError('Clip speaker/language labels disagree with the credited source')
        condition = clip['condition']
        if condition not in ('natural', 'quiet_minus24dB', 'white_noise_15dB'):
            raise ValueError('Unknown source condition; preserve its explicit preparation before importing')
        chosen_relative = 'clips/'+clip['id']+'/original.wav'
        chosen_path, chosen_hash = checked_file(source_root, chosen_relative)
        audio, native_rate = sf.read(chosen_path, dtype='float64')
        if audio.ndim != 1 or not len(audio) or not np.all(np.isfinite(audio)):
            raise ValueError('Chosen original must be finite mono audio')
        if native_rate != (48000 if condition == 'natural' else 8000):
            raise ValueError('Natural references must use 48-kHz originals; stress references use modified 8-kHz originals')
        if condition != 'natural' and chosen_hash != clip['input_sha256']:
            raise ValueError('Modified stress original differs from the verified signal fed to the encoder')
        divisor = math.gcd(native_rate, RATE)
        converted = resample_poly(audio, RATE//divisor, native_rate//divisor)
        if len(converted) < SHORT_SAMPLES:
            raise ValueError('A fixed center window requires at least 2.048 seconds of original audio')
        matches = [c for c in natural if c['source'] == clip['source'] and c['start_seconds'] == clip['start_seconds']]
        if len(matches) != 1:
            raise ValueError('Every stress example must identify one natural base excerpt')
        base_id = matches[0]['id']
        for variant in ('full', 'center2048'):
            start = 0 if variant == 'full' else (len(converted)-SHORT_SAMPLES)//2
            unpadded = converted if variant == 'full' else converted[start:start+SHORT_SAMPLES]
            padded = np.pad(unpadded, (0, (-len(unpadded)) % 64))
            identifier = clip['id']+'-'+variant
            relative = Path('clips')/identifier/'reference.wav'
            destination = output/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_float_wav(destination, padded)
            # Report the bytes actually provided to the encoders, including
            # float32 storage rounding. No level adjustment is hidden here.
            saved, saved_rate = sf.read(destination, dtype='float64')
            if saved_rate != RATE or len(saved) != len(padded):
                raise AssertionError('Saved corpus reference changed rate or duration')
            over = int(np.count_nonzero(abs(saved) > 1.))
            relative_start = start/RATE
            relative_end = min(len(audio)/native_rate, relative_start+len(unpadded)/RATE)
            records.append(dict(id=identifier, source_id=source['id'], source_clip_id=clip['id'],
                base_clip_id=base_id, language=clip['language'], voice=clip['voice'], speaker=clip['speaker'],
                split=speaker_split(source['id']), condition=condition, variant=variant,
                reference=relative.as_posix(), reference_sha256=digest(destination),
                sample_rate=RATE, samples=len(saved), unpadded_samples=len(unpadded),
                padding_samples=len(saved)-len(unpadded), duration_seconds=len(saved)/RATE,
                content_duration_seconds=len(unpadded)/RATE,
                source_start_seconds=clip['start_seconds']+relative_start,
                source_end_seconds=clip['start_seconds']+relative_end,
                source_relative_start_seconds=relative_start, source_relative_end_seconds=relative_end,
                source_clip_start_seconds=clip['start_seconds'], source_file=chosen_relative,
                chosen_original_sha256=chosen_hash, source_sample_rate=native_rate,
                source_samples=len(audio), source_duration_seconds=len(audio)/native_rate,
                input_8000_sha256=clip['input_sha256'], source_ogg_sha256=source['sha256'],
                output_peak=float(np.max(abs(saved))), output_rms=float(np.sqrt(np.mean(saved**2))),
                output_mean=float(np.mean(saved)), input_pcm_range_exceeded=bool(over),
                input_pcm_range_exceeded_samples=over, cropped=variant != 'full',
                whole_phrase_guaranteed=False))
    manifest = dict(schema='micromusic-speech-corpus-v1', sample_rate=RATE,
        output_subtype='FLOAT', gain_normalization=False, dc_removal=False, clipping=False,
        resampling='scipy.signal.resample_poly with reduced integer rate ratio; default anti-alias filter',
        padding='Trailing zeros only, to a multiple of 64 samples',
        short_window=dict(samples=SHORT_SAMPLES, seconds=SHORT_SAMPLES/RATE,
            selection='Centered in the unpadded resampled excerpt; floor the initial sample index',
            note='Explicit fixed crop; may cut a word and is not a complete-phrase claim'),
        source_offset_note='Absolute offsets inherit the source excerpt start metadata; actual WAV frame counts determine duration, not the nominal eight-second label',
        split_definition=dict(tuning_source_ids=sorted(TUNING), evaluation_source_ids=sorted(EVALUATION),
            purpose='Speaker-disjoint evaluation of encoder algorithms; per-clip encoding/parameter optimization is still allowed'),
        source_manifest_sha256=digest(manifest_path),
        source_inventory_sha256=digest(inventory_path) if inventory is not None else None,
        source_sha256_normalized_lf=source_digest(),
        upstream=dict(project_relative_path=UPSTREAM_PROJECT, corpus_commit=UPSTREAM_COMMIT,
            source_manifest='reports/real-speech-corpus.json', source_inventory='tests/real-speech-sources.json'),
        sources=sources, clips=records,
        counts=dict(source_speakers=len(sources), source_clips=len(corpus['clips']), full=sum(c['variant']=='full' for c in records), center2048=sum(c['variant']=='center2048' for c in records)),
        runtime=dict(numpy=np.__version__, scipy=scipy.__version__, soundfile=sf.__version__, libsndfile=sf.__libsndfile_version__))
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    (output/'ATTRIBUTION.md').write_text(attributed_text(sources), encoding='utf-8', newline='\n')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', required=True, type=Path)
    p.add_argument('--output', type=Path, default=ROOT/'build/speech-corpus')
    p.add_argument('--manifest', '--source-manifest', dest='source_manifest', type=Path,
                   help='Use a retained source report if source-root/corpus.json is absent')
    p.add_argument('--source-inventory', type=Path, help='Optional original tests/real-speech-sources.json snapshot')
    a = p.parse_args()
    manifest = prepare(a.source_root, a.output, a.source_manifest, a.source_inventory)
    print(json.dumps(dict(**manifest['counts'], output_manifest=str((a.output/'manifest.json').resolve())), ensure_ascii=False))


if __name__ == '__main__':
    main()
