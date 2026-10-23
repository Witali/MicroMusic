"""Optional lossless storage for LPX3 v1; synthesis and quantization are unchanged.

The smallest actual representation wins: original LPX3, DEFLATE of the packed
container, or DEFLATE after reversible excitation/scale byte rearrangement.
This is a PC container experiment, not an AVR decompressor.
"""
import struct
import zlib

LPX = struct.Struct('<4sBBHIIHHI')
WRAP = struct.Struct('<4sBIII')  # magic, transform, raw bytes, inflated bytes, CRC32
MAX_BYTES = 64*1024*1024


def header(data):
    if len(data) < LPX.size:
        raise ValueError('Truncated LPX3 header')
    magic, version, bits, rate, samples, base, block, brightness, blocks = LPX.unpack_from(data)
    if (magic != b'LPX3' or version != 1 or bits not in (2, 3, 4) or not 4000 <= rate <= 96000
            or not 0 < samples <= MAX_BYTES or not 36 <= base <= MAX_BYTES
            or not 20 <= block <= 2048 or brightness > 700 or blocks != (samples+block-1)//block):
        raise ValueError('Invalid LPX3 descriptor')
    prefix = LPX.size+base+blocks
    packed = (samples*bits+7)//8
    if prefix+packed > MAX_BYTES or prefix+samples+1 > MAX_BYTES:
        raise ValueError('LPX3 exceeds the bounded storage limit')
    return bits, samples, base, blocks, prefix, packed


def validate(data):
    info = header(data)
    bits, samples, base, blocks, prefix, packed = info
    if len(data) != prefix+packed:
        raise ValueError('Truncated or trailing LPX3 bytes')
    if data[24:28] != b'LPC2' or data[28] not in (1, 2):
        raise ValueError('Missing embedded LPC2 descriptor')
    if struct.unpack_from('<H', data, 30)[0] != struct.unpack_from('<H', data, 6)[0]:
        raise ValueError('Embedded sample rate differs')
    if struct.unpack_from('<I', data, 40)[0] != samples:
        raise ValueError('Embedded sample count differs')
    return info


def unpack_codes(data, bits, samples):
    result = bytearray()
    accumulator = count = 0
    mask = (1 << bits)-1
    for value in data:
        accumulator |= value << count
        count += 8
        while count >= bits and len(result) < samples:
            result.append(accumulator & mask)
            accumulator >>= bits
            count -= bits
    if len(result) != samples:
        raise ValueError('Truncated excitation')
    return result


def pack_codes(codes, bits):
    accumulator = count = 0
    result = bytearray()
    for value in codes:
        if not 0 <= value < 1 << bits:
            raise ValueError('Invalid expanded excitation code')
        accumulator |= value << count
        count += bits
        while count >= 8:
            result.append(accumulator & 255)
            accumulator >>= 8
            count -= 8
    if count:
        result.append(accumulator & 255)
    return result


def transform(data, method):
    bits, samples, base, blocks, prefix, _ = validate(data)
    if method == 0:
        return data
    result = bytearray(data[:prefix])
    codes = unpack_codes(data[prefix:], bits, samples)
    if method == 2:
        previous = 0
        for i in range(24+base, prefix):
            current = result[i]
            result[i] = (current-previous) & 255
            previous = current
        previous = 0
        for i, current in enumerate(codes):
            codes[i] = (current-previous) & ((1 << bits)-1)
            previous = current
    elif method != 1:
        raise ValueError('Unknown LPX3 storage transform')
    # Preserve even nonzero unused final bits, for byte-exact restoration.
    used = samples*bits % 8
    padding = data[-1] & (255 ^ ((1 << used)-1)) if used else 0
    return bytes(result+codes+bytes([padding]))


def restore(data, method):
    if method == 0:
        validate(data)
        return data
    if method not in (1, 2):
        raise ValueError('Unknown LPX3 storage transform')
    bits, samples, base, blocks, prefix, packed = header(data)
    if len(data) != prefix+samples+1:
        raise ValueError('Invalid expanded LPX3 length')
    result = bytearray(data[:prefix])
    codes = bytearray(data[prefix:prefix+samples])
    if any(value >= 1 << bits for value in codes):
        raise ValueError('Invalid expanded excitation code')
    if method == 2:
        previous = 0
        for i in range(24+base, prefix):
            result[i] = (result[i]+previous) & 255
            previous = result[i]
        previous = 0
        for i, value in enumerate(codes):
            codes[i] = (value+previous) & ((1 << bits)-1)
            previous = codes[i]
    packed_codes = pack_codes(codes, bits)
    used = samples*bits % 8
    padding_mask = 255 ^ ((1 << used)-1) if used else 0
    if data[-1] & ~padding_mask:
        raise ValueError('Invalid unused excitation bits')
    packed_codes[-1] |= data[-1]
    result.extend(packed_codes)
    validate(result)
    return bytes(result)


def unpack(data):
    data = bytes(data)
    if data[:4] == b'LPX3':
        validate(data)
        return data
    if len(data) < WRAP.size:
        raise ValueError('Truncated LPZ1 wrapper')
    magic, method, raw_bytes, expanded_bytes, checksum = WRAP.unpack_from(data)
    if (magic != b'LPZ1' or method not in (0, 1, 2) or not 60 <= raw_bytes <= MAX_BYTES
            or not 60 <= expanded_bytes <= MAX_BYTES):
        raise ValueError('Invalid LPZ1 header')
    inflater = zlib.decompressobj()
    try:
        expanded = inflater.decompress(data[WRAP.size:], expanded_bytes+1)
    except zlib.error as error:
        raise ValueError('Damaged compressed LPX3') from error
    if (len(expanded) != expanded_bytes or not inflater.eof
            or inflater.unconsumed_tail or inflater.unused_data):
        raise ValueError('Invalid compressed LPX3 length or trailing data')
    raw = restore(expanded, method)
    if len(raw) != raw_bytes or zlib.crc32(raw) != checksum:
        raise ValueError('LPX3 checksum mismatch')
    return raw


def pack(data):
    """Return chosen storage and measured alternatives, never more than raw."""
    data = bytes(data)
    validate(data)
    candidates = [('original', data)]
    for method, label in enumerate(('deflate-packed', 'deflate-code-bytes', 'deflate-delta-bytes')):
        expanded = transform(data, method)
        blob = WRAP.pack(b'LPZ1', method, len(data), len(expanded), zlib.crc32(data))+zlib.compress(expanded, 9)
        candidates.append((label, blob))
    label, selected = min(candidates, key=lambda item: len(item[1]))
    if unpack(selected) != data:
        raise AssertionError('Entropy packing changed the original LPX3 stream')
    return selected, dict(method=label, original_bytes=len(data), stored_bytes=len(selected),
        saved_bytes=len(data)-len(selected), candidate_bytes={name: len(blob) for name, blob in candidates},
        exact_original_restored=True, decoder_code_included=False, avr_implemented=False)
