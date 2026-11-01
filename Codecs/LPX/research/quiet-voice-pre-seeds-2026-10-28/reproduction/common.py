"""Shared I/O/source guards for parameterized old-epoch research projections.

The original executed scripts remain in ignored storage. These projections
remove local paths, add output/source guards, and are not byte-identical copies.
No corpus recording, codec stream or waveform fingerprint is distributed here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def parser(description, *, reseed=False):
    result = argparse.ArgumentParser(description=description)
    for name in ('codec-tools', 'voice-tools', 'objective-tools', 'output'):
        result.add_argument('--' + name, type=Path, required=True)
    if reseed:
        result.add_argument('--reseed-tools', type=Path, required=True)
    return result


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def prepare(args, *, reseed=False):
    from types import SimpleNamespace
    record = json.loads((HERE.parent / 'source-runtime.json').read_text())
    expected = record['frozen_source_files']
    for name, item in expected.items():
        folder = (args.voice_tools if name == 'voice_character.py' else
                  args.objective_tools if name == 'speech_voice_objective.py' else args.codec_tools)
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Frozen research source differs: ' + name)
    if reseed:
        item = record['published_reseed_projection_source']
        if hashlib.sha256((args.reseed_tools / 'reseed_speech_excitation.py').read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Expected the published 41f57496 reseed component')
    output = args.output.resolve()
    if output == (ROOT / 'build').resolve() or not output.is_relative_to((ROOT / 'build').resolve()) or output.exists():
        raise ValueError('Use a fresh owned output under this checkout\'s ignored build/')
    sys.path[:0] = [str(args.codec_tools.resolve()), str(args.voice_tools.resolve()),
                   str(args.objective_tools.resolve())]
    if reseed:
        sys.path.insert(3, str(args.reseed_tools.resolve()))
    import numpy as np
    import soundfile as sf
    from batch_decoder import BatchSession
    from benchmark_speech_flash import source_hashes
    import speech_compact as compact
    import speech_v4 as v4
    from standard_metrics import error_metrics, pwm_pcm16, pwm_duties
    from refine_speech_compact import no_regression
    from voice_character import track_pitch, compare_voice
    from speech_voice_objective import VoiceObjective
    if source_hashes(args.codec_tools.resolve().parent / 'src') != record['decoder_sources']:
        raise ValueError('Frozen decoder source differs')
    output.mkdir(parents=True)
    return SimpleNamespace(np=np, sf=sf, BatchSession=BatchSession, compact=compact, v4=v4,
                           metrics=error_metrics, pwm=pwm_pcm16, duties=pwm_duties,
                           floors=no_regression, track_pitch=track_pitch,
                           compare_voice=compare_voice, VoiceObjective=VoiceObjective,
                           output=output)


def reference(ctx, path):
    value, rate = ctx.sf.read(path, dtype='int16')
    if rate != 8000 or value.ndim != 1 or not 1 <= len(value) <= 64000:
        raise ValueError('Expected full mono 8 kHz PCM16, 1..64000 samples')
    return value


def measure(ctx, source, pcm, criterion):
    return dict(metrics={'pcm16': ctx.metrics(source, pcm, True),
                         'pwm8': ctx.metrics(source, ctx.pwm(pcm), True)},
                voice=ctx.compare_voice(source, pcm),
                voice_objective=criterion.components(pcm), voice_score=criterion.score(pcm))


def emit(ctx, label, blob, pcm, source, criterion, decoders):
    if len(pcm) != len(source) or not ctx.np.array_equal(ctx.compact.decode_model(blob), pcm):
        raise AssertionError('Full model/reference geometry mismatch')
    for decoder in decoders:
        ctx.np.testing.assert_array_equal(decoder.decode_one_s16(blob, len(source)), pcm)
        ctx.np.testing.assert_array_equal(decoder.decode_one(blob, len(source)), ctx.duties(pcm))
    (ctx.output / (label + '.l4hy')).write_bytes(blob)
    ctx.sf.write(ctx.output / (label + '.wav'), pcm, 8000, subtype='PCM_16')
    return dict(variant=label, bytes=len(blob), raw_alternative=True, quality_adopted=False,
                common_v5_model_pcm_pwm_exact=True, **measure(ctx, source, pcm, criterion))
