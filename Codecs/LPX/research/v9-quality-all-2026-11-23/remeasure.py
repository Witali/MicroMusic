#!/usr/bin/env python3
"""Remeasure exact frozen baseline artifacts under a new prospective evaluator.

This never reruns or changes the encoder. Target bytes, all decoded artifacts,
complete caps and original native timing are verified and retained. In
particular, old v1 receipts are not overwritten by the v2 diagnostic extension.
"""
import argparse
from pathlib import Path
import shutil
import time
import corpus as c
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--frozen-results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest_path = c.private_path(args.manifest)
    manifest = c.json_read(manifest_path)
    old = c.private_path(args.frozen_results)
    out = c.private_path(args.output, fresh=True)
    out.mkdir(parents=True)
    names = []
    for job in manifest["jobs"]:
        start = time.monotonic()
        name = job["job_id"]
        original = c.json_read(old / (name + ".json"))
        if (original["phase"] != "baseline" or original["encoder_sha256"] != manifest["baseline_binary_sha256"]
                or original["target_sha256"] != job["target_sha256"]
                or c.digest(manifest_path.parent / job["target"]) != job["target_sha256"]):
            raise ValueError("Remeasurement must retain exact baseline and prepared source bytes")
        for suffix, key in ((".lpx", "stream_sha256"), (".s16le", "pcm_sha256"), (".u8", "pwm_sha256")):
            if c.digest(old / (name + suffix)) != original[key]:
                raise ValueError("Frozen baseline artifact changed")
            shutil.copyfile(old / (name + suffix), out / (name + suffix))
        target = np.fromfile(manifest_path.parent / job["target"], dtype="<i2")
        pcm = np.fromfile(out / (name + ".s16le"), dtype="<i2")
        pwm = np.fromfile(out / (name + ".u8"), dtype=np.uint8)
        measured = c.metrics(target, pcm, pwm, job["sample_rate"], job["kind"] == "speech", Path(manifest["evaluator"]))
        for path in ("pcm16", "pwm8"):
            if measured[path]["error_energy"] != original["metrics"][path]["error_energy"]:
                raise AssertionError("Remeasurement changed the waveform reference")
            before, after = original["metrics"][path]["stoi"], measured[path]["stoi"]
            if (before is None) != (after is None) or before is not None and abs(before - after) > 1e-12:
                raise AssertionError("Remeasurement changed the STOI reference/membership")
        receipt = dict(original, job=job, metrics=measured, baseline_api_timing_reused_from_frozen_v1=True,
                       remeasurement_seconds=time.monotonic() - start,
                       original_frozen_receipt_sha256=c.digest(old / (name + ".json")),
                       diagnostics_version=manifest["diagnostics_version"])
        c.json_write(out / (name + ".json"), receipt)
        names.append(name + ".json")
    c.json_write(out / "run-private.json", {"schema": 1, "phase": "baseline", "manifest_sha256": c.digest(manifest_path),
                 "encoder_sha256": manifest["baseline_binary_sha256"], "completed": len(names),
                 "prospective_jobs": len(manifest["jobs"]), "job_receipts": names,
                 "native_outputs_and_timing_reused_exactly": True})
    print({"stage": "frozen_baseline_remeasured", "jobs": len(names), "native_outputs_unchanged": True})


if __name__ == "__main__":
    main()
