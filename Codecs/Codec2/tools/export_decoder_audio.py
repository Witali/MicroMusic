#!/usr/bin/env python3
"""Retain WAV examples only from the completed, hash-bound AVR verification."""
import argparse
import hashlib
import json
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument('--compact', action='store_true', help='Use the completed ATmega64A compact verification')
    profile.add_argument('--hybrid', action='store_true', help='Use the completed fixed-IFFT hybrid verification')
    profile.add_argument('--postfilter', action='store_true', help='Use the completed integer postfilter power verification')
    profile.add_argument('--spectral', action='store_true', help='Use the completed integer weighted-spectrum verification')
    profile.add_argument('--canonical', action='store_true', help='Use the completed integer main-spectrum and canonical LPC verification')
    profile.add_argument('--matrix', action='store_true', help='Use the completed shared in-place main-spectrum verification')
    profile.add_argument('--nopost', action='store_true', help='Use the experimental LPC-postfilter-off verification; its oracle also has the filter off')
    args = parser.parse_args()
    name = 'nopost' if args.nopost else 'matrix' if args.matrix else 'canonical' if args.canonical else 'spectral' if args.spectral else 'postfilter' if args.postfilter else 'hybrid' if args.hybrid else 'compact' if args.compact else 'full'
    profiles = {'full': ('decoder', 'full-decoder'), 'compact': ('compact', 'compact-decoder'),
                'hybrid': ('hybrid', 'hybrid-decoder'), 'postfilter': ('postfilter', 'postfilter-decoder'),
                'spectral': ('spectral', 'spectral-decoder'), 'canonical': ('canonical', 'canonical-decoder'),
                'matrix': ('matrix', 'matrix-decoder'), 'nopost': ('nopost', 'nopost-decoder')}
    folder, report_name = profiles[name]
    build = ROOT.parents[1] / ('build/codec2/' + folder)
    out = ROOT / ('validation/' + name + '-3200')
    report_path = 'reports/' + report_name + '.json'
    report = json.loads((ROOT / report_path).read_text(encoding='utf-8'))
    assert report['avr_execution']['complete']
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for record, language in zip(report['avr_execution']['results'], ('english', 'russian')):
        assert record['completeStream']
        for suffix, filename, wanted in (
            ('avr', record['name'] + '.avr.pcm', record['outputSha256']),
            ('upstream', record['name'] + '.upstream.pcm', record['expectedSha256'])):
            pcm = (build / filename).read_bytes()
            assert hashlib.sha256(pcm).hexdigest() == wanted
            path = out / f'{language}_{suffix}.wav'
            with wave.open(str(path), 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(pcm)
            results.append({'path': path.name, 'packet_fixture': record['name'], 'frames': record['frames'],
                'pcm_sha256': wanted, 'wav_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    provenance = {'source': 'Synthetic test speech from the user-supplied R3 archive; no new voice recording.',
                  'verification': '../../' + report_path,
                  'avr_mcu': report['avr_execution']['mcu'] + ' instruction simulation; no analog hardware recording.',
                  'files': results}
    if name == 'nopost':
        provenance['decoder_options'] = 'Both AVR and upstream WAVs have the optional LPC postfilter and its bass boost disabled. Subjective quality is unqualified. Default-filter references are in ../matrix-3200/.'
    (out / 'PROVENANCE.json').write_bytes((json.dumps(provenance, indent=2) + '\n').encode('utf-8'))
    print('Retained four unnormalized PCM16/8kHz WAVs from verified outputs')


if __name__ == '__main__':
    main()
