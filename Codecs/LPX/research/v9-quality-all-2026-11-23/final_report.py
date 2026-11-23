#!/usr/bin/env python3
"""Allowlisted cohort reporting of all frozen metrics and their tradeoffs.

This only reduces existing receipts/frame arrays. It never encodes, changes a
score, fits gain/alignment, selects cases or exports private source identities,
paths, hashes, frame arrays or time indices. Empty diagnostic subsets stay
unassessed. Spectral powers use their fixed frame-count denominators.
"""
import argparse
import math
from pathlib import Path
import corpus as c

COUNT_FIELDS = ("frames", "active_reference_frames", "reference_period_frames", "paired_period_frames",
                "missing_decoded_period_frames", "within_tolerance_frames", "near_half_pitch_frames",
                "near_double_pitch_frames", "decoded_collapsed_active_frames")


def add(dest, key, value):
    dest[key] = dest.get(key, 0) + value


def maximum(dest, key, value):
    if value is not None:
        dest[key] = value if dest.get(key) is None else max(dest[key], value)
    else:
        dest.setdefault(key, None)


def sum_summary(dest, source):
    for key, value in source.items():
        if key in ("low_hz", "high_hz", "framewise_private"):
            continue
        if key == "noisy_unvoiced":
            sum_summary(dest.setdefault(key, {}), value)
        elif isinstance(value, (int, float)):
            add(dest, key, value)


def frame_spikes(arrays, noisy):
    transitions = [a or b for a, b in zip(noisy, noisy[1:])]
    result = {}
    for key, values in arrays.items():
        if key not in ("waveform_residual_power", "magnitude_residual_power", "magnitude_change_residual_power",
                       "envelope_error", "onset_error"):
            continue
        mask = transitions if key in ("magnitude_change_residual_power", "onset_error") else noisy
        result[key + "_max_abs"] = max(map(abs, values), default=None)
        result["noisy_" + key + "_max_abs"] = max((abs(value) for value, use in zip(values, mask) if use), default=None)
    return result


def high_arrays(bands, cutoff):
    chosen = [b["framewise_private"] for b in bands if b["low_hz"] >= cutoff]
    if not chosen:
        return None
    answer = {key: [sum(values) for values in zip(*(b[key] for b in chosen))]
              for key in ("source_power", "output_power", "waveform_residual_power", "magnitude_residual_power",
                          "magnitude_change_residual_power")}
    source, output = [list(map(math.sqrt, answer[key])) for key in ("source_power", "output_power")]
    answer["envelope_error"] = [b - a for a, b in zip(source, output)]
    answer["onset_error"] = [max(0., b - a) - max(0., d - e)
                             for a, b, e, d in zip(output, output[1:], source, source[1:])]
    return answer


def update_path(dest, metric):
    add(dest, "samples", metric["samples"])
    add(dest, "reference_energy", metric["reference_energy"])
    add(dest, "error_energy", metric["error_energy"])
    add(dest, "clips_or_rails", metric["clipped_samples"])
    maximum(dest, "max_abs_error_pcm16", metric["max_abs_error_pcm16"])
    if metric["stoi"] is not None:
        add(dest, "stoi_sum", metric["stoi"])
        add(dest, "stoi_assessed_cases", 1)
    for name in ("voice", "noise"):
        add(dest, "objective_" + name + "_sum", metric["objective_" + name])
    diagnostic = dest.setdefault("analysis8k_diagnostic", {})
    for name in ("within", "collapsed", "source_period_frames"):
        add(diagnostic, name, metric["objective_diagnostic"][name])
    for name in ("period", "shape"):
        value = metric["objective_diagnostic"][name]
        if value is not None:
            add(diagnostic, name + "_sum", value)
            add(diagnostic, name + "_assessed_cases", 1)
    native = dest.setdefault("native_rate_pitch_observations", {})
    for name in COUNT_FIELDS:
        add(native, name, metric["voice"][name])
    spectrum = dest.setdefault("v2_spectrum", {})
    for name, value in metric["v2_spectrum"].items():
        add(spectrum, name + "_sum", value)
    full = metric["full_band"]
    band_dest = dest.setdefault("frequency_bands", [{"low_hz": b["low_hz"], "high_hz": b["high_hz"]} for b in full["bands"]])
    temporal = metric["temporal"]
    noisy = temporal["source_framewise_private"]["noisy_unvoiced"]
    for b, t, target in zip(full["bands"], temporal["bands"], band_dest):
        add(target, "spectral_frames", full["frames"])
        add(target, "source_supported_cases", b["source_supported"])
        for name in ("source_power", "output_power", "complex_residual_power", "magnitude_residual_power"):
            add(target, name + "_frame_sum", b[name] * full["frames"])
        sum_summary(target.setdefault("temporal", {}), t)
        for name, value in frame_spikes(t["framewise_private"], noisy).items():
            maximum(target.setdefault("frame_spikes", {}), name, value)
    highs = dest.setdefault("high_bands_from_hz", {})
    for cutoff, t in temporal["high_bands_from_hz"].items():
        if t is None:
            continue
        target = highs.setdefault(cutoff, {})
        sum_summary(target.setdefault("temporal", {}), t)
        for name, value in frame_spikes(high_arrays(temporal["bands"], int(cutoff)), noisy).items():
            maximum(target.setdefault("frame_spikes", {}), name, value)


def per_case_spikes(metric):
    temporal = metric["temporal"]
    noisy = temporal["source_framewise_private"]["noisy_unvoiced"]
    results = {}
    for band in temporal["bands"]:
        results["band_" + str(band["low_hz"])] = frame_spikes(band["framewise_private"], noisy)
    for cutoff in temporal["high_bands_from_hz"]:
        arrays = high_arrays(temporal["bands"], int(cutoff))
        if arrays is not None:
            results["high_" + cutoff] = frame_spikes(arrays, noisy)
    return results


def finish_path(path, cases):
    n, reference, error = path["samples"], path["reference_energy"], path["error_energy"]
    path["pooled_rmse_pcm16"] = math.sqrt(error / n)
    path["pooled_ser_db"] = 10 * math.log10(reference / error) if reference > 0 and error > 0 else None
    path["pooled_ser_status"] = "finite" if reference > 0 and error > 0 else "perfect" if error == 0 else "zero_reference"
    path["reference_rms_pcm16"] = math.sqrt(reference / n)
    path["max_abs_error_percent_fs"] = path["max_abs_error_pcm16"] * 100 / 32768
    path["stoi_assessed_cases"] = path.get("stoi_assessed_cases", 0)
    path["stoi_mean_assessed"] = path.get("stoi_sum", 0) / path["stoi_assessed_cases"] if path["stoi_assessed_cases"] else None
    for name in ("voice", "noise"):
        path["objective_" + name + "_mean"] = path["objective_" + name + "_sum"] / cases
    for name in ("period", "shape"):
        count = path["analysis8k_diagnostic"].get(name + "_assessed_cases", 0)
        path["analysis8k_diagnostic"][name + "_mean_assessed"] = path["analysis8k_diagnostic"].get(name + "_sum", 0) / count if count else None
    for name, value in list(path["v2_spectrum"].items()):
        path["v2_spectrum"][name.removesuffix("_sum") + "_case_mean"] = value / cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--pitch-summary")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = c.json_read(c.private_path(args.manifest))
    baseline, candidate = c.private_path(args.baseline), c.private_path(args.candidate)
    groups = {}
    for job in manifest["jobs"]:
        if job["split"] not in ("tuning", "heldout", "controls", "continuous_long", "native_wideband_control", "public_pilot"):
            raise ValueError("Only anonymous allowlisted cohort labels can be exported")
        if job["mode"] not in ("p4", "p6", "k3", "k8") or job["sample_rate"] not in (8000, 12000, 16000):
            raise ValueError("Unexpected profile/rate")
        a = c.json_read(baseline / (job["job_id"] + ".json"))
        b = c.json_read(candidate / (job["job_id"] + ".json"))
        if a["target_sha256"] != job["target_sha256"] or b["target_sha256"] != job["target_sha256"]:
            raise ValueError("Source binding changed")
        for name in ("legacy_cap", "final_cap"):
            if a["driver"][name] != b["driver"][name]:
                raise ValueError("Complete declared byte budget changed")
        for row in (a, b):
            if (row["driver"]["samples"] != job["samples"] or row["driver"]["sample_rate"] != job["sample_rate"]
                    or not row["driver"]["native_decoder_exact"] or row["driver"]["file_bytes"] > row["driver"]["final_cap"]):
                raise ValueError("Complete decoder geometry/budget verification failed")
        key = "/".join((job["split"], job["mode"], str(job["sample_rate"])))
        group = groups.setdefault(key, {"cases": 0, "changed_streams": 0, "changed_pcm16": 0, "v2_admitted": 0,
                    "file_growth_cases": 0, "file_shrink_cases": 0, "file_equal_cases": 0,
                    "minimum_file_byte_delta": None, "maximum_file_byte_delta": None,
                    "baseline": {"file_bytes": 0, "api_wall_seconds": 0., "selection_score_sum": 0., "paths": {}},
                    "candidate": {"file_bytes": 0, "api_wall_seconds": 0., "selection_score_sum": 0., "paths": {}},
                    "selection_score_assessed_cases": 0, "selection_score_floor_failures": 0,
                    "tradeoff_cases": {}, "spike_worsened_cases": {}, "admission_failures": {},
                    "production_control_score_equivalent": job["split"] != "controls"})
        group["cases"] += 1
        group["changed_streams"] += a["stream_sha256"] != b["stream_sha256"]
        group["changed_pcm16"] += a["pcm_sha256"] != b["pcm_sha256"]
        delta = b["driver"]["file_bytes"] - a["driver"]["file_bytes"]
        group["file_growth_cases"] += delta > 0
        group["file_shrink_cases"] += delta < 0
        group["file_equal_cases"] += delta == 0
        group["minimum_file_byte_delta"] = delta if group["minimum_file_byte_delta"] is None else min(delta, group["minimum_file_byte_delta"])
        maximum(group, "maximum_file_byte_delta", delta)
        group["v2_admitted"] += b["v2_admission"]["passed"]
        if b["v2_admission"]["candidate"]["score"] is not None:
            group["selection_score_assessed_cases"] += 1
            add(group["baseline"], "selection_score_sum", b["v2_admission"]["baseline"]["score"])
            add(group["candidate"], "selection_score_sum", b["v2_admission"]["candidate"]["score"])
        else:
            group["selection_score_floor_failures"] += 1
        for reason in b["v2_admission"]["failures"]:
            add(group["admission_failures"], reason, 1)
        for name, row in (("baseline", a), ("candidate", b)):
            add(group[name], "file_bytes", row["driver"]["file_bytes"])
            add(group[name], "api_wall_seconds", row["driver"]["api_encode_seconds"])
            for domain in ("pcm16", "pwm8"):
                update_path(group[name]["paths"].setdefault(domain, {}), row["metrics"][domain])
        for domain in ("pcm16", "pwm8"):
            old, new = a["metrics"][domain], b["metrics"][domain]
            for name in ("error_energy", "max_abs_error_pcm16", "clipped_samples", "objective_voice", "objective_noise"):
                add(group["tradeoff_cases"], domain + "/" + name + "_worsened", new[name] > old[name])
            for component, ratio in b["v2_admission"]["candidate"]["relative_components"][domain].items():
                add(group["tradeoff_cases"], domain + "/relative_" + component + "_worsened", ratio is None or ratio > 1 + 1e-12)
            before, after = per_case_spikes(old), per_case_spikes(new)
            for band, values in before.items():
                for name, value in values.items():
                    other = after[band][name]
                    if (value is None) != (other is None):
                        raise AssertionError("Source-frozen spike subset membership changed")
                    if value is not None:
                        add(group["spike_worsened_cases"], domain + "/" + band + "/" + name, other > value)
    for group in groups.values():
        for phase in ("baseline", "candidate"):
            count = group["selection_score_assessed_cases"]
            group[phase]["selection_score_mean_assessed"] = group[phase]["selection_score_sum"] / count if count else None
            for path in group[phase]["paths"].values():
                finish_path(path, group["cases"])
    answer = {"schema": "lpx-frozen-quality-all-metrics-v1", "jobs": len(manifest["jobs"]),
              "complete": True, "source_cases": len(manifest["source_records"]),
              "scope": "Frozen V3, same prepared PCM/complete budgets. Objective metrics and heuristic pitch, not perceived-quality percentages or true F0.",
              "timing_scope": "API wall time under concurrent bounded work, not an isolated speed benchmark.",
              "groups": groups}
    if args.pitch_summary:
        pitch = c.json_read(c.private_path(args.pitch_summary))
        if pitch["completed_jobs"] != len(manifest["jobs"]):
            raise ValueError("Pitch report must retain the complete fixed denominator")
        answer["native_pitch_frame_tradeoffs"] = pitch["groups"]
    c.json_write(Path(args.output), answer)
    print({"stage": "all_frozen_metrics_exported", "jobs": answer["jobs"], "groups": len(groups), "private_arrays_exported": False})


if __name__ == "__main__":
    main()
