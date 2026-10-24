"""Automatic arbitrary-clip initialization for the existing tiny integer decoder.

The reference is used only by the offline encoder. The output is an ordinary
period-fixed-v1 model, with no reference-dependent decoder state or side data.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import subprocess

import numpy as np

from fixed_period import gain_sample, integer_noise, validate
from period_wave import encode_model, train_book
from tiny_period import pack_tiny, unpack_tiny


def pad_reference(audio):
    """Preserve every input sample and add only the final partial-block padding."""
    audio = np.asarray(audio, dtype=np.float64)
    if audio.ndim != 1 or len(audio) < 3072 or not np.all(np.isfinite(audio)):
        raise ValueError('Expected finite mono audio of at least 3072 samples')
    padded = (len(audio)+63)//64*64
    if padded > 1023*64:
        raise ValueError('Tiny decoder supports at most 1023 complete blocks')
    if np.max(abs(audio)) > 1:
        raise ValueError('Audio must be normalized to the signed PCM range')
    return np.pad(audio, (0, padded-len(audio)))


def analyze_reference(audio, *, starts=4, seed=23120, pitch_mode='legacy'):
    if starts < 1:
        raise ValueError('Dictionary training starts must be positive')
    reference = pad_reference(audio)
    base, analysis = encode_model(reference, seed=seed, starts=starts, pitch_mode=pitch_mode)
    return reference, base, analysis


def initialize_model(reference, base, analysis, words, *, starts=4, seed=23120):
    """Fit one of four small dictionaries, gains and white-noise amplitudes.

    Gains are chosen from the exact integer power-of-two modes. White residual
    power uses the actual deterministic integer noise source. In unvoiced
    frames the periodic base is muted; no voiced/unvoiced decoder branch is
    needed. No phoneme, time interval or speaker frequency is hard coded.
    """
    if words not in (1, 2, 4, 8):
        raise ValueError('Expected a 1, 2, 4 or 8 word dictionary')
    shapes = np.asarray(analysis['shapes'])
    voiced = np.asarray(analysis['f0']) > 0
    book = train_book(shapes, voiced, starts=starts, seed=seed, count=words)
    gains = np.asarray((0, 1, 2, 3, 4, 5, 7))
    # Lookup arithmetic at nibble points is exact, before interpolation.
    vectors = np.asarray([[gain_sample(int(v)*16, int(g)) for v in word]
                          for word in book for g in gains], dtype=float)/128
    distance = np.sum((shapes[:, None, :]-vectors[None, :, :])**2, axis=2)
    choices = np.argmin(distance, axis=1)
    filters = [[0]*8 for _ in range(3)]
    noise = integer_noise(len(reference), 0xace1, np.asarray(filters))[0]/128
    frames = []
    for i, (pitch, _, _, _) in enumerate(base['frames']):
        index, gain = int(choices[i]//len(gains)), int(gains[choices[i] % len(gains)])
        start, stop = i*64, (i+1)*64
        if not voiced[i]:
            gain = 0
        periodic_power = float(np.mean(vectors[index*len(gains)+int(np.flatnonzero(gains==gain)[0])]**2))
        target_power = float(np.mean(reference[start:stop]**2))
        unexplained = max(0., target_power-periodic_power)
        unit_power = max(float(np.mean(noise[start:stop]**2)), 1e-12)
        residual = int(np.clip(round(64*np.sqrt(unexplained/unit_power)), 0, 15))
        frames.append([int(pitch), 128 | gain << 4 | (index if gain else 0), residual])
    model = dict(schema='period-fixed-v1', sample_rate=7500, samples=len(reference), hop=64,
                 phase_bits=4, dc_block_shift=7, initial_phase_u16=base['initial_phase_u16'],
                 noise_seed_u16=0xace1, codebook=book.astype(int).tolist()+[[0]*32 for _ in range(16-words)],
                 noise_filters=filters, frames=frames)
    validate(model)
    return model


def simplify_regions(model, width, *, preserve_phase=True):
    """Hold gain, wave and residual over regions; optionally preserve phase sum.

    A held pitch is the nearest regional mean. The phase-preserving version
    distributes the integer remainder at the region end. Both are automatic
    rate/quality candidates, evaluated against the complete reference.
    """
    if width < 1:
        raise ValueError('Region width must be positive')
    result = deepcopy(model)
    for start in range(0, len(result['frames']), width):
        frames = result['frames'][start:start+width]
        total = sum(frame[0] for frame in frames)
        pitch = total//len(frames) if preserve_phase else int(round(total/len(frames)))
        remainder = total-pitch*len(frames) if preserve_phase else 0
        gains = [(frame[1] >> 4) & 7 for frame in frames]
        gain = int(np.median(gains))
        if gain == 6:
            gain = 5
        audible = [frame[1] & 15 for frame in frames if frame[1] & 112]
        index = max(set(audible), key=lambda value:(audible.count(value), -value)) if audible else 0
        residual = int(round(float(np.mean([frame[2] for frame in frames]))))
        for offset, frame in enumerate(frames):
            frame[:] = [pitch+int(offset >= len(frames)-remainder),
                        128 | gain << 4 | (index if gain else 0), residual]
    return result


def attenuate(model):
    """One decoder-native gain/noise reduction step, without changing timing."""
    result = deepcopy(model)
    for frame in result['frames']:
        gain = (frame[1] >> 4) & 7
        gain = 5 if gain == 7 else max(0, gain-1)
        frame[1] = 128 | gain << 4 | ((frame[1] & 15) if gain else 0)
        frame[2] = frame[2]*3//4
    return result


def measure_code(model, output, avr_bin):
    """Measure the actual one-shot assembler specialization without linking.

    This deliberately measures .o symbols; a model can be oversized during
    rate search. The normal firmware builder still performs the final link,
    strict limits and three-engine cycle-accurate verification.
    """
    output, avr_bin = Path(output), Path(avr_bin)
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[3]
    template = root/'ATtiny13A/Sound/codec/tiny/firmware.S'
    packed = pack_tiny(model)
    (output/'model-flash.bin').write_bytes(packed['flash_data'])
    constants = dict(packed['constants'], PLAY_ONCE=1)
    (output/'config.inc').write_text(''.join(f'.set {key},{value}\n' for key,value in constants.items()), encoding='ascii')
    (output/'firmware.S').write_text(template.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    import os
    suffix = '.exe' if os.name == 'nt' else ''
    def run(name, args):
        command = [str(avr_bin/(name+suffix)), *args]
        done = subprocess.run(command, cwd=output, capture_output=True, text=True)
        if done.returncode:
            raise RuntimeError(done.stdout+done.stderr)
        return done.stdout
    compiler = run('avr-gcc', ['--version']).splitlines()[0]
    run('avr-gcc', ['-mmcu=attiny13', '-nostdlib', '-x', 'assembler', '-c', 'firmware.S', '-o', 'firmware.o'])
    symbols = run('avr-nm', ['-n', 'firmware.o'])
    code = next(int(row.split()[0],16) for row in symbols.splitlines() if row.split()[-1:] == ['wave_data'])
    return dict(code_bytes=code, flash_data_budget=1024-code, compiler=compiler,
                compile_features=constants, playback_mode='once')


def load_tiny_search():
    """Reuse the tested reduced-dictionary exact decoder search implementation."""
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location('train_tiny_speech', root/'tools/train-tiny-speech.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TinySearch


def lossless_roundtrip(model):
    from fixed_period import decode_fixed
    packed = pack_tiny(model)
    if not np.array_equal(decode_fixed(model), decode_fixed(unpack_tiny(packed))):
        raise AssertionError('Tiny Flash/EEPROM packing changed synthesized PCM')
    return packed
