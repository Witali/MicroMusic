"""Prepare fixed local audiobook excerpts before any encoder measurements.

All titles, source paths, audio fingerprints and payloads remain under build/.
Only anonymous counts are printed. Originals are read-only.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import unicodedata
import wave

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
EXTENSIONS = {'.mp3', '.m4a', '.m4b', '.wav', '.flac', '.ogg', '.opus', '.aac'}
RATE, SAMPLES, START, SEED = 8000, 160000, 120, 20261126


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def normalized_title(title):
    title = unicodedata.normalize('NFKC', title).casefold()
    title = re.sub(r'\b(?:глава|часть|части|том|part|chapter)\s*(?:\d+|[ivxlcdm]+)\b', ' ', title)
    return ''.join(c if c.isalnum() else ' ' for c in title).split()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    output.relative_to((REPO / 'build').resolve())
    if output.exists() or output == (REPO / 'build').resolve():
        raise ValueError('Use a fresh dedicated ignored output directory')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('Existing ffmpeg and ffprobe are required')
    files = sorted((p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS),
                   key=lambda p: p.relative_to(source).as_posix().casefold())
    output.mkdir(parents=True)
    records = []
    for ordinal, path in enumerate(files):
        info = subprocess.run([ffprobe, '-v', 'error', '-show_format', '-show_streams',
                               '-of', 'json', str(path)], capture_output=True, text=True, encoding='utf-8')
        if info.returncode:
            (output / 'probe-error-private.log').write_text(info.stderr, encoding='utf-8')
            raise RuntimeError('A source probe failed; details remain private')
        probe = json.loads(info.stdout)
        if float(probe['format'].get('duration', 0)) < START + 20:
            continue
        folder = output / ('candidate-%03d' % ordinal)
        folder.mkdir()
        before = path.stat()
        source_sha = sha(path)
        target = folder / 'reference.pcm16'
        command = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-n',
                   '-ss', str(START), '-i', str(path), '-map', '0:a:0', '-t', '20',
                   '-vn', '-sn', '-dn', '-ac', '1', '-ar', str(RATE),
                   '-c:a', 'pcm_s16le', '-f', 's16le', str(target)]
        result = subprocess.run(command, capture_output=True)
        (folder / 'ffmpeg-private.log').write_bytes(result.stderr)
        if result.returncode or target.stat().st_size != SAMPLES * 2:
            raise RuntimeError('A source did not produce exactly twenty seconds')
        if (before.st_size, before.st_mtime_ns) != (path.stat().st_size, path.stat().st_mtime_ns):
            raise RuntimeError('Original media changed while preparing it')
        payload = target.read_bytes()
        with wave.open(str(folder / 'reference.wav'), 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE); wav.writeframes(payload)
        title = probe['format'].get('tags', {}).get('title', path.stem)
        title_key = ' '.join(normalized_title(title))
        row = dict(source_ordinal=ordinal, source_file=str(path), source_sha256=source_sha,
                   source_bytes=before.st_size, source_mtime_ns=before.st_mtime_ns,
                   title=title, normalized_title=title_key,
                   category=str(path.parent.relative_to(source)), probe=probe,
                   target_file=target.relative_to(output).as_posix(), target_sha256=sha(target),
                   samples=SAMPLES, rate=RATE, start_seconds=START, seconds=20,
                   level_policy='preserve; no fitted gain, normalization, silence trim or alignment',
                   command=command)
        records.append(row)
        write(folder / 'source-private.json', row)
        print('Prepared candidate', ordinal, flush=True)
    # Source-only duplicate removal; keep the first exact prepared waveform.
    selected, excluded, seen = [], [], set()
    for row in records:
        if row['target_sha256'] in seen:
            excluded.append(dict(source_ordinal=row['source_ordinal'], reason='exact prepared PCM duplicate'))
        elif len(selected) < 20:
            selected.append(row); seen.add(row['target_sha256'])
        else:
            excluded.append(dict(source_ordinal=row['source_ordinal'], reason='after fixed first20 distinct waveforms'))
    if len(selected) != 20:
        write(output / 'insufficient-private.json', dict(candidates=records, excluded=excluded))
        raise RuntimeError('Fewer than twenty distinct source-only excerpts are available')
    # Group exact original identity and normalized metadata-title aliases.
    parent = list(range(20))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, a in enumerate(selected):
        for j, b in enumerate(selected[:i]):
            if a['source_sha256'] == b['source_sha256'] or a['normalized_title'] == b['normalized_title']:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(20):
        groups.setdefault(find(i), []).append(i)
    group_rows = list(groups.values()); random.Random(SEED).shuffle(group_rows)
    categories = sorted({r['category'] for r in selected})
    # Deterministic group-level subset, preferring category-balanced eight.
    states = {(0,) * (len(categories) + 1): ()}
    for gi, indices in enumerate(group_rows):
        counts = tuple(sum(selected[i]['category'] == c for i in indices) for c in categories)
        for state, chosen in list(states.items()):
            nxt = (state[0] + len(indices), *(state[k + 1] + counts[k] for k in range(len(categories))))
            if nxt[0] <= 8:
                states.setdefault(nxt, chosen + (gi,))
    options = [(sum(abs(s[k + 1] - 8 / len(categories)) for k in range(len(categories))), chosen)
               for s, chosen in states.items() if s[0] == 8]
    if not options:
        raise RuntimeError('Metadata groups cannot make the fixed12/8 split')
    heldout_groups = set(min(options)[1])
    for gi, indices in enumerate(group_rows):
        for i in indices:
            selected[i].update(ordinal=i, source_group='group-%02d' % gi,
                               split='heldout' if gi in heldout_groups else 'development')
    manifest = dict(schema='lpx-audiobook-twenty-second-sources-private-v1',
                    prepared_before_encoding=True, sources=selected, excluded=excluded,
                    candidate_count=len(records), seed=SEED,
                    normalization='NFKC/casefold; remove numbered chapter/part markers; alphanumeric whitespace',
                    grouping_scope='Original-file/title alias groups only; narrator or underlying-book independence is not established',
                    ffmpeg_version=subprocess.check_output([ffmpeg, '-version'], text=True).splitlines()[0],
                    recipe='Fixed120..140 seconds; first audio stream; mono PCM16/8000; no volume fitting',
                    preparer_sha256=sha(Path(__file__).resolve()))
    write(output / 'sources-private.json', manifest)
    print(json.dumps(dict(status='PREPARED', clips=20, samples_each=SAMPLES,
                          groups=len(groups), split=dict(Counter(r['split'] for r in selected)),
                          category_counts=sorted(Counter(r['category'] for r in selected).values()))), flush=True)


if __name__ == '__main__':
    main()
