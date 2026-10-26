#!/usr/bin/env python3
"""Retain WAV examples only from the completed, hash-bound AVR verification."""
import hashlib
import json
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT.parents[1] / 'build/codec2/decoder'
OUT = ROOT / 'validation/full-3200'


def main():
    report = json.loads((ROOT / 'reports/full-decoder.json').read_text(encoding='utf-8'))
    assert report['avr_execution']['complete']
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for record, language in zip(report['avr_execution']['results'], ('english', 'russian')):
        assert record['completeStream']
        for suffix, filename, wanted in (
            ('avr', record['name'] + '.avr.pcm', record['outputSha256']),
            ('upstream', record['name'] + '.upstream.pcm', record['expectedSha256'])):
            pcm = (BUILD / filename).read_bytes()
            assert hashlib.sha256(pcm).hexdigest() == wanted
            path = OUT / f'{language}_{suffix}.wav'
            with wave.open(str(path), 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(pcm)
            results.append({'path': path.name, 'packet_fixture': record['name'], 'frames': record['frames'],
                'pcm_sha256': wanted, 'wav_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    provenance = {'source': 'Synthetic test speech from the user-supplied R3 archive; no new voice recording.',
                  'verification': '../../reports/full-decoder.json',
                  'avr_mcu': 'ATmega1284P instruction simulation; no analog hardware recording.',
                  'files': results}
    (OUT / 'PROVENANCE.json').write_bytes((json.dumps(provenance, indent=2) + '\n').encode('utf-8'))
    print('Retained four unnormalized PCM16/8kHz WAVs from verified outputs')


if __name__ == '__main__':
    main()
