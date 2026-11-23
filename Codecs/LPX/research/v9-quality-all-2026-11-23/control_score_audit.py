#!/usr/bin/env python3
"""Separate mathematical guard parity from uncalibrated music intelligibility.

The frozen negative-control report deliberately has no speech STOI. The public
encoder ABI does use that mathematical term. This report recomputes it only
to expose the difference in score definitions; it is not a claim that STOI
measures music quality. No source, output, production score or gate is changed.
"""
import argparse
from pathlib import Path
import sys
import corpus as c
import numpy as np
from objective_metrics import score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    path = c.private_path(args.manifest)
    manifest = c.json_read(path)
    sys.path.insert(0, manifest["evaluator"])
    from standard_metrics import error_metrics
    baseline, candidate = c.private_path(args.baseline), c.private_path(args.candidate)
    groups = {}
    for job in manifest["jobs"]:
        if job["split"] != "controls":
            continue
        if job["mode"] not in ("p4", "p6", "k3", "k8"):
            raise ValueError("Unexpected control profile")
        target_path = path.parent / job["target"]
        if c.digest(target_path) != job["target_sha256"]:
            raise ValueError("Frozen target changed")
        target = np.fromfile(target_path, dtype="<i2")
        old = c.json_read(baseline / (job["job_id"] + ".json"))
        new = c.json_read(candidate / (job["job_id"] + ".json"))
        views = []
        for folder, row in ((baseline, old), (candidate, new)):
            metrics = {}
            for domain, suffix, key in (("pcm16", ".s16le", "pcm_sha256"), ("pwm8", ".u8", "pwm_sha256")):
                decoded = folder / (job["job_id"] + suffix)
                if c.digest(decoded) != row[key]:
                    raise ValueError("Decoded artifact changed")
                pcm = np.fromfile(decoded, dtype="<i2") if domain == "pcm16" else (np.fromfile(decoded, dtype=np.uint8).astype(np.int32) - 128) * 256
                value = error_metrics(target, pcm, speech=True, rate=job["sample_rate"])
                if value["error_energy"] != row["metrics"][domain]["error_energy"]:
                    raise AssertionError("Mathematical audit changed the waveform reference")
                metrics[domain] = dict(row["metrics"][domain], stoi=value["stoi"])
            views.append(metrics)
        math_before, math_after = score(views[0], views[0]), score(views[1], views[0])
        group = groups.setdefault(job["mode"], {"cases": 0, "mathematical_stoi_assessed_paths": 0,
                   "mathematical_stoi_floor_passed_cases": 0, "mathematical_score_passed_cases": 0,
                   "mathematical_baseline_score_sum": 0., "mathematical_candidate_score_sum": 0.,
                   "frozen_semantic_control_score_before_sum": 0., "frozen_semantic_control_score_after_sum": 0.,
                   "maximum_absolute_score_definition_difference": 0.})
        group["cases"] += 1
        stoi_passed = True
        for domain in ("pcm16", "pwm8"):
            a, b = views[0][domain]["stoi"], views[1][domain]["stoi"]
            if a is not None:
                group["mathematical_stoi_assessed_paths"] += 1
                stoi_passed &= b is not None and b >= a - 1e-12
        group["mathematical_stoi_floor_passed_cases"] += stoi_passed
        passed = math_after["score"] is not None and math_after["score"] <= math_before["score"] + 1e-12
        group["mathematical_score_passed_cases"] += passed
        if math_after["score"] is not None:
            group["mathematical_baseline_score_sum"] += math_before["score"]
            group["mathematical_candidate_score_sum"] += math_after["score"]
            group["maximum_absolute_score_definition_difference"] = max(group["maximum_absolute_score_definition_difference"],
                abs(math_after["score"] - new["v2_admission"]["candidate"]["score"]))
        group["frozen_semantic_control_score_before_sum"] += new["v2_admission"]["baseline"]["score"]
        group["frozen_semantic_control_score_after_sum"] += new["v2_admission"]["candidate"]["score"]
    answer = {"schema": 1, "scope": "Mathematical production-term parity only; no music/synthetic intelligibility claim.",
              "original_frozen_control_reports_unchanged": True, "groups": groups}
    c.json_write(Path(args.output), answer)
    print({"stage": "control_score_definitions_audited", "cases": sum(g["cases"] for g in groups.values()),
           "math_stoi_floor_passed": sum(g["mathematical_stoi_floor_passed_cases"] for g in groups.values()),
           "math_score_passed": sum(g["mathematical_score_passed_cases"] for g in groups.values())})


if __name__ == "__main__":
    main()
