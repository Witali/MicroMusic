"""Measure the published firmware gain against its unscaled source and original."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from pystoi import stoi
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from fixed_period import decode_fixed
from hq4_core import decode, unpack_stream
from hq4_speech_search import deterministic_estoi
from output_level import scale_pcm, describe_level


def measure():
    catalog = json.loads((ROOT/'web-player/hq4-firmware.json').read_text(encoding='utf-8'))
    results = []
    sha = lambda data: hashlib.sha256(data).hexdigest()
    for entry in catalog['entries']:
        clip = entry['audioReferenceId']
        if entry['codec'] == 'tiny-period':
            model = ROOT/'ATtiny13A/Sound/research/tiny-speech'/clip/'model.json'
            before = decode_fixed(json.loads(model.read_text(encoding='utf-8')))
        else:
            frames, durations = unpack_stream((ROOT/'ATtiny13A/Sound/codec/release'/clip/'speech.hq').read_bytes())
            before = decode(frames, durations, 0)
        level = entry['outputLevel']
        feedback = level['rounding'] == 'error-feedback'
        after = scale_pcm(before, level['numerator'], level['shift'], feedback)
        if describe_level(before, level['numerator'], level['shift'], feedback) != level:
            raise ValueError('Catalog output gain does not match exact PCM: '+clip)
        report_path = (ROOT/'web-player'/entry['verification']).resolve()
        report = json.loads(report_path.read_text(encoding='utf-8'))
        verification = report['verification']
        expected = np.r_[after, np.full(len(after)*2, 128, np.uint8)]
        if (not verification['pass'] or sha(expected.tobytes()) != verification['actualPcmSha256']
                or report['imageSha256'] != entry['flashSha256'] or report['flashBytes'] > 1024
                or verification['lostOverflows'] or verification['missedSamples']):
            raise ValueError('Scaled PCM was not emitted by the full qualified AVR image: '+clip)
        reference_path = ROOT/'web-player'/entry['originalAudioUrl']
        if sha(reference_path.read_bytes()) != entry['originalAudioSha256']:
            raise ValueError('Original hash differs: '+clip)
        reference, rate = sf.read(reference_path)
        objective = SpectralObjective(reference, rate)
        def metrics(pcm):
            audio = (pcm.astype(float)-128)/128
            return dict(stoi=float(stoi(reference, audio, rate)),
                        estoi=float(deterministic_estoi(reference, audio, rate)),
                        **objective.spectrum(audio))
        old, new = metrics(before), metrics(after)
        error = (after.astype(float)-128)-(before.astype(float)-128)*level['gain']
        if np.max(abs(error)) >= 1 or new['stoi'] < old['stoi']-.002:
            raise ValueError('Output gain changed the waveform or speech quality: '+clip)
        results.append(dict(id=entry['id'], flashBytes=report['flashBytes'],
                            eepromBytes=entry['eepromBytes'], imageSha256=report['imageSha256'],
                            outputLevel=level, beforeMetrics=old, afterMetrics=new,
                            maximumRoundingErrorLsb=float(np.max(abs(error))),
                            maximumCompletionCycles=verification['foregroundTiming']['maximumCompletionCycles'],
                            minimumSP=verification['minimumSP'],
                            fullPhraseAndSilenceVerified=True, hardwareTested=False))
    return dict(schema='micromusic-firmware-output-level-v1',
                scope='Constant gain in the actual speech firmware; no player level matching or clipping.',
                results=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = measure()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps([dict(id=row['id'], flash=row['flashBytes'], peak=row['outputLevel']['after']['peak'],
                           stoi=row['afterMetrics']['stoi'], cycles=row['maximumCompletionCycles'])
                      for row in report['results']]))
