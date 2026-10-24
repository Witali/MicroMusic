"""Decode source-only ATtiny13A probe captures; never predict Timer0 results."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def level(row, name):
    value = row[name].strip()
    if value not in ("0", "1"):
        raise ValueError(f"{name} must be a digital 0/1 value, got {value!r}")
    return int(value)


def decode_rows(rows, profile):
    """Rows must include time_s,clock,data,t0; capture starts before the boot frame."""
    bits, bit_times, rises = [], [], []
    previous_clock = previous_t0 = 0
    previous_time = float("-inf")
    first = True
    for row in rows:
        at = float(row["time_s"])
        if not math.isfinite(at):
            raise ValueError("CSV timestamps must be finite numbers")
        clock, data, t0 = (level(row, name) for name in ("clock", "data", "t0"))
        if at < previous_time:
            raise ValueError("CSV timestamps are not monotonic")
        if first and (clock or t0):
            raise ValueError("Capture must begin with trace clock and T0 low, before boot")
        first = False
        if clock and not previous_clock:
            bits.append(data)
            bit_times.append(at)
        if t0 and not previous_t0:
            rises.append(at)
        previous_clock, previous_t0, previous_time = clock, t0, at
    if len(bits) % 112:
        raise ValueError(f"Incomplete frame or missing clock edges: {len(bits)} bits is not a multiple of 112")
    records = []
    names = ("version", "type", "sequenceLow", "sequenceHigh", "tcnt0", "tifr0",
             "pinb", "ocr0a", "ocr0b", "tccr0a", "tccr0b")
    for offset in range(0, len(bits), 112):
        frame = []
        for byte in range(14):
            value = 0
            for bit in bits[offset + byte * 8:offset + byte * 8 + 8]:
                value = (value << 1) | bit
            frame.append(value)
        if frame[:2] != [0xA5, 0x5A]:
            raise ValueError(f"Invalid sync at frame {len(records)}; verify wiring/bit order")
        checksum = 0
        for value in frame[2:]:
            checksum ^= value
        if checksum:
            raise ValueError(f"Checksum mismatch at frame {len(records)}")
        record = dict(zip(names, frame[2:13]))
        record["sequence"] = record.pop("sequenceLow") | (record.pop("sequenceHigh") << 8)
        record["frameEndSeconds"] = bit_times[offset + 111]
        if record["version"] != 1 or record["type"] not in (0, 1, 2):
            raise ValueError(f"Unsupported wire version/type at frame {len(records)}")
        records.append(record)
    if not records or records[0]["type"] != 0 or records[0]["sequence"]:
        raise ValueError("The initial boot record, sequence 0, is missing")
    if rises and records[0]["frameEndSeconds"] >= rises[0]:
        raise ValueError("T0 pulses started before the boot frame completed")
    sequence, writes = 0, 0
    for record in records[1:]:
        if record["type"] == 1:
            sequence += 1
            if record["sequence"] != sequence % 65536:
                raise ValueError("Missing/duplicated pulse record or unexpected sequence")
            if sequence > len(rises) or record["frameEndSeconds"] < rises[sequence - 1]:
                raise ValueError("Pulse record precedes its external T0 rising edge")
            if sequence < len(rises) and record["frameEndSeconds"] >= rises[sequence]:
                raise ValueError("Pulse record was not emitted before the next T0 rising edge")
        elif record["type"] == 2:
            writes += 1
            expected = profile["defines"].get("PROBE_WRITE_AFTER", 0)
            if not expected or sequence != expected or record["sequence"] != expected:
                raise ValueError("Scheduled-write marker does not match the selected profile")
        else:
            raise ValueError("Unexpected second boot record: did the device reset?")
    if sequence != profile["pulses"] or len(rises) != profile["pulses"]:
        raise ValueError(f"Expected {profile['pulses']} external pulses and samples; got {len(rises)} pulses/{sequence} samples")
    if writes != bool(profile["defines"].get("PROBE_WRITE_AFTER", 0)):
        raise ValueError("Missing/duplicated scheduled-write marker")
    return rises, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--capture-kind", choices=("hardware", "synthetic"), required=True,
                        help="Explicit provenance; a decoder test must never be labeled a silicon observation")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("timer0-top-zero-probe.json"))
    parser.add_argument("--source", type=Path, help="Actual firmware source used for this capture; defaults to the configured sibling source")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    profiles = {profile["id"]: profile for profile in config["profiles"]}
    if args.profile not in profiles:
        parser.error("Unknown profile; choose " + ", ".join(profiles))
    with args.csv.open(newline="", encoding="utf-8-sig") as capture:
        reader = csv.DictReader(capture)
        required = {"time_s", "clock", "data", "t0"}
        if not required.issubset(reader.fieldnames or []):
            parser.error("CSV requires columns time_s,clock,data,t0; retain oc0a/oc0b waveform columns too")
        try:
            rises, records = decode_rows(reader, profiles[args.profile])
        except (ValueError, KeyError) as error:
            parser.error(str(error))
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    source = args.source or Path(__file__).with_name(config["firmware"])
    result = {"schema": "micromusic-attiny13a-timer0-observed-trace-v1",
              "status": "observed-hardware" if args.capture_kind == "hardware" else "synthetic-decoder-test",
              "profile": args.profile, "waveformCsv": str(args.csv),
              "measurements": {"captureSha256": sha(args.csv), "sourceSha256": sha(source),
                               "configurationSha256": sha(args.config)},
              "t0RisesSeconds": rises, "records": records}
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
