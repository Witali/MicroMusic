"""Experimental long-frame HQ4 stream; existing HQ4 files are unchanged.

Extended pitch headers use bits 5:0 as duration/64. Zero aliases 256 samples
for compatibility with the old extended header. 0xff remains the EOF marker,
so 3968 is the maximum duration. The synthesizer arithmetic is unchanged.
"""
import numpy as np

DECODER_BYTES = 442
STREAM_BUDGET = 1024-DECODER_BYTES-1
MAX_FRAME_SAMPLES = 3968


def validate(frames, durations):
    f, d = np.asarray(frames), np.asarray(durations)
    if (f.ndim != 2 or f.shape[1] != 6 or not len(f)
            or d.shape != (len(f),) or not np.all(np.isfinite(f))
            or not np.all(np.isfinite(d)) or not np.all(f == np.floor(f))
            or not np.all(d == np.floor(d)) or np.any(f < 0) or np.any(f > 255)
            or np.any(f[:, 0] > 126) or np.any(f[:, 1] > 63)
            or np.any(d < 64) or np.any(d > MAX_FRAME_SAMPLES) or np.any(d % 64)):
        raise ValueError('Expected Nx6 HQ4 bytes and matching 64..3968-sample durations in steps of 64')
    return f.astype(np.uint8), d.astype(np.uint16)


def pack_stream(frames, durations):
    f, d = validate(frames, durations)
    result = bytearray()
    old = None
    for row, duration in zip(f, d):
        pitch, excitation, *coefficients = map(int, row)
        duration = int(duration)
        if pitch <= 63 and duration in (64, 128, 256):
            result.append((duration & 0xc0) | pitch)
        else:
            # The zero alias retains legacy pitch>63, duration=256 bytes.
            code = 0 if duration == 256 else duration//64
            result.extend((0xc0 | code, pitch))
        if old is None or (old[:2] != coefficients[:2] and old[2:] != coefficients[2:]):
            mode = 0
        elif old == coefficients:
            mode = 1
        elif old[:2] != coefficients[:2]:
            mode = 2
        else:
            mode = 3
        result.append((mode << 6) | excitation)
        if mode == 0:
            result.extend(coefficients)
        elif mode == 2:
            result.extend(coefficients[:2])
        elif mode == 3:
            result.extend(coefficients[2:])
        old = coefficients
    return bytes(result)


def unpack_stream(payload):
    """Strictly read a stream without EOF; the assembler adds the sentinel."""
    data = bytes(payload)
    offset, coefficients, frames, durations = 0, [0]*4, [], []

    def take():
        nonlocal offset
        if offset == len(data):
            raise ValueError('Truncated long HQ4 frame')
        value = data[offset]
        offset += 1
        return value

    while offset < len(data):
        header = take()
        if header == 255:
            raise ValueError('Input must omit the EOF marker')
        if header & 0xc0 == 0xc0:
            duration = (header & 63)*64 or 256
            pitch = take()
        else:
            duration = header & 0xc0 or 256
            pitch = header & 63
        excitation = take()
        mode = excitation >> 6
        if not frames and mode:
            raise ValueError('First frame must initialize all four coefficient bytes')
        if mode == 0:
            coefficients = [take() for _ in range(4)]
        elif mode == 2:
            coefficients[:2] = [take(), take()]
        elif mode == 3:
            coefficients[2:] = [take(), take()]
        frames.append([pitch, excitation & 63, *coefficients])
        durations.append(duration)
    return validate(frames, durations)
