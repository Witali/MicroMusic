"""Apply the retained experiment patch to a hash-checked production snapshot.

Production sources are read only. Derived source and provenance stay in build/.
All original project provenance/licensing remains applicable; this patch does
not import third-party implementation or introduce a new license grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
from benchmark_speech_flash import source_hashes
from output_paths import protect_outputs

BASE_COMMIT = '5c7e0592'
BINDING = HERE.parents[1] / 'v5-parameter-costs-2026-10-28/source-runtime.json'
PATCH = HERE / 'decoder-v6-scale-repeat-v1.patch'
sha = lambda data: hashlib.sha256(data).hexdigest()


def apply_patch(text, patch):
    """Strict one-file unified patch, no fuzz, shell, or writes to source."""
    lines = text.splitlines(keepends=True)
    changes = patch.splitlines(keepends=True)
    if changes[:2] != ['--- a/Lpx4HybridCore.cpp\n', '+++ b/Lpx4HybridCore.cpp\n']:
        raise ValueError('Unexpected experimental patch target')
    at = 2
    consumed = 0
    output = []
    while at < len(changes):
        match = re.fullmatch(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n', changes[at])
        if not match:
            raise ValueError('Unsupported patch hunk')
        old_start, old_count, new_start, new_count = map(int, match.groups())
        if old_start - 1 < consumed:
            raise ValueError('Overlapping patch hunks')
        output.extend(lines[consumed:old_start - 1])
        consumed = old_start - 1
        if len(output) != new_start - 1:
            raise ValueError('Patch new-line anchor mismatch')
        at += 1
        removed = added = 0
        while at < len(changes) and not changes[at].startswith('@@ '):
            change = changes[at]
            if change[0] in ' -':
                if consumed >= len(lines) or lines[consumed] != change[1:]:
                    raise ValueError('Production patch context changed')
                consumed += 1
                removed += 1
            if change[0] in ' +':
                output.append(change[1:])
                added += 1
            if change[0] not in ' +-':
                raise ValueError('Unsupported patch line')
            at += 1
        if (removed, added) != (old_count, new_count):
            raise ValueError('Patch hunk length mismatch')
    output.extend(lines[consumed:])
    return ''.join(output)


def materialize(output, source=None):
    source = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/src' if source is None else Path(source).resolve()
    expected = json.loads(BINDING.read_text())['decoder_sources']
    if source_hashes(source) != expected:
        raise ValueError('Production source differs from frozen 5c7e0592 snapshot')
    output = Path(output).resolve()
    build = (ROOT / 'build').resolve()
    if not output.is_relative_to(build) or output == build:
        raise ValueError('Derived experiment must stay in ignored build storage')
    targets = [output / 'src' / name for name in expected] + [output / 'provenance.json']
    for target in targets:
        if target.is_symlink() or target.exists() and target.stat().st_nlink > 1:
            raise ValueError('Derived output aliases another file')
    protect_outputs([BINDING, PATCH, Path(__file__), *source.rglob('*')], targets)
    content = {name: (source / name).read_bytes() for name in expected}
    content['Lpx4HybridCore.cpp'] = apply_patch(content['Lpx4HybridCore.cpp'].decode().replace('\r\n', '\n'), PATCH.read_text()).encode()
    derived = {name: sha(value) for name, value in content.items()}
    receipt = {'schema': 'lpx-scale-repeat-derived-source-v1', 'baseline_commit': BASE_COMMIT,
               'production_source_sha256': expected, 'derived_source_sha256': derived,
               'patch_sha256': sha(PATCH.read_bytes()), 'materializer_sha256': sha(Path(__file__).read_bytes()),
               'syntax': 'L4HY version 6, payload selector 1, scale repeat 0 / absolute 1',
               'production_sources_unchanged': True, 'new_persistent_members': 0,
               'provenance': 'Derived only from the original project source above. Original provenance and licensing apply; no third-party source was added.'}
    serialized = json.dumps(receipt, indent=2, allow_nan=False).encode() + b'\n'
    artifacts = {output / 'src' / name: value for name, value in content.items()}
    artifacts[output / 'provenance.json'] = serialized
    for target, value in artifacts.items():
        if target.exists() and target.read_bytes() != value:
            raise ValueError('Immutable derived source/provenance changed; use a fresh output')
    for target, value in artifacts.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(value)
    if source_hashes(source) != expected or source_hashes(output / 'src') != derived:
        raise ValueError('Source changed during materialization')
    return output / 'src', receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    _, receipt = materialize(args.output, args.source)
    print(json.dumps(receipt, indent=2))
