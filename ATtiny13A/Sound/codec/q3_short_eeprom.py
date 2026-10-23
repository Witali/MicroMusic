"""Lossless physical EEPROM layouts for ordinary Q3 pulsebooks.

Logical synthesis remains four signed 16-tap rows. Compile-time widths may
remove only proven zero tails. No quantization or phrase-specific correction.
"""
import numpy as np

WIDTHS = (4, 8, 16)
PACKINGS = ('raw', 'nibble')


def validate_book(book, width):
    values = np.asarray(book)
    if width not in WIDTHS:
        raise ValueError('Pulse width must be 4, 8 or 16')
    if (values.shape != (4, 16) or values.dtype.kind not in 'iu'
            or np.any(values < -7) or np.any(values > 7)):
        raise ValueError('Logical pulsebook must be 4x16 signed integers in -7..7')
    if np.any(values[:, width:] != 0):
        raise ValueError('Cannot remove nonzero pulse tails')
    return values.astype(np.int8)


def minimum_width(book):
    values = validate_book(book, 16)
    return next(width for width in WIDTHS if not np.any(values[:, width:]))


def encode_book(book, width, packing):
    values = validate_book(book, width)[:, :width].reshape(-1).astype(np.int16)
    if packing == 'raw':
        return (values*8).astype(np.int8).tobytes()
    if packing != 'nibble':
        raise ValueError('Packing must be raw or nibble')
    nibbles = values & 15
    return (nibbles[::2] | (nibbles[1::2] << 4)).astype(np.uint8).tobytes()


def decode_book(data, width, packing):
    if width not in WIDTHS or packing not in PACKINGS:
        raise ValueError('Invalid pulsebook layout')
    expected = 4*width if packing == 'raw' else 2*width
    if len(data) != expected:
        raise ValueError('Encoded pulsebook has the wrong byte count')
    if packing == 'raw':
        scaled = np.frombuffer(data, np.int8).astype(np.int16)
        if np.any(scaled % 8) or np.any(scaled < -56) or np.any(scaled > 56):
            raise ValueError('Raw taps must be exact signed multiples of eight in -56..56')
        values = scaled//8
    else:
        packed = np.frombuffer(data, np.uint8)
        nibbles = np.empty(4*width, np.int16)
        nibbles[::2], nibbles[1::2] = packed & 15, packed >> 4
        if np.any(nibbles == 8):
            raise ValueError('Nibble -8 is outside the logical tap range')
        values = ((nibbles+8) & 15)-8
    result = np.zeros((4, 16), np.int8)
    result[:, :width] = values.reshape(4, width)
    return result


def split_storage(book, payload, width, packing, prefix=None):
    """EOF stays in Flash; the prefix may split any speech header/packet byte."""
    payload = bytes(payload)
    if not payload:
        raise ValueError('A complete nonempty speech stream is required')
    encoded = encode_book(book, width, packing)
    capacity = min(64-len(encoded), len(payload))
    if prefix is None:
        prefix = capacity
    if isinstance(prefix, bool) or not isinstance(prefix, int) or not 0 <= prefix <= capacity:
        raise ValueError('Speech prefix exceeds free EEPROM or the complete input stream')
    eeprom = encoded+payload[:prefix]
    result = dict(width=width, packing=packing, book_bytes=len(encoded),
        prefix_bytes=prefix, prefix_start=len(encoded), prefix_end=len(encoded)+prefix,
        free_eeprom_bytes=64-len(eeprom),
        eeprom=eeprom+b'\xff'*(64-len(eeprom)), flash_suffix=payload[prefix:])
    assert result['eeprom'][len(encoded):len(encoded)+prefix]+result['flash_suffix'] == payload
    return result


def code_bytes(width, packing, prefix_bytes):
    if width not in WIDTHS or packing not in PACKINGS:
        raise ValueError('Invalid pulsebook layout')
    raw_shift = {4:2, 8:1, 16:0}[width]
    lookup_extra_words = raw_shift if packing == 'raw' else raw_shift+6
    return 368+lookup_extra_words*2+(26 if prefix_bytes else 0)


def candidates(book, payload):
    for width in WIDTHS:
        try:
            validate_book(book, width)
        except ValueError:
            continue
        for packing in PACKINGS:
            maximum = split_storage(book, payload, width, packing)['prefix_bytes']
            for prefix in sorted({0, maximum}):
                layout = split_storage(book, payload, width, packing, prefix)
                code = code_bytes(width, packing, prefix)
                flash = (code+len(layout['flash_suffix'])+2) & ~1
                yield dict(layout, code_bytes=code, flash_bytes=flash,
                    maximum_stream_bytes=1024-code-1+prefix)
