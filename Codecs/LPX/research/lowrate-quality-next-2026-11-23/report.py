#!/usr/bin/env python3
"""Run the unchanged aggregate reducers with accurate second-study provenance.

This does not encode, select sources or change any score. Detailed pitch cases
and frame indices stay in the private work directory. The final JSON inherits
the shared reducer's anonymous allowlist; no source or artifact bindings leave
the private receipts.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import study as s

c = s.c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--label", choices=("public_prototype_v2", "public_final_v3", "public_pitch_guarded", "new_primary", "known_regression"), required=True)
    parser.add_argument("--guard-contract", help="Private source/binary/addendum binding created before guarded encoding")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = c.json_read(c.private_path(args.manifest))
    work = c.private_path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    common = ["--manifest", args.manifest, "--baseline", args.baseline, "--candidate", args.candidate]
    pitch = work / "pitch-aggregate.json"
    subprocess.run([sys.executable, str(s.SHARED / "pitch_tradeoffs.py"), *common,
                    "--output", str(work / "pitch-private.json"), "--aggregate-output", str(pitch)], check=True)
    aggregate = work / "all-metrics-aggregate.json"
    subprocess.run([sys.executable, str(s.SHARED / "final_report.py"), *common,
                    "--pitch-summary", str(pitch), "--output", str(aggregate)], check=True)
    answer = c.json_read(aggregate)
    answer["study"] = "lowrate_quality_next"
    answer["comparison"] = args.label
    answer["baseline_commit"] = s.BASELINE
    answer["scope"] = "Same source-level prepared PCM and complete caps; unchanged V3-derived score and metric equations. Objective comparisons and heuristic pitch, not perceived-quality percentages or true F0."
    historical = any(c.json_read(Path(args.baseline) / (job["job_id"] + ".json")).get("baseline_api_timing_is_historical", False)
                     for job in manifest["jobs"])
    answer["baseline_timings_reused_historical"] = historical
    answer["timing_scope"] = ("Reused baseline API times retain their historical generation; candidate ran under bounded concurrent work. This is not a fresh isolated speed benchmark."
                              if historical else "API wall times under bounded concurrent work, not an isolated speed benchmark.")
    if args.guard_contract:
        contract = c.json_read(c.private_path(args.guard_contract))
        if (contract["manifest_sha256"] != c.digest(args.manifest)
                or contract["pitch_guard_addendum_sha256"] != c.digest(s.HERE / "PITCH_GUARD.md")
                or contract["baseline_commit"] != s.BASELINE):
            raise ValueError("Guarded run contract no longer matches the frozen source/addendum")
        detail = c.json_read(work / "pitch-private.json")
        cases = {row["job_id"]: row for row in detail["cases_private"]}
        result = {"passed": True, "jobs": len(manifest["jobs"]), "failed_jobs": 0,
                  "source_freeze_commit": contract["candidate_source_freeze_commit"], "paths": {}}
        for job in manifest["jobs"]:
            receipt = c.json_read(Path(args.candidate) / (job["job_id"] + ".json"))
            if receipt["encoder_sha256"] != contract["candidate_binary_sha256"]:
                raise ValueError("Guarded candidate binary differs from its prospective contract")
            failed = False
            for domain in ("pcm16", "pwm8"):
                observations = cases[job["job_id"]]["paths"][domain]
                target = result["paths"].setdefault(domain, {"new_half_pitch": 0, "new_double_pitch": 0, "failed_cases": 0})
                bad = bool(observations["new_half_pitch"] or observations["new_double_pitch"])
                target["new_half_pitch"] += observations["new_half_pitch"]
                target["new_double_pitch"] += observations["new_double_pitch"]
                target["failed_cases"] += bad
                failed |= bad
            result["failed_jobs"] += failed
        result["passed"] = result["failed_jobs"] == 0
        answer["additional_octave_guard_verification"] = result
    c.json_write(Path(args.output), answer)
    print({"stage": "second_study_reported", "comparison": args.label, "jobs": answer["jobs"],
           "historical_baseline_timing": historical, "private_record_bindings_exported": False})


if __name__ == "__main__":
    main()
