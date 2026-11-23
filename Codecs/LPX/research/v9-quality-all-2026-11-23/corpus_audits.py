#!/usr/bin/env python3
"""Supplementary private inputs/audits, deliberately separate from primary27.

prepare-wideband consumes the already approved native 2.4-second WAV converted
from its original MP3; it never routes through 8 kHz. prepare-long consumes the
existing 128001-sample continuous reference. audit-sparse2 checks all archived
2 kbit/s incumbents against their own prepared targets and exact PCM/PWM, using
lossless Python V9 repacking only as an independent reference operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import corpus as c


def prepare(args):
    import numpy as np
    out = c.private_path(args.output, fresh=True)
    out.mkdir(parents=True)
    source = Path(args.source).resolve()
    if args.command == "prepare-wideband":
        pcm, rate = c.read_wav(source)
        if rate != 44100 or len(pcm) != 105840:
            raise ValueError("Prospective wideband control is the fixed complete44.1 kHz/2.4-second source")
        rates, label = (12000, 16000), "native_wideband_control"
    else:
        pcm, rate = np.fromfile(source, dtype="<i2"), 8000
        if len(pcm) != 128001:
            raise ValueError("Prospective Long audit requires the existing128001-sample reference")
        rates, label = (8000,), "continuous_long"
    baseline = c.private_path(args.baseline_build)
    jobs = []
    for actual in rates:
        target = c.resample(pcm, rate, actual)
        name = f"case-00-{actual}.s16le"
        (out / name).write_bytes(target.astype("<i2").tobytes())
        for mode in ("p4", "p6"):
            jobs.append({"job_id": f"case-00-{mode}-{actual}", "ordinal": 0, "kind": "speech", "split": label,
                         "mode": mode, "sample_rate": actual, "samples": len(target), "target": name,
                         "target_sha256": c.digest(out / name), "calls": 4, "auto_quiet": False,
                         "normalize": False, "size_allowance_percent": 0})
    manifest = {"schema": 1, "set": label, "jobs": jobs,
                "source_records": [{"ordinal": 0, "source": str(source), "source_file_sha256": c.digest(source),
                                    "source_pcm_sha256": hashlib.sha256(pcm.astype("<i2").tobytes()).hexdigest(),
                                    "source_rate": rate, "source_samples": len(pcm), "kind": "speech", "split": label}],
                "supplement_harness_sha256": c.digest(__file__), **c.study_metadata(baseline)}
    c.json_write(out / "manifest-private.json", manifest)
    print(json.dumps({"stage": "supplement_targets_frozen", "set": label, "cases": 1, "jobs": len(jobs),
                      "source_rate": rate, "source_samples": len(pcm), "target_rates": list(rates)}))


def audit_sparse(args):
    import numpy as np
    out = c.private_path(args.output, fresh=True)
    out.mkdir(parents=True)
    manifest_path = Path(args.firmware_manifest).resolve()
    original = c.json_read(manifest_path)
    jobs = [j for j in original["jobs"] if float(j["kbps"]) == 2]
    if len(jobs) != 27 or {j["ordinal"] for j in jobs} != set(range(27)):
        raise ValueError("Expected exact established27 Sparse80/2k incumbents")
    encoder = c.private_path(args.encoder)
    build = c.json_read(encoder.parent / "build-private.json")
    if c.digest(encoder) != build["binary_sha256"]:
        raise ValueError("Changed native decoder binary")
    tools = c.ROOT / c.CODEC_REL / "tools"
    sys.path.insert(0, str(tools))
    from speech_v9 import repack
    evaluator = encoder.parent / "source" / c.CODEC_REL / "tools"
    receipts = []
    for row in sorted(jobs, key=lambda x: x["ordinal"]):
        ordinal = row["ordinal"]
        paths = {field: manifest_path.parent / row[field] for field in
                 ("stream_file", "target_file", "expected_pcm16_file", "expected_pwm8_file")}
        hash_fields = {"stream_file": "stream_sha256", "target_file": "target_sha256",
                       "expected_pcm16_file": "expected_pcm16_sha256", "expected_pwm8_file": "expected_pwm8_sha256"}
        for field, path in paths.items():
            if c.digest(path) != row[hash_fields[field]]:
                raise ValueError("Archived prepared input/output binding mismatch")
        stream, _ = repack(paths["stream_file"].read_bytes(), 9)
        path = out / f"case-{ordinal:02d}-sparse2-8000"
        command = [c.wsl_path(encoder), "decode", c.wsl_path(path.with_suffix(".s16le")), c.wsl_path(path.with_suffix(".u8"))]
        result = subprocess.run(c.native_command(command, args.distro), input=stream, capture_output=True)
        path.with_suffix(".stderr-private.json").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError("Sparse80 native V9 decode failed; numeric private error retained")
        if (path.with_suffix(".s16le").read_bytes() != paths["expected_pcm16_file"].read_bytes() or
                path.with_suffix(".u8").read_bytes() != paths["expected_pwm8_file"].read_bytes()):
            raise AssertionError("Lossless V9 repack changed incumbent PCM/PWM")
        path.with_suffix(".lpx").write_bytes(stream)
        target = np.fromfile(paths["target_file"], dtype="<i2")
        pcm = np.fromfile(path.with_suffix(".s16le"), dtype="<i2")
        pwm = np.fromfile(path.with_suffix(".u8"), dtype=np.uint8)
        driver = json.loads(result.stderr)
        if len(target) != row["samples"] or len(pcm) != len(target) or len(pwm) != len(target):
            raise AssertionError("Sparse80 complete geometry mismatch")
        speech = ordinal < 20
        measured = c.metrics(target, pcm, pwm, 8000, speech, evaluator)
        receipt = {"schema": 1, "phase": "incumbent_audit", "job": {"ordinal": ordinal,
                   "job_id": path.name, "mode": "sparse2", "sample_rate": 8000, "samples": len(target),
                   "kind": "speech" if speech else "music", "split": "tuning" if ordinal in c.TUNING else "heldout" if speech else "controls"},
                   "driver": driver, "metrics": measured, "declared_level": row["declared_level"],
                   "complete_original_bytes": row["encoded_bytes"], "original_cap": row["complete_byte_cap"],
                   "prepared_target_sha256": c.digest(paths["target_file"]), "original_stream_sha256": c.digest(paths["stream_file"]),
                   "v9_stream_sha256": c.digest(path.with_suffix(".lpx")), "exact_pcm16": True, "exact_pwm8": True,
                   "lossless_repacker_sha256": c.digest(tools / "speech_v9.py"), "encoder_sha256": c.digest(encoder)}
        c.json_write(path.with_suffix(".json"), receipt)
        receipts.append(path.with_suffix(".json").name)
    c.json_write(out / "run-private.json", {"schema": 1, "phase": "incumbent_audit", "completed": len(receipts),
                 "prospective_jobs": 27, "job_receipts": receipts, "firmware_manifest_sha256": c.digest(manifest_path)})
    print(json.dumps({"stage": "sparse2_audit_completed", "jobs": len(receipts), "exact_pcm16": len(receipts), "exact_pwm8": len(receipts)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare-wideband", "prepare-long"):
        p = sub.add_parser(name)
        p.add_argument("--source", required=True)
        p.add_argument("--baseline-build", required=True)
        p.add_argument("--output", required=True)
        p.set_defaults(func=prepare)
    p = sub.add_parser("audit-sparse2")
    p.add_argument("--firmware-manifest", required=True)
    p.add_argument("--encoder", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--distro", default="Ubuntu")
    p.set_defaults(func=audit_sparse)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
