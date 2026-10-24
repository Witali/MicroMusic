"""Decode raw ATtiny13A wire-v2 probe frames; never infer a silicon outcome."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def finite(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not a boolean")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def decode_rows(rows, config, profile, allow_reset_fragments=False):
    """Preserve six raw bytes, serial timestamps and explicit unframed ranges."""
    policy = config.get("sequencePolicy")
    if allow_reset_fragments and policy not in ("reset-to-zero", "restartable-pairs"):
        raise ValueError("Fragment recovery is only for reset-to-zero or restartable-pairs probes")
    bits, times, previous_clock, previous_time = [], [], 0, float("-inf")
    for index, row in enumerate(rows):
        at = finite(row["time_s"], "time_s")
        clock, data = str(row["clock"]).strip(), str(row["data"]).strip()
        if clock not in ("0", "1") or data not in ("0", "1"):
            raise ValueError("clock/data must be digital 0/1")
        clock, data = int(clock), int(data)
        if at < previous_time:
            raise ValueError("CSV timestamps are not monotonic")
        if not index and clock:
            raise ValueError("Capture must start with trace clock low")
        if clock and not previous_clock:
            bits.append(data)
            times.append(at)
        previous_clock, previous_time = clock, at

    def packet(offset):
        frame = []
        for start in range(offset, offset + 112, 8):
            byte = 0
            for bit in bits[start:start + 8]:
                byte = (byte << 1) | bit
            frame.append(byte)
        if frame[:2] != [0xa5, 0x5a]:
            raise ValueError(f"Invalid sync at bit{offset}")
        checksum = 0
        for byte in frame[2:]:
            checksum ^= byte
        if checksum:
            raise ValueError(f"Checksum mismatch at bit{offset}")
        if frame[2] != 2:
            raise ValueError("Unsupported wire version; legacy Timer0 wire-v1 is distinct")
        if frame[3] != config["probeId"] or frame[4] != profile["profileId"]:
            raise ValueError("Probe/profile identity does not match the selected source profile")
        return {"version": 2, "probeId": frame[3], "profileId": frame[4],
                "sequence": frame[5] | (frame[6] << 8), "data": frame[7:13],
                "bitOffset": offset, "frameStartSeconds": times[offset],
                "frameEndSeconds": times[offset + 111]}

    records, accepted, offset = [], [], 0
    while offset + 112 <= len(bits):
        try:
            record = packet(offset)
        except ValueError:
            if not allow_reset_fragments:
                raise
            offset += 1
            continue
        records.append(record)
        accepted.append((offset, offset + 112))
        offset += 112
    if not records:
        raise ValueError("No complete matching wire-v2 frame")
    fragments, previous_end = [], 0
    for begin, end in [*accepted, (len(bits), len(bits))]:
        if begin > previous_end:
            fragments.append({"startBit": previous_end, "endBit": begin,
                              "bitCount": begin - previous_end,
                              "startSeconds": times[previous_end], "endSeconds": times[begin - 1]})
        previous_end = end
    if fragments and not allow_reset_fragments:
        raise ValueError("Incomplete frame or missing clock edges")
    sequence_gaps = []
    if policy == "restartable-pairs":
        # Boot0/1 is mandatory; optional completion2/3 follows it. A reset can
        # restart at0 after either complete pair, never silently inside a pair.
        state = 0
        for index, record in enumerate(records):
            allowed = {0: (0,), 1: (1,), 2: (0, 2), 3: (3,), 4: (0,)}[state]
            sequence = record["sequence"]
            if sequence not in allowed:
                if not allow_reset_fragments:
                    raise ValueError("Missing/duplicated record or incomplete restartable-pairs sequence")
                sequence_gaps.append({"recordIndex": index, "expectedSequences": list(allowed),
                                      "observedSequence": sequence})
            # Retain every complete raw frame, including one whose partner was
            # interrupted. No missing frame or byte value is manufactured.
            state = {0: 1, 1: 2, 2: 3, 3: 4}.get(sequence, 0)
        if state in (1, 3):
            if not allow_reset_fragments:
                raise ValueError("Incomplete restartable-pairs sequence at end of capture")
            sequence_gaps.append({"recordIndex": len(records), "expectedSequences": [state],
                                  "observedSequence": None})
    else:
        for index, record in enumerate(records):
            expected = 0 if policy == "reset-to-zero" else index % 65536
            if record["sequence"] != expected:
                raise ValueError("Missing/duplicated record or unexpected sequence")
    expected = profile.get("expectedRecords", config.get("expectedRecords"))
    if expected is not None and len(records) != expected:
        raise ValueError(f"Expected {expected} records, got {len(records)}")
    quality = "unframed-bits-retained" if fragments else "complete-frames"
    if sequence_gaps:
        quality = "unframed-bits-and-sequence-gaps-retained" if fragments else "sequence-gaps-retained"
    result = {"records": records, "fragments": fragments, "transportQuality": quality}
    if policy == "restartable-pairs":
        result["sequenceGaps"] = sequence_gaps
    return result


def measurements(value):
    required = {"chipMarking", "chipRevision", "vccVolts", "temperatureC", "clockHz",
                "fuses", "instrument", "timingToleranceSeconds"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise ValueError("Hardware measurements require " + ", ".join(sorted(required)))
    if not isinstance(value["chipMarking"], str) or not value["chipMarking"].strip():
        raise ValueError("Record the measured chip marking")
    if value["chipRevision"] is not None and not isinstance(value["chipRevision"], str):
        raise ValueError("chipRevision must be a string or null when unknown")
    for name in ("vccVolts", "clockHz", "timingToleranceSeconds"):
        if finite(value[name], name) <= 0:
            raise ValueError(name + " must be positive")
    finite(value["temperatureC"], "temperatureC")
    if not isinstance(value["instrument"], dict) or not value["instrument"]:
        raise ValueError("Record instrument/acquisition settings")
    if not isinstance(value["fuses"], dict) or not {"low", "high", "lock"}.issubset(value["fuses"]):
        raise ValueError("Record low/high/lock fuse readback")
    for name in ("low", "high", "lock"):
        byte = value["fuses"][name]
        byte = int(byte, 0) if isinstance(byte, str) else byte
        if not isinstance(byte, int) or isinstance(byte, bool) or not 0 <= byte <= 255:
            raise ValueError("Fuse values must be bytes")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--capture-kind", choices=("hardware", "synthetic"), required=True)
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--allow-reset-fragments", action="store_true")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if config["schema"] != "micromusic-attiny13a-hardware-probe-v1":
            raise ValueError("Unsupported probe configuration schema")
        profiles = {profile["id"]: profile for profile in config["profiles"]}
        if args.profile not in profiles:
            raise ValueError("Unknown source profile")
        conditions = {}
        if args.capture_kind == "hardware":
            if args.measurements is None:
                raise ValueError("Hardware captures require --measurements JSON; synthetic tests must use --capture-kind synthetic")
            conditions = measurements(json.loads(args.measurements.read_text(encoding="utf-8")))
        with args.csv.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            required = {"time_s", "clock", "data"}
            if args.capture_kind == "hardware":
                required.update(config.get("requiredCsvColumns", []))
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("CSV requires " + ", ".join(sorted(required)))
            result = decode_rows(reader, config, profiles[args.profile], args.allow_reset_fragments)
        source = args.source or args.config.parent / config["firmware"]
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        folder = Path(__file__).parent
        result.update({"schema": "micromusic-attiny13a-hardware-probe-trace-v1",
                       "status": "observed-hardware" if args.capture_kind == "hardware" else "synthetic-decoder-test",
                       "qualification": "unreviewed-capture", "profile": args.profile,
                       "waveformCsv": str(args.csv), "measurements": conditions,
                       "identities": {"captureSha256": sha(args.csv), "sourceSha256": sha(source),
                                      "configurationSha256": sha(args.config),
                                      "wireSha256": sha(folder / "probe-wire.inc"),
                                      "registerDefinitionsSha256": sha(folder / "../attiny13a-registers.generated.inc")}})
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.error(str(error))
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
