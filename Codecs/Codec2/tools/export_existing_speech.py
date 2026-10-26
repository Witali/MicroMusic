#!/usr/bin/env python3
"""Retain original/upstream/two AVR listening WAVs after all human clips pass."""
import hashlib
import json
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT.parents[1] / 'build/codec2/existing-speech'
OUT = ROOT / 'validation/existing-speech-3200'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    fixture_path = ROOT / 'fixtures/existing-speech.json'
    report_path = ROOT / 'reports/existing-speech.json'
    fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
    report = json.loads(report_path.read_text())
    assert sha(fixture_path.read_bytes()) == report['fixture_sha256']
    execution = report['avr_execution']
    assert execution['complete'] and len(execution['results']) == 8
    assert [(r['profile'], r['name']) for r in execution['results']] == [
        (p, c['id']) for p in ('matrix', 'nopost') for c in fixture['clips']]
    files = []
    for clip in fixture['clips']:
        name = clip['id']
        folder = OUT / name
        source = ROOT / clip['source_8k_wav']
        assert sha(source.read_bytes()) == clip['source_8k_wav_sha256']
        files.append({'path': source.relative_to(OUT).as_posix(), 'kind': 'unencoded_source_8k',
            'wav_sha256': clip['source_8k_wav_sha256'], 'pcm_sha256': clip['input_pcm_sha256']})
        for profile, kind, suffix, wav_name in [
                ('matrix', 'upstream_pf1', 'upstream', 'upstream.wav'),
                ('matrix', 'avr_pf1', 'avr', 'avr-postfilter.wav'),
                ('nopost', 'avr_pf0', 'avr', 'avr-nopost.wav')]:
            record = next(r for r in execution['results'] if r['profile'] == profile and r['name'] == name)
            assert record['completeStream'] and record['frames'] == clip['frames']
            pcm = (BUILD / profile / (name + '.' + suffix + '.pcm')).read_bytes()
            wanted = record['expectedSha256'] if suffix == 'upstream' else record['outputSha256']
            assert sha(pcm) == wanted
            path = folder / wav_name
            with wave.open(str(path), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(pcm)
            files.append({'path': path.relative_to(OUT).as_posix(), 'kind': kind,
                'wav_sha256': sha(path.read_bytes()), 'pcm_sha256': wanted,
                'packet_sha256': record['packetSha256'],
                'decoder_image_sha256': record['binarySha256'] if suffix == 'avr' else report['oracle_binary_sha256']})
    provenance = {'verification': '../../reports/existing-speech.json', 'fixtures': '../../fixtures/existing-speech.json',
        'source_scope': fixture['source_scope'], 'preprocessing': fixture['preprocessing'],
        'output_scope': 'Unnormalized PCM16 mono/8kHz. Original upstream on PC and exact AVR instruction simulation; no analog board recording.',
        'files': files}
    (OUT / 'PROVENANCE.json').write_bytes((json.dumps(provenance, indent=2) + '\n').encode())
    print('Retained 16 listening WAVs: four original human clips, same packets, ordinary and simplified AVR profiles')


if __name__ == '__main__':
    main()
