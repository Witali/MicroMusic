"""Lossless target packing for the voiced/white period decoder.

The synthesis arithmetic is fixed_period; this module only specializes fields
and splits the packed wavebook between Flash and 64 bytes of read-only EEPROM.
No EEPROM writes occur during playback.
"""
import numpy as np

from compact_period import Reader, Writer, repeat_read, repeat_write
from fixed_period import validate


def validate_tiny(model):
    frames, book, _ = validate(model)
    if model['phase_bits'] != 4 or model.get('dc_block_shift') != 7:
        raise ValueError('Tiny speech requires phase_bits=4 and dc_block_shift=7')
    if model['samples'] % 64 or model['samples']//64 > 255:
        raise ValueError('Tiny speech requires 1..255 complete 64-sample blocks')
    if any((h & 112) and not (h & 128) for _, h, _ in frames):
        raise ValueError('Tiny speech supports voiced base frames only')
    if any((r & 15) and (r >> 4) for _, _, r in frames):
        raise ValueError('Tiny speech supports white residuals only')
    active = [int(h)&15 for _, h, _ in frames if h & 112]
    words = max(active, default=0)+1
    return frames, book[:words], words


def pack_tiny(model):
    """Return flash_tables, field_stream, flash_data, eeprom and constants."""
    frames, book, words = validate_tiny(model)
    index_bits = max(1, (words-1).bit_length())
    nibbles = (book.ravel()+8).astype(np.uint8)
    wave = (nibbles[::2] | nibbles[1::2] << 4).tobytes()
    used = min(64, len(wave))
    split = len(wave)-used
    eeprom = wave[split:]+b'\xff'*(64-used)
    writer = Writer()
    previous_pitch = previous_gain = previous_index = previous_level = 0
    for pitch, header, residual in frames:
        pitch, header, residual = int(pitch), int(header), int(residual)
        delta = pitch-previous_pitch
        if not delta:
            writer.put(0, 1)
        else:
            writer.put(1, 1)
            if abs(delta) == 1:
                writer.put(0, 1)
                writer.put(int(delta < 0), 1)
            else:
                writer.put(1, 1)
                if 2 <= abs(delta) <= 5:
                    writer.put(0, 1)
                    writer.put(2*(abs(delta)-2)+int(delta < 0), 3)
                else:
                    writer.put(1, 1)
                    writer.put(pitch, 8)
        previous_pitch = pitch
        gain = (header >> 4) & 7
        previous_gain = repeat_write(writer, gain, previous_gain, 3)
        if gain:
            previous_index = repeat_write(writer, header & 15, previous_index, index_bits)
        previous_level = repeat_write(writer, residual & 15, previous_level, 4)
    fields = writer.finish()
    constants = dict(SAMPLES=model['samples'], BLOCKS=model['samples']//64,
                     INITIAL_PHASE=model['initial_phase_u16'], NOISE_SEED=model['noise_seed_u16'],
                     DC_SHIFT=7, INDEX_BITS=index_bits, INDEX_MASK=(1 << index_bits)-1,
                     WAVE_BYTES=len(wave), WAVE_FLASH_BYTES=split, EEPROM_WAVE_SPLIT=split,
                     EEPROM_USED_BYTES=used, ENABLE_GAIN6=int(any(((int(h)>>4)&7)==6 for _,h,_ in frames)))
    return dict(flash_tables=wave[:split], field_stream=fields, flash_data=wave[:split]+fields,
                eeprom=eeprom, constants=constants)


def unpack_tiny(bundle):
    """Independent sequential unpacker; canonicalizes inactive base fields."""
    c = bundle['constants']
    flash, eeprom = bytes(bundle['flash_data']), bytes(bundle['eeprom'])
    words = c['WAVE_BYTES']//16
    split, used = c['WAVE_FLASH_BYTES'], c['EEPROM_USED_BYTES']
    if (not 1 <= words <= 16 or c['WAVE_BYTES'] != words*16 or used != min(64,words*16) or
            split+used != words*16 or c['EEPROM_WAVE_SPLIT'] != split or len(eeprom)!=64 or
            eeprom[used:] != b'\xff'*(64-used) or c['INDEX_BITS'] != max(1,(words-1).bit_length()) or
            c['SAMPLES'] != c['BLOCKS']*64 or not 1 <= c['BLOCKS'] <= 255):
        raise ValueError('Invalid tiny speech layout')
    if len(flash) <= split:
        raise ValueError('Truncated tiny speech data')
    wave = np.frombuffer(flash[:split]+eeprom[:used], np.uint8)
    nibbles = np.column_stack((wave & 15, wave >> 4)).ravel().astype(int)-8
    book = nibbles.reshape(words,32).tolist()+[[0]*32 for _ in range(16-words)]
    reader = Reader(flash[split:])
    pitch = gain = index = level = 0
    frames = []
    for _ in range(c['BLOCKS']):
        if reader.get(1):
            if not reader.get(1):
                pitch += -1 if reader.get(1) else 1
            elif not reader.get(1):
                code = reader.get(3)
                pitch += (code//2+2)*(-1 if code & 1 else 1)
            else:
                pitch = reader.get(8)
        gain = repeat_read(reader,gain,3)
        if gain:
            index = repeat_read(reader,index,c['INDEX_BITS'])
            if index >= words:
                raise ValueError('Tiny wave index exceeds stored dictionary')
        level = repeat_read(reader,level,4)
        frames.append([pitch,(128 | gain << 4 | index) if gain else 0,level])
    reader.finish()
    model = dict(schema='period-fixed-v1',sample_rate=7500,samples=c['SAMPLES'],hop=64,
                 phase_bits=4,dc_block_shift=c['DC_SHIFT'],initial_phase_u16=c['INITIAL_PHASE'],
                 noise_seed_u16=c['NOISE_SEED'],codebook=book,noise_filters=[[0]*8 for _ in range(3)],frames=frames)
    validate_tiny(model)
    if c['ENABLE_GAIN6'] != int(any(((h>>4)&7)==6 for _,h,_ in frames)):
        raise ValueError('Tiny gain feature disagrees with frame data')
    return model
