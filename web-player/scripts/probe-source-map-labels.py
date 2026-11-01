"""Test source-map label transport through the registered Binaryen optimizer.

Diagnostic only: labels identify input positions, not measured C inline scopes
or exclusive durations. Raw maps and binaries must remain under ignored build/.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

if not __debug__:
    raise RuntimeError("Run without -O: this diagnostic requires its proof assertions")

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def vlq(value):
    assert isinstance(value, int) and -(2**31) <= value < 2**31
    value = 1 if value == -(2**31) else ((-value << 1 | 1) if value < 0 else value << 1)
    result = ""
    while True:
        digit, value = value & 31, value >> 5
        result += ALPHABET[digit | (32 if value else 0)]
        if not value:
            return result


def decode_map(mapping):
    assert mapping.get("version") == 3 and isinstance(mapping.get("sources"), list)
    assert all(isinstance(s, str) for s in mapping["sources"])
    names = mapping.get("names", [])
    assert isinstance(names, list) and all(isinstance(n, str) for n in names)
    assert isinstance(mapping.get("mappings"), str) and ";" not in mapping["mappings"]
    assert isinstance(mapping.get("sourceRoot", ""), str)
    rows = []
    offset = source = line = column = name = 0
    for segment in mapping["mappings"].split(",") if mapping["mappings"] else []:
        values, number, shift = [], 0, 0
        for char in segment:
            digit = ALPHABET.index(char)
            number += (digit & 31) << shift
            assert number < 2**32 and shift <= 30
            if digit & 32:
                shift += 5
            else:
                values.append(-(2**31) if number == 1 else (-(number >> 1) if number & 1 else number >> 1))
                number = shift = 0
        assert segment and shift == 0 and len(values) in (1, 4, 5)
        offset += values[0]
        assert offset >= 0 and (not rows or offset > rows[-1]["offset"])
        row = {"offset": offset, "delta": values[0], "position": None, "name": None}
        if len(values) > 1:
            source += values[1]
            line += values[2]
            column += values[3]
            assert 0 <= source < len(mapping["sources"]) and min(line, column) >= 0
            row["position"] = (mapping.get("sourceRoot", ""), mapping["sources"][source], line, column)
            row["fields"] = values[:4]
            if len(values) == 5:
                name += values[4]
                assert 0 <= name < len(names)
                row["name"] = names[name]
        rows.append(row)
    return rows


def label_map(mapping, unique):
    segments, labels, positions = [], [], {}
    previous = 0
    for row in decode_map(mapping):
        if row["position"] is None:
            segments.append(vlq(row["delta"]))
            continue
        index = len(labels) if unique else 0
        label = "micromusic-scope-" + str(index)
        if unique or not labels:
            labels.append(label)
        positions.setdefault(label, set()).add(row["position"])
        segments.append("".join(vlq(v) for v in row["fields"] + [index - previous]))
        previous = index
    return {**mapping, "names": labels, "mappings": ",".join(segments)}, positions


def executable_sections(data):
    assert data[:8] == b"\0asm\1\0\0\0"
    result, offset = [], 8
    while offset < len(data):
        start, tag = offset, data[offset]
        offset += 1
        size = shift = 0
        while True:
            assert offset < len(data) and shift < 35
            byte = data[offset]
            offset += 1
            size |= (byte & 127) << shift
            shift += 7
            if not byte & 128:
                break
        end = offset + size
        assert end <= len(data)
        if tag:
            result.append((tag, start, data[start:end]))
        offset = end
    return result


def check_labels(rows, expected):
    named = [row for row in rows if row["name"] is not None]
    for row in named:
        assert row["name"] in expected, "Unexpected scope label"
        assert row["position"] in expected[row["name"]], "Label/source-position mismatch"
    return len(named), len({row["name"] for row in named})


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("input", "source-map", "emsdk", "out-dir"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--reference", type=Path, default=root / "web-player/wasm/attiny13a.wasm")
    args = parser.parse_args()
    out = args.out_dir.resolve()
    assert out != root / "build" and (root / "build") in out.parents, "Keep diagnostics under build/"
    optimizer = args.emsdk / "upstream/bin" / ("wasm-opt.exe" if os.name == "nt" else "wasm-opt")
    original = json.loads(args.source_map.read_text(encoding="utf-8"))
    uniform, uniform_positions = label_map(original, False)
    unique, unique_positions = label_map(original, True)
    reference = executable_sections(args.reference.read_bytes())
    out.mkdir(parents=True, exist_ok=True)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    report = {"schema": "micromusic-source-map-label-transport-v1", "exclusiveDurationsMeasured": False,
              "realInlineScopesAssigned": False, "inputMappedPositions": len(unique_positions),
              "inputSha256": sha(args.input.read_bytes()), "sourceMapSha256": sha(args.source_map.read_bytes()),
              "referenceSha256": sha(args.reference.read_bytes()), "optimizerSha256": sha(optimizer.read_bytes()),
              "scriptSha256": sha(Path(__file__).read_bytes().replace(b"\r\n", b"\n")), "results": []}
    for variant, mapping, expected in [("baseline", original, None), ("uniform", uniform, uniform_positions),
                                       ("unique", unique, unique_positions)]:
        inp, binary, emitted = [out / (variant + suffix) for suffix in (".input.map", ".wasm", ".output.map")]
        inp.write_text(json.dumps(mapping), encoding="utf-8")
        command = [str(optimizer), str(args.input), "-O3", "--input-source-map", str(inp),
                   "--output-source-map", str(emitted), "-o", str(binary)]
        subprocess.run(command, check=True, capture_output=True)
        assert executable_sections(binary.read_bytes()) == reference, "Executable sections/offsets changed"
        rows = decode_map(json.loads(emitted.read_text(encoding="utf-8")))
        named, distinct = check_labels(rows, expected) if expected is not None else (0, 0)
        mapped = sum(row["position"] is not None for row in rows)
        if expected is not None:
            assert named == mapped and named > 0, "Some source labels did not survive"
        report["results"].append({"variant": variant, "executableSectionsAndOffsetsEqual": True,
                                  "mappedPositions": mapped, "namedPositions": named, "distinctLabels": distinct,
                                  "labelSourcePositionsVerified": expected is not None,
                                  "inputMapSha256": sha(inp.read_bytes()), "outputMapSha256": sha(emitted.read_bytes()),
                                  "outputWasmSha256": sha(binary.read_bytes())})
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
