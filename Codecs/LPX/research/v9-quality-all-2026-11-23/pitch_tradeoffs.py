#!/usr/bin/env python3
"""Audit frozen native-rate pitch observations without changing any threshold.

The internal antialiased 8 kHz view and independent native-rate observations
remain distinct. Neither is validated true F0. Only changed outputs need new
frame masks; identical outputs have exactly zero lost/gained observations.
Detailed cases, time indices and A/B paths stay in ignored private build/.
"""
import argparse
from pathlib import Path
import sys
import corpus as c
import numpy as np


COUNT_FIELDS = ("reference_period_frames", "within_tolerance_frames", "missing_decoded_period_frames",
                "near_half_pitch_frames", "near_double_pitch_frames", "decoded_collapsed_active_frames")


def masks(source, decoded, tolerance):
    paired = source.voiced & decoded.voiced
    cents = np.full(len(source.voiced), np.nan)
    cents[paired] = 1200 * np.log2(decoded.hz[paired] / source.hz[paired])
    return {"within": paired & (abs(cents) <= tolerance),
            "missing": source.voiced & ~decoded.voiced,
            "half": paired & (abs(cents + 1200) <= tolerance),
            "double": paired & (abs(cents - 1200) <= tolerance)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--aggregate-output", required=True)
    args = parser.parse_args()
    path = c.private_path(args.manifest)
    manifest = c.json_read(path)
    baseline, candidate = c.private_path(args.baseline), c.private_path(args.candidate)
    sys.path.insert(0, manifest["evaluator"])
    from voice_character import PitchSettings, track_pitch
    cache, groups, cases = {}, {}, []
    for job in manifest["jobs"]:
        receipt_path = candidate / (job["job_id"] + ".json")
        if not receipt_path.exists():
            continue
        old = c.json_read(baseline / (job["job_id"] + ".json"))
        new = c.json_read(receipt_path)
        if old["target_sha256"] != job["target_sha256"] or new["target_sha256"] != job["target_sha256"]:
            raise ValueError("Pitch audit must retain the same source binding")
        case = {"job_id": job["job_id"], "ordinal": job["ordinal"], "split": job["split"],
                "mode": job["mode"], "sample_rate": job["sample_rate"], "paths": {},
                "prepared_reference": str(path.parent / job["target"]),
                "baseline_lpx": str(baseline / (job["job_id"] + ".lpx")),
                "candidate_lpx": str(candidate / (job["job_id"] + ".lpx"))}
        for domain, suffix, hash_key in (("pcm16", ".s16le", "pcm_sha256"), ("pwm8", ".u8", "pwm_sha256")):
            a, b = old["metrics"][domain]["voice"], new["metrics"][domain]["voice"]
            if a["settings"] != b["settings"] or a["reference_period_frames"] != b["reference_period_frames"]:
                raise ValueError("Native source pitch mask/settings changed")
            key = "/".join((job["split"], job["mode"], str(job["sample_rate"]), domain))
            group = groups.setdefault(key, {"cases": 0, "changed_cases": 0, "cases_with_lost_matches": 0,
                         "cases_with_net_match_decrease": 0, "lost_matches": 0, "gained_matches": 0,
                         "new_missing_voicing": 0, "new_half_pitch": 0, "new_double_pitch": 0,
                         **{prefix + field: 0 for prefix in ("before_", "after_") for field in COUNT_FIELDS}})
            group["cases"] += 1
            for field in COUNT_FIELDS:
                group["before_" + field] += a[field]
                group["after_" + field] += b[field]
            group["cases_with_net_match_decrease"] += b["within_tolerance_frames"] < a["within_tolerance_frames"]
            details = {"changed": old[hash_key] != new[hash_key], "before": {field: a[field] for field in COUNT_FIELDS},
                       "after": {field: b[field] for field in COUNT_FIELDS},
                       "internal_analysis8k_before": old["metrics"][domain].get("objective_diagnostic"),
                       "internal_analysis8k_after": new["metrics"][domain].get("objective_diagnostic"),
                       "lost_matches": 0, "gained_matches": 0, "new_missing_voicing": 0,
                       "new_half_pitch": 0, "new_double_pitch": 0, "lost_frame_indices_private": []}
            if details["changed"]:
                group["changed_cases"] += 1
                target = path.parent / job["target"]
                if c.digest(target) != job["target_sha256"]:
                    raise ValueError("Source target changed")
                cache_key = (job["target"], job["sample_rate"])
                settings = PitchSettings(**a["settings"])
                if cache_key not in cache:
                    cache[cache_key] = track_pitch(np.fromfile(target, dtype="<i2"), settings)
                source = cache[cache_key]
                tracks = []
                for folder, receipt in ((baseline, old), (candidate, new)):
                    decoded = folder / (job["job_id"] + suffix)
                    if c.digest(decoded) != receipt[hash_key]:
                        raise ValueError("Decoded artifact changed")
                    pcm = np.fromfile(decoded, dtype="<i2") if domain == "pcm16" else (np.fromfile(decoded, dtype=np.uint8).astype(np.int32) - 128) * 256
                    tracks.append(track_pitch(pcm, settings))
                before, after = [masks(source, result, settings.tolerance_cents) for result in tracks]
                if (int(before["within"].sum()) != a["within_tolerance_frames"] or
                        int(after["within"].sum()) != b["within_tolerance_frames"]):
                    raise AssertionError("Recomputed native observations differ from frozen diagnostic")
                differences = {"lost_matches": before["within"] & ~after["within"],
                               "gained_matches": after["within"] & ~before["within"],
                               "new_missing_voicing": after["missing"] & ~before["missing"],
                               "new_half_pitch": after["half"] & ~before["half"],
                               "new_double_pitch": after["double"] & ~before["double"]}
                for name, mask in differences.items():
                    details[name] = int(mask.sum())
                    group[name] += details[name]
                group["cases_with_lost_matches"] += details["lost_matches"] > 0
                details["lost_frame_indices_private"] = np.flatnonzero(differences["lost_matches"]).tolist()
            case["paths"][domain] = details
        cases.append(case)
    worst_tuning = [row for row in cases if row["split"] == "tuning" and any(value["lost_matches"] or value["new_half_pitch"]
                                      or value["new_double_pitch"] or value["new_missing_voicing"] for value in row["paths"].values())]
    worst_tuning.sort(key=lambda row: tuple(-sum(value[name] for value in row["paths"].values())
                                           for name in ("new_half_pitch", "lost_matches", "new_missing_voicing", "new_double_pitch")))
    aggregate = {"schema": 1, "completed_jobs": len(cases), "prospective_jobs": len(manifest["jobs"]),
                 "scope": "Native-rate source-frozen YIN observations, not true F0; same 100-cent threshold and 80/20ms geometry.",
                 "groups": groups}
    c.json_write(c.private_path(args.output), dict(aggregate, cases_private=cases, worst_tuning_private=worst_tuning,
                                                  evaluator_sha256=c.digest(__file__), manifest_sha256=c.digest(path)))
    c.json_write(c.private_path(args.aggregate_output), aggregate)
    print({"stage": "native_pitch_tradeoffs_audited", "jobs": len(cases), "worst_tuning_cases": len(worst_tuning),
           "lost_matches_across_job_paths": sum(row["lost_matches"] for row in groups.values()),
           "new_half_pitch_across_job_paths": sum(row["new_half_pitch"] for row in groups.values())})


if __name__ == "__main__":
    main()
