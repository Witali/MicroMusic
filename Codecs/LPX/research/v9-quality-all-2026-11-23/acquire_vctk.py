#!/usr/bin/env python3
"""Bounded lossless VCTK 0.92 acquisition from its official range-capable ZIP.

Audio, archive members, identities, hashes and receipts stay in ignored build/.
This is research acquisition, never an encoder dependency. Requires NumPy,
SciPy and SoundFile. See the official version/terms at the landing page below.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import urllib.request
import wave
import zipfile

for _name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_name] = '1'

LANDING = 'https://datashare.ed.ac.uk/handle/10283/3443'
ARCHIVE = 'https://datashare.ed.ac.uk/bitstreams/535f4286-e54c-4038-838c-a02285e32cb2/download'
SMALL_OFFICIAL_FILES = {
    'official-readme-private.txt': 'https://datashare.ed.ac.uk/bitstreams/bb7edd96-5d96-4c0e-8989-1e45597e7b72/download',
    'official-license-private.txt': 'https://datashare.ed.ac.uk/bitstreams/956a1688-0b59-428c-8a2f-10837433dde3/download',
}
SIZE = 11747302977
ROOT = Path(__file__).resolve().parents[4]
SALT = 'lpx-native-wideband-v1'

def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')

class RangeZip(io.RawIOBase):
    """Never consume a 200 response; count and cache every requested body byte."""
    def __init__(self, out, limit):
        self.out, self.limit, self.position = out, limit, 0
        self.cache = out / 'range-cache'
        self.cache.mkdir(exist_ok=True)
        self.ledger_path = out / 'transfer-private.json'
        self.ledger = json.loads(self.ledger_path.read_text()) if self.ledger_path.exists() else {
            'url': ARCHIVE, 'archive_bytes': SIZE, 'body_bytes': 0, 'requests': []}
        if self.ledger['url'] != ARCHIVE or self.ledger['archive_bytes'] != SIZE:
            raise ValueError('Existing cache belongs to a different archive')
    def tell(self): return self.position
    def seekable(self): return True
    def readable(self): return True
    def seek(self, offset, whence=0):
        self.position = offset + (self.position if whence == 1 else SIZE if whence == 2 else 0)
        if not 0 <= self.position <= SIZE: raise ValueError('Invalid archive seek')
        return self.position
    def read(self, count=-1):
        if count < 0: count = SIZE - self.position
        count = min(count, SIZE - self.position)
        if not count: return b''
        start, stop = self.position, self.position + count - 1
        cached = self.cache / f'{start}-{stop}.bin'
        if cached.exists():
            data = cached.read_bytes()
            if len(data) != count: raise ValueError('Incomplete cached range')
        else:
            if self.ledger['body_bytes'] + count > self.limit:
                raise RuntimeError('Hard transfer budget reached before request')
            request = urllib.request.Request(ARCHIVE, headers={
                'Range': f'bytes={start}-{stop}', 'Accept-Encoding': 'identity',
                'User-Agent': 'MicroMusic-lossless-corpus-audit/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                expected = f'bytes {start}-{stop}/{SIZE}'
                if response.status != 206 or response.headers.get('Content-Range') != expected:
                    raise RuntimeError('Server ignored or mismatched Range; body not consumed')
                if response.headers.get('Content-Length') not in (None, str(count)):
                    raise RuntimeError('Mismatched range length; body not consumed')
                chunks, remaining = [], count
                try:
                    while remaining:
                        chunk = response.read(min(65536, remaining))
                        if not chunk: raise RuntimeError('Truncated range response')
                        chunks.append(chunk); remaining -= len(chunk)
                        self.ledger['body_bytes'] += len(chunk)
                    data = b''.join(chunks)
                    self.ledger['requests'].append({'start': start, 'bytes': count, 'status': 206})
                finally: write_json(self.ledger_path, self.ledger)
            cached.write_bytes(data)
        self.position += count
        return data

def ordered(values, category):
    return sorted(values, key=lambda value: hashlib.sha256(
        (SALT + '|' + category + '|' + value).encode()).digest())

def small_official_files(reader):
    for name, url in SMALL_OFFICIAL_FILES.items():
        path = reader.out / name
        if path.exists(): continue
        if reader.ledger['body_bytes'] + 65537 > reader.limit:
            raise RuntimeError('No remaining metadata transfer budget')
        with urllib.request.urlopen(url, timeout=30) as response:
            length = response.headers.get('Content-Length')
            if response.status != 200 or length is None or int(length) > 65536:
                raise RuntimeError('Unexpected official metadata length; body not consumed')
            raw = response.read(65537)
        reader.ledger['body_bytes'] += len(raw)
        write_json(reader.ledger_path, reader.ledger)
        if len(raw) != int(length): raise RuntimeError('Official metadata was truncated or too large')
        path.write_bytes(raw)

def flac_info(prefix):
    if len(prefix) < 42 or prefix[:4] != b'fLaC' or prefix[4] & 127:
        raise ValueError('Expected FLAC with STREAMINFO first')
    bits = int.from_bytes(prefix[18:26], 'big')
    return bits >> 44, ((bits >> 41) & 7) + 1, ((bits >> 36) & 31) + 1, bits & ((1 << 36) - 1)

def upper_power(pcm, rate):
    import numpy as np
    from scipy.signal import resample_poly
    from math import gcd
    divisor = gcd(rate, 16000)
    samples = resample_poly(pcm.astype(np.float64), 16000 // divisor, rate // divisor)
    samples = np.clip(np.rint(samples), -32768, 32767).astype(np.int16).astype(np.float64)
    window, powers = np.hanning(512), np.zeros(8)
    padded = np.pad(samples, (256, 512))
    weights = np.full(257, 2.); weights[[0, -1]] = 1
    bands = np.minimum(7, np.arange(257) * 16000 // (512 * 1000))
    for at in range(0, len(samples) + 256, 256):
        spectrum = np.abs(np.fft.rfft(padded[at:at + 512] * window)) ** 2 * weights
        powers += np.bincount(bands, weights=spectrum, minlength=8)
    fractions = powers / powers.sum() if powers.sum() else powers
    return fractions.tolist(), bool((fractions[4:] > 1e-4).any())

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--count', type=int, default=24)
    parser.add_argument('--index-only', action='store_true')
    parser.add_argument('--max-mib', type=int, default=63,
        help='Hard response-body limit; 63 leaves room under the 64 MiB study cap')
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if not out.is_relative_to(ROOT / 'build'):
        raise ValueError('Private acquisition must stay under ignored build/')
    if not 1 <= args.count <= 24 or not 1 <= args.max_mib <= 63:
        raise ValueError('Count or transfer bound outside predeclared limits')
    out.mkdir(parents=True, exist_ok=True)
    reader = RangeZip(out, args.max_mib * 1024 * 1024)
    small_official_files(reader)
    with zipfile.ZipFile(reader) as archive:
        names = archive.namelist()
        speakers = {}
        for name in names:
            match = re.search(r'(?:^|/)wav48_silence_trimmed/(p\d+)/(p\d+_\d+_mic1\.flac)$', name)
            if match: speakers.setdefault(match[1], []).append(name)
        metadata_names = [name for name in names if name.lower().endswith(('speaker-info.txt', 'speaker_info.txt'))]
        genders = {}
        for ordinal, name in enumerate(metadata_names):
            raw = archive.read(name)
            (out / f'official-speaker-metadata-{ordinal}-private.txt').write_bytes(raw)
            for line in raw.decode('utf-8', errors='replace').splitlines():
                match = re.match(r'\s*(p\d+)\s+\d+\s+([MF])\b', line)
                if match: genders[match[1]] = match[2]
        for ordinal, name in enumerate(name for name in names
                if name.lower().endswith(('readme.txt', 'license.txt', 'license_text.txt', 'copying'))):
            if archive.getinfo(name).file_size <= 100000:
                (out / f'official-provenance-{ordinal}-private.txt').write_bytes(archive.read(name))
        write_json(out / 'archive-index-private.json', {
            'landing_page': LANDING, 'archive': ARCHIVE, 'entries': names,
            'speaker_gender': genders, 'selection_salt': SALT})
        if args.index_only:
            print(json.dumps({'range_validated': True, 'archive_members': len(names),
                'speakers': len(speakers), 'gender_metadata_available': bool(genders),
                'body_bytes': reader.ledger['body_bytes']})); return
        import numpy as np
        import soundfile as sf
        candidates = ordered(list(speakers), 'speaker')
        if genders:
            groups = [ordered([speaker for speaker in candidates if genders.get(speaker) == gender], 'speaker')
                      for gender in ('F', 'M')]
            candidates = [speaker for pair in zip(*groups) for speaker in pair]
        receipt, cases = [], []
        for speaker in candidates[:48]:
            for member in ordered(speakers[speaker], 'utterance')[:24]:
                with archive.open(member) as item: info = flac_info(item.read(42))
                rate, channels, depth, count = info
                if rate != 48000 or channels != 1 or depth != 16 or not 4 <= count / rate <= 8:
                    continue
                flac = archive.read(member)
                pcm, decoded_rate = sf.read(io.BytesIO(flac), dtype='int16', always_2d=True)
                if decoded_rate != rate or pcm.shape != (count, 1):
                    raise ValueError('Decoded FLAC differs from original STREAMINFO')
                pcm = pcm[:, 0]; fractions, upper = upper_power(pcm, rate)
                if not upper:
                    receipt.append({'member': member, 'decision': 'source-upper-band-ineligible',
                                    'source_band_fractions_16k': fractions})
                    continue
                ordinal = len(cases) + 1
                stem = f'anon-{ordinal:03}'
                (out / f'{stem}.flac').write_bytes(flac)
                path = out / f'{stem}.wav'
                with wave.open(str(path), 'wb') as target:
                    target.setnchannels(1); target.setsampwidth(2); target.setframerate(rate)
                    target.writeframes(pcm.astype('<i2').tobytes())
                detail = {'member': member, 'anonymous_speaker': speaker, 'gender': genders.get(speaker),
                    'original_streaminfo': info, 'source_band_fractions_16k': fractions,
                    'flac_sha256': hashlib.sha256(flac).hexdigest(), 'selection': 'source-only-v1'}
                cases.append({'source': str(path), 'corpus': 'vctk', 'language': 'en',
                    'split': 'tuning' if ordinal <= 4 else 'heldout', 'native_rate': rate,
                    'native_samples': count, 'source_pcm_sha256': hashlib.sha256(pcm.astype('<i2').tobytes()).hexdigest(),
                    'selection_receipt': detail})
                receipt.append({'member': member, 'decision': 'accepted', 'anonymous': stem})
                write_json(out / 'manifest-private.json', {'schema': 'lpx-native-wideband-sources-v1',
                    'cases': cases, 'selection_protocol': 'Distinct speakers, hash-order by fixed salt; alternating official F/M metadata when available; whole 4–8 second 48 kHz PCM16 mono mic1 utterances; source-only >4 kHz power eligibility after direct 16 kHz resampling; first four tuning, rest heldout/reserve.'})
                write_json(out / 'selection-private.json', receipt)
                print(json.dumps({'acquired': ordinal, 'native_rate': rate,
                    'seconds': count / rate, 'upper_source_eligible': True,
                    'body_bytes': reader.ledger['body_bytes']}), flush=True)
                break
            if len(cases) >= args.count: break
        if len(cases) < args.count:
            raise RuntimeError('Bounded deterministic source reserve was insufficient')
        print(json.dumps({'complete': len(cases), 'body_bytes': reader.ledger['body_bytes'],
                          'lossless_originals': True, 'outputs_used_for_selection': False}))

if __name__ == '__main__':
    try: main()
    except Exception as error:
        # Exception values can contain source identities or private local paths.
        print(json.dumps({'failed': type(error).__name__, 'details': 'Private receipts retained; no full archive fallback'}))
        raise SystemExit(1)
