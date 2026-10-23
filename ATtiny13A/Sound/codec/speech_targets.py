"""Explicit output profiles for trained speech models.

Training can call ``decode_for_profile`` so its objective hears the target's
arithmetic. Exporting data does not establish firmware size, RAM or timing.
"""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import wave

import numpy as np


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class OutputProfile:
    name: str
    target: str
    arithmetic: str
    sample_rate: int = 7500
    flash_bytes: int | None = None
    sram_bytes: int | None = None
    cpu_hz: int | None = None
    adapter: str | None = None


def resolve_profile(target='pc', arithmetic=None, mcu=None, custom_profile=None):
    """Resolve a built-in profile, optionally overriding documented limits.

    Custom profile JSON is data, not a shell command. Its adapter names a Python
    script implementing the same --model/--output interface as the AVR builder.
    """
    if target not in ('pc', 'avr', 'mcu'):
        raise ValueError('Target must be pc, avr or mcu')
    arithmetic = arithmetic or ('float' if target == 'pc' else 'fixed')
    if arithmetic not in ('float', 'fixed') or (target != 'pc' and arithmetic != 'fixed'):
        raise ValueError('AVR and MCU output require fixed arithmetic')
    if target == 'avr' and mcu not in (None, 'attiny13', 'attiny13a'):
        raise ValueError('Only attiny13/attiny13a has an AVR adapter; use mcu with a custom profile')
    if target == 'pc' and mcu is not None:
        raise ValueError('--mcu only applies to MCU targets')
    if target == 'avr':
        profile = OutputProfile('attiny13a-fixed', target, arithmetic, flash_bytes=1024,
                                sram_bytes=64, cpu_hz=9600000,
                                adapter='tools/build-fixed-period.py')
    else:
        name = f'{mcu or "generic-mcu"}-fixed' if target == 'mcu' else f'pc-{arithmetic}'
        profile = OutputProfile(name, target, arithmetic)
    if custom_profile is not None:
        if isinstance(custom_profile, (str, Path)):
            custom_profile = json.loads(Path(custom_profile).read_text(encoding='utf-8'))
        values = dict(custom_profile)
        if values.pop('schema', None) != 'speech-output-profile-v1':
            raise ValueError('Expected speech-output-profile-v1 profile')
        allowed = {'name', 'sample_rate', 'flash_bytes', 'sram_bytes', 'cpu_hz', 'adapter'}
        if set(values)-allowed:
            raise ValueError('Unknown custom profile fields: '+', '.join(sorted(set(values)-allowed)))
        profile = replace(profile, **values)
    if not isinstance(profile.name, str) or not profile.name.strip():
        raise ValueError('Profile name must be nonempty')
    if profile.sample_rate != 7500:
        raise ValueError('This codec currently supports 7500 Hz only; export never resamples')
    for field in ('flash_bytes', 'sram_bytes', 'cpu_hz'):
        value = getattr(profile, field)
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError(field+' must be a positive integer or null')
    if profile.adapter is not None and (not isinstance(profile.adapter, str) or not profile.adapter):
        raise ValueError('Adapter must be a Python script path or null')
    if profile.target == 'pc' and profile.adapter is not None:
        raise ValueError('PC profiles do not use a firmware adapter')
    return profile


def prepare_model(model, profile):
    """Convert arithmetic explicitly; changing target never changes sample rate."""
    schema = model.get('schema')
    if profile.arithmetic == 'float':
        if schema != 'period-colored-v1':
            raise ValueError('Float output expects period-colored-v1; fixed models have no inverse conversion')
        from colored_period import validate
        validate(model)
        return model
    from fixed_period import from_colored, validate
    if schema == 'period-colored-v1':
        model = from_colored(model)
    elif schema != 'period-fixed-v1':
        raise ValueError('Fixed output expects period-colored-v1 or period-fixed-v1')
    validate(model)
    return model


def decode_for_profile(model, profile):
    """Return normalized PCM for an encoder objective, using target arithmetic.

    Fixed output is signed DAC amplitude divided by 128, including quantization
    and clipping. This function does not normalize volume or remove DC.
    """
    prepared = prepare_model(model, profile)
    if profile.arithmetic == 'float':
        from colored_period import decode_colored
        return decode_colored(prepared)
    from fixed_period import decode_fixed
    return (decode_fixed(prepared).astype(np.float64)-128)/128


def c_data_header(payload, symbol='speech_data'):
    """A portable packed-data header; AVR reads it through pgm_read_byte."""
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', symbol):
        raise ValueError('C symbol must be an identifier')
    guard = symbol.upper()+'_H'
    lines = [f'#ifndef {guard}', f'#define {guard}', '#include <stdint.h>',
             '#ifdef __AVR__', '#include <avr/pgmspace.h>', '#define SPEECH_STORAGE PROGMEM',
             '#else', '#define SPEECH_STORAGE', '#endif', '',
             '/* Packed period-fixed-v1 data; this header contains no decoder. */',
             f'static const uint8_t {symbol}[] SPEECH_STORAGE = {{']
    for start in range(0, len(payload), 16):
        lines.append('    '+', '.join(f'0x{value:02x}' for value in payload[start:start+16])+',')
    lines += ['};', f'#define {symbol.upper()}_BYTES {len(payload)}u',
              '#undef SPEECH_STORAGE', f'#endif /* {guard} */', '']
    return '\n'.join(lines)


def _json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8')


def _write(path, content):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)


def _wav(path, audio, *, fixed):
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setframerate(7500)
        handle.setsampwidth(1 if fixed else 2)
        pcm = audio.astype(np.uint8).tobytes() if fixed else np.rint(
            np.clip(audio, -1, 32767/32768)*32768).astype('<i2').tobytes()
        handle.writeframes(pcm)


def export_model(model, output, profile, *, build=False, adapter_options=(), symbol='speech_data'):
    """Export model, packed data and exact arithmetic preview plus a manifest.

    MCU exports add a C header. --build calls an explicit Python adapter; the
    adapter must supply a build.json report with measured validation results.
    Unavailable adapters are errors, never successful firmware placeholders.
    """
    if build and (profile.target == 'pc' or profile.adapter is None):
        raise ValueError('This profile has no firmware adapter')
    prepared = prepare_model(model, profile)
    fixed = profile.arithmetic == 'fixed'
    if fixed:
        from fixed_period import decode_fixed, pack_fixed, unpack_fixed
        payload = pack_fixed(prepared)
        restored = unpack_fixed(payload)
        audio = decode_fixed(prepared)
        if not np.array_equal(audio, decode_fixed(restored)):
            raise AssertionError('Packed fixed data changes synthesized PCM')
    else:
        from colored_period import decode_colored, pack_colored, unpack_colored
        payload = pack_colored(prepared)
        restored = unpack_colored(payload)
        audio = decode_colored(prepared)
        if not np.array_equal(audio, decode_colored(restored)):
            raise AssertionError('Packed float data changes synthesized PCM')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    _write(output/'model.json', _json_bytes(prepared))
    _write(output/'speech.bin', payload)
    raw = audio.astype(np.uint8).tobytes() if fixed else audio.astype('<f4').tobytes()
    raw_name = 'speech.u8' if fixed else 'speech.f32'
    _write(output/raw_name, raw)
    _wav(output/'speech.wav', audio, fixed=fixed)
    names = ['model.json', 'speech.bin', raw_name, 'speech.wav']
    if profile.target != 'pc':
        _write(output/'speech_data.h', c_data_header(payload, symbol).encode('ascii'))
        names.append('speech_data.h')
    samples = prepared['samples'] if fixed else prepared['base']['samples']
    normalized = (audio.astype(np.float64)-128)/128 if fixed else audio
    manifest = dict(schema='speech-export-v1', profile=asdict(profile), model_schema=prepared['schema'],
                    input_model_sha256=sha256(_json_bytes(model)).hexdigest(),
                    converted_from_float=fixed and model['schema'] == 'period-colored-v1',
                    conversion_note='Float-to-fixed conversion requires coefficient retuning against the fixed decoder.'
                                    if fixed and model['schema'] == 'period-colored-v1' else None,
                    samples=samples, sample_rate=7500, data_bytes=len(payload),
                    pcm=dict(encoding='unsigned-8' if fixed else 'float32-le',
                             raw_file=raw_name, centered_mean=float(np.mean(normalized)),
                             peak=float(np.max(abs(normalized)))),
                    validation=dict(packed_roundtrip_pcm_equal=True, firmware='not_built',
                                    flash_data_fits=None if profile.flash_bytes is None else len(payload)<=profile.flash_bytes,
                                    total_flash_bytes=None, sram_bytes=None, cycles_per_sample=None,
                                    timing_verified=False),
                    artifacts={name:dict(bytes=(output/name).stat().st_size,
                                         sha256=sha256((output/name).read_bytes()).hexdigest()) for name in names})
    _write(output/'manifest.json', _json_bytes(manifest))
    if build:
        adapter = Path(profile.adapter)
        if not adapter.is_absolute():
            adapter = ROOT/adapter
        if not adapter.is_file():
            raise FileNotFoundError('Firmware adapter is unavailable: '+str(adapter))
        command = [sys.executable, str(adapter), '--model', str((output/'model.json').resolve()),
                   '--output', str((output/'firmware').resolve()), *map(str, adapter_options)]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        _write(output/'build.log', (result.stdout+result.stderr).encode('utf-8'))
        manifest['validation']['firmware'] = 'build_failed' if result.returncode else 'built_unverified'
        manifest['adapter_returncode'] = result.returncode
        report = output/'firmware/build.json'
        if result.returncode == 0 and report.is_file():
            manifest['adapter_report'] = json.loads(report.read_text(encoding='utf-8'))
        _write(output/'manifest.json', _json_bytes(manifest))
        if result.returncode:
            raise RuntimeError('Firmware adapter failed; see '+str(output/'build.log'))
    return manifest
