"""Measure complete lossless containers for small HQ4 streams, not AVR ports."""
import argparse
from collections import Counter
import hashlib
import heapq
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b'HQE1'
MODES = {'byte-huffman': 1, 'nibble-huffman': 2, 'nibble-tree': 3,
         'prefix1': 4, 'prefix2': 5, 'prefix4': 6, 'rice0': 7, 'rice1': 8, 'rice2': 9, 'rice3': 10,
         'byte-huffman-dense': 11}


class Writer:
    def __init__(self):
        self.bits = []

    def write(self, value, count):
        self.bits.extend((value >> bit) & 1 for bit in range(count-1, -1, -1))

    def packed(self):
        data = bytearray((len(self.bits)+7)//8)
        for index, bit in enumerate(self.bits):
            data[index//8] |= bit << (7-index % 8)
        return bytes(data)


class Reader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def read(self, count=1):
        value = 0
        for _ in range(count):
            if self.position >= len(self.data)*8:
                raise ValueError('Truncated entropy payload')
            value = (value << 1) | ((self.data[self.position//8] >> (7-self.position % 8)) & 1)
            self.position += 1
        return value

    def finish(self):
        if (self.position+7)//8 != len(self.data):
            raise ValueError('Trailing payload bytes')
        while self.position < len(self.data)*8:
            if self.read():
                raise ValueError('Nonzero padding')


def nibbles(data):
    return [value for byte in data for value in (byte & 15, byte >> 4)]


def from_nibbles(values):
    if len(values) % 2 or any(not 0 <= value < 16 for value in values):
        raise ValueError('Invalid nibble sequence')
    return bytes(values[i] | (values[i+1] << 4) for i in range(0, len(values), 2))


def huffman_lengths(symbols):
    counts = Counter(symbols)
    heap = [(count, symbol, [symbol]) for symbol, count in counts.items()]
    heapq.heapify(heap)
    lengths = Counter()
    while len(heap) > 1:
        a, _, left = heapq.heappop(heap)
        b, _, right = heapq.heappop(heap)
        for symbol in left+right:
            lengths[symbol] += 1
        heapq.heappush(heap, (a+b, min(left+right), left+right))
    return {symbol: max(1, lengths[symbol]) for symbol in counts}


def canonical(lengths):
    codes, code, previous = {}, 0, 0
    for symbol, length in sorted(lengths.items(), key=lambda item: (item[1], item[0])):
        if length < 1 or length > 255:
            raise ValueError('Invalid canonical code length')
        code <<= length-previous
        if code >= 1 << length:
            raise ValueError('Oversubscribed canonical code')
        codes[symbol] = code, length
        code, previous = code+1, length
    return codes


def tree_bytes(codes):
    root = {}
    for symbol, (code, length) in codes.items():
        node = root
        for shift in range(length-1, -1, -1):
            node = node.setdefault((code >> shift) & 1, {})
        node['symbol'] = symbol
    def emit(node):
        if 'symbol' in node:
            return bytes([128 | node['symbol']])
        if 0 not in node or 1 not in node:
            raise ValueError('Compact tree requires a complete multi-symbol code')
        left, right = emit(node[0]), emit(node[1])
        return bytes([1+len(left)])+left+right
    return emit(root)


def encode(data, method):
    if len(data) > 65535 or method not in MODES:
        raise ValueError('Unsupported bounded container')
    header = MAGIC+struct.pack('<BH', MODES[method], len(data))
    symbols = list(data) if method.startswith('byte-huffman') else nibbles(data)
    writer, book, lengths = Writer(), b'', {}
    if 'huffman' in method or method == 'nibble-tree':
        lengths = huffman_lengths(symbols)
        codes = canonical(lengths)
        if method == 'byte-huffman':
            book = struct.pack('<H', len(lengths))+bytes(value for symbol in sorted(lengths) for value in (symbol, lengths[symbol]))
        elif method == 'byte-huffman-dense':
            if max(lengths.values(), default=0) > 15:
                raise ValueError('Dense four-bit lengths cannot represent this byte codebook')
            book = from_nibbles([lengths.get(symbol, 0) for symbol in range(256)])
        elif method == 'nibble-tree' and len(lengths) > 1:
            tree = tree_bytes(codes)
            book = bytes([len(tree)])+tree
        elif method == 'nibble-tree':
            book = bytes([1, 128 | (symbols[0] if symbols else 0)])
            codes = {symbol: (0, 0) for symbol in lengths}
            lengths = {symbol: 0 for symbol in lengths}
        else:
            book = from_nibbles([lengths.get(symbol, 0) for symbol in range(16)])
        for symbol in symbols:
            writer.write(*codes[symbol])
    elif method.startswith('prefix'):
        count = int(method[6:])
        top = sorted(range(16), key=lambda symbol: (-symbols.count(symbol), symbol))[:count]
        book = bytes([int(math.log2(count))])+from_nibbles(top+[0]*(count % 2))
        for symbol in symbols:
            if symbol in top:
                writer.write(0, 1)
                writer.write(top.index(symbol), int(math.log2(count)))
            else:
                writer.write(1, 1)
                writer.write(symbol, 4)
    else:
        k = int(method[4:])
        order = sorted(range(16), key=lambda symbol: (-symbols.count(symbol), symbol))
        book = bytes([k])+from_nibbles(order)
        for symbol in symbols:
            rank = order.index(symbol)
            writer.write(0, rank >> k)
            writer.write(1, 1)
            writer.write(rank & ((1 << k)-1), k)
    payload = writer.packed()
    frequencies = Counter(symbols)
    return header+book+payload, dict(header_bytes=len(header), codebook_bytes=len(book),
        payload_bits=len(writer.bits), payload_bytes=len(payload), symbols=len(symbols),
        alphabet_size=len(set(symbols)), maximum_code_length=max(lengths.values(), default=0),
        shannon_lower_bound_bits=sum(count*math.log2(len(symbols)/count) for count in frequencies.values()),
        lengths=lengths)


def decode(data):
    if len(data) < 7 or data[:4] != MAGIC:
        raise ValueError('Bad entropy container')
    mode, size = struct.unpack_from('<BH', data, 4)
    method = next((name for name, value in MODES.items() if value == mode), None)
    if method is None:
        raise ValueError('Unknown entropy mode')
    offset, count, tree, top, order = 7, (size if mode in (1, 11) else 2*size), None, None, None
    if mode == 1:
        used = struct.unpack_from('<H', data, offset)[0]
        offset += 2
        if used > 256 or offset+2*used > len(data):
            raise ValueError('Invalid byte codebook')
        lengths = {data[offset+2*i]: data[offset+2*i+1] for i in range(used)}
        if len(lengths) != used:
            raise ValueError('Duplicate byte codebook symbols')
        offset += 2*used
    elif mode == 2:
        if offset+8 > len(data):
            raise ValueError('Truncated nibble codebook')
        lengths = {symbol: length for symbol, length in enumerate(nibbles(data[offset:offset+8])) if length}
        offset += 8
    elif mode == 11:
        if offset+128 > len(data): raise ValueError('Truncated dense byte lengths')
        lengths = {symbol: length for symbol, length in enumerate(nibbles(data[offset:offset+128])) if length}
        offset += 128
    elif mode == 3:
        if offset >= len(data): raise ValueError('Missing compact tree')
        nodes = data[offset]
        offset += 1
        tree = data[offset:offset+nodes]
        offset += nodes
        if not nodes or nodes > 31 or len(tree) != nodes:
            raise ValueError('Invalid compact tree')
    elif 4 <= mode <= 6:
        if offset >= len(data): raise ValueError('Missing prefix table')
        logk = data[offset]
        offset += 1
        if logk != mode-4:
            raise ValueError('Inconsistent prefix table')
        top = nibbles(data[offset:offset+(2**logk+1)//2])[:2**logk]
        offset += (2**logk+1)//2
        if len(top) != 2**logk or len(set(top)) != len(top):
            raise ValueError('Duplicate prefix table')
    else:
        if offset >= len(data): raise ValueError('Missing Rice table')
        k = data[offset]
        offset += 1
        if k != mode-7:
            raise ValueError('Inconsistent Rice table')
        order = nibbles(data[offset:offset+8])
        offset += 8
        if len(order) != 16 or len(set(order)) != 16:
            raise ValueError('Invalid Rice ranking')
    reader, out = Reader(data[offset:]), []
    if mode in (1, 2, 11):
        inverse = {(length, code): symbol for symbol, (code, length) in canonical(lengths).items()}
        maximum = max(lengths.values(), default=0)
        for _ in range(count):
            code = 0
            for length in range(1, maximum+1):
                code = (code << 1) | reader.read()
                if (length, code) in inverse:
                    out.append(inverse[length, code])
                    break
            else:
                raise ValueError('Unmatched canonical code')
    elif mode == 3:
        for _ in range(count):
            index = 0
            while not tree[index] & 128:
                skip = tree[index]
                index += skip if reader.read() else 1
                if not skip or index >= len(tree):
                    raise ValueError('Tree pointer out of bounds')
            if tree[index] & 112:
                raise ValueError('Invalid leaf')
            out.append(tree[index] & 15)
    elif top is not None:
        for _ in range(count):
            if not reader.read():
                out.append(top[reader.read(logk)])
            else:
                value = reader.read(4)
                if value in top:
                    raise ValueError('Noncanonical escaped prefix symbol')
                out.append(value)
    else:
        for _ in range(count):
            quotient = 0
            while not reader.read():
                quotient += 1
                if quotient > 15:
                    raise ValueError('Invalid Rice quotient')
            rank = (quotient << k) | reader.read(k)
            if rank >= 16:
                raise ValueError('Invalid Rice rank')
            out.append(order[rank])
    reader.finish()
    return bytes(out) if mode in (1, 11) else from_nibbles(out)


def split_stream(data):
    headers, coefficients, frames = bytearray(), bytearray(), []
    offset = 0
    while offset < len(data):
        start = offset
        first = data[offset]
        offset += 1
        if first == 255:
            raise ValueError('Source stream must omit EOF')
        headers.append(first)
        if first & 192 == 192:
            if first & 60 or offset >= len(data) or data[offset] > 126:
                raise ValueError('Invalid extended HQ4 header')
            headers.append(data[offset]); offset += 1
        if offset >= len(data):
            raise ValueError('Truncated HQ4 spectral header')
        spectral = data[offset]
        headers.append(spectral); offset += 1
        count = (4, 0, 2, 2)[spectral >> 6]
        if not frames and count != 4 or offset+count > len(data):
            raise ValueError('Missing/truncated coefficient update')
        coefficients.extend(data[offset:offset+count]); offset += count
        frames.append(dict(bytes=data[start:offset], coefficient_bytes=data[offset-count:offset] if count else b''))
    if not frames:
        raise ValueError('Empty HQ4 stream')
    return bytes(headers), bytes(coefficients), frames


def join_stream(headers, coefficients):
    out, hi, ci = bytearray(), 0, 0
    while hi < len(headers):
        first = headers[hi]; out.append(first); hi += 1
        if first & 192 == 192:
            if hi >= len(headers): raise ValueError('Truncated separated pitch')
            out.append(headers[hi]); hi += 1
        if hi >= len(headers): raise ValueError('Truncated separated header')
        spectral = headers[hi]; out.append(spectral); hi += 1
        count = (4, 0, 2, 2)[spectral >> 6]
        if ci+count > len(coefficients): raise ValueError('Truncated separated coefficients')
        out.extend(coefficients[ci:ci+count]); ci += count
    if ci != len(coefficients): raise ValueError('Trailing separated coefficients')
    result = bytes(out)
    split_stream(result)
    return result


def encode_split(data, method):
    headers, coefficients, _ = split_stream(data)
    inner, info = encode(coefficients, method)
    outer = b'HQY1'+struct.pack('<HH', len(headers), len(coefficients))+headers+inner
    return outer, dict(info, separation_header_bytes=8, raw_header_bytes=len(headers), coefficient_bytes=len(coefficients))


def decode_split(data):
    if len(data) < 8 or data[:4] != b'HQY1': raise ValueError('Bad separated container')
    headers, coefficients = struct.unpack_from('<HH', data, 4)
    if 8+headers > len(data): raise ValueError('Truncated separated container')
    recovered = decode(data[8+headers:])
    if len(recovered) != coefficients: raise ValueError('Separated coefficient count differs')
    return join_stream(data[8:8+headers], recovered)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stream', action='append', required=True, help='Label=actual speech.hq path')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--retain', type=Path)
    a = p.parse_args()
    report = dict(schema='hq4-small-stream-entropy-v1', avr_decoder_implemented=False,
        bitreader_code_estimate_bytes=70, eeprom_free_bytes=0,
        estimate_policy='Optimistic70 additional code bytes; tree bytes included in actual container; no proven timing/code/RAM win', streams=[])
    for item in a.stream:
        label, source = item.split('=', 1)
        source = Path(source)
        data = source.read_bytes()
        headers, coefficients, frames = split_stream(data)
        build_path = source.parent.parent/'avr/build.json'
        built = json.loads(build_path.read_text(encoding='utf-8')) if build_path.is_file() else None
        row = dict(id=label, source=source.resolve().relative_to(ROOT).as_posix(),
            raw_bytes=len(data), source_sha256=hashlib.sha256(data).hexdigest(),
            frames=len(frames), raw_headers=len(headers), coefficient_bytes=len(coefficients), candidates=[])
        if built:
            if built['streamSha256'] != hashlib.sha256(data).hexdigest():
                raise ValueError('Actual build report belongs to another speech stream')
            row['baseline'] = {key: built[key] for key in ('flashBytes', 'codeBytes', 'streamBytes', 'eofBytes', 'linkerPaddingBytes', 'eepromUsedBytes', 'eepromSha256')}
            row['baseline']['minimum_slack_cycles'] = built['verification']['foregroundTiming']['minimumSlackCycles']
        for separated in (False, True):
            for method in MODES:
                if separated and method.startswith('byte-huffman'): continue
                blob, info = (encode_split if separated else encode)(data, method)
                recovered = (decode_split if separated else decode)(blob)
                if recovered != data: raise AssertionError('Independent decoder changed exact HQ4 bytes')
                name = ('split-' if separated else '')+method
                destination = a.output/label/(name+'.bin')
                destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(blob)
                gain = len(data)-len(blob)
                result = dict(method=name, container_bytes=len(blob), **info,
                    data_saving_bytes=gain, net_saving_after_70b_code=gain-70,
                    independent_roundtrip=True, container_sha256=hashlib.sha256(blob).hexdigest())
                # Fixed firmware can compile all counts, mode tags and pointer
                # constants into its reader. This deliberately optimistic
                # deployment lower bound retains every coding-table byte.
                removable_book_metadata = 2 if method == 'byte-huffman' else (1 if method == 'nibble-tree' or method.startswith(('prefix', 'rice')) else 0)
                minimal_data = info['payload_bytes']+info['codebook_bytes']-removable_book_metadata+(len(headers) if separated else 0)
                result.update(deployment_minimum_data_bytes=minimal_data,
                    deployment_minimum_data_saving_bytes=len(data)-minimal_data,
                    incremental_reader_break_even_bytes=len(data)-minimal_data,
                    net_deployment_saving_after_estimated_70b_reader=len(data)-minimal_data-70,
                    deployment_policy='Headerless optimistic lower bound; counts/modes/pointers/EOF handling must still be implemented in code or constants')
                lengths = result.pop('lengths')
                if lengths:
                    per_frame = [sum(lengths[n] for n in (nibbles(frame['coefficient_bytes'] if separated else frame['bytes'])
                        if not method.startswith('byte-huffman') else frame['bytes'])) for frame in frames]
                    result['coded_bits_per_frame'] = dict(mean=sum(per_frame)/len(per_frame), maximum=max(per_frame),
                        full_update_maximum=max(bits for bits, frame in zip(per_frame, frames) if len(frame['coefficient_bytes']) == 4))
                    result['code_lengths'] = lengths
                row['candidates'].append(result)
        row['best_complete_container'] = min(row['candidates'], key=lambda c:c['container_bytes'])['method']
        report['streams'].append(row)
    report['source_sha256_normalized_lf'] = hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest()
    save(a.output/'report.json', report)
    if a.retain: save(a.retain/'report.json', report)
    print(json.dumps({row['id']: min(row['candidates'], key=lambda c:c['container_bytes']) for row in report['streams']}, indent=2))


if __name__ == '__main__':
    main()
