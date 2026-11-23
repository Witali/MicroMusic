#!/usr/bin/env python3
"""Freeze source-only genuine-wideband primary and narrowband regressions."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

import corpus as c

GROUPS = [("fleurs", "ru", "tuning", 2), ("fleurs", "ru", "heldout", 4),
          ("fleurs", "en", "tuning", 2), ("fleurs", "en", "heldout", 4),
          ("vctk", "en", "tuning", 4), ("vctk", "en", "heldout", 8)]


def source_corpus(value):
    value = value.lower()
    return "vctk" if "vctk" in value else value


def primary(args):
    out = c.private_path(args.output, fresh=True)
    pools, input_bindings = [], []
    for name in args.manifest:
        path = Path(name).resolve()
        manifest = c.json_read(path)
        if manifest["schema"] != "lpx-native-wideband-sources-v1":
            raise ValueError("Expected an independently acquired original-rate source manifest")
        input_bindings.append({"path": str(path), "sha256": c.digest(path)})
        for source in manifest["cases"]:
            pcm, rate = c.read_wav(source["source"])
            native_samples = source.get("native_samples", len(pcm))
            if rate < 16000 or source["native_rate"] != rate or native_samples != len(pcm):
                raise ValueError("Native source header mismatch or genuinely narrowband source")
            raw_hash = hashlib.sha256(pcm.astype("<i2").tobytes()).hexdigest()
            if source.get("source_pcm_sha256", raw_hash) != raw_hash:
                raise ValueError("Source PCM changed after independent acquisition freeze")
            duration = len(pcm) / rate
            if not 4 <= duration <= 8:
                continue
            prepared = c.resample(pcm, rate, 16000)
            spectrum = c.full_band(prepared, prepared, 16000)
            if not any(b["source_supported"] and b["low_hz"] >= 4000 for b in spectrum["bands"]):
                continue
            pools.append({"source_record": source, "pcm": pcm, "rate": rate,
                          "corpus": source_corpus(source["corpus"]), "language": source["language"],
                          "split": source["split"], "source_pcm_sha256": raw_hash,
                          "source_band_diagnostic": spectrum,
                          "high6": any(b["source_supported"] and b["low_hz"] >= 6000 for b in spectrum["bands"])})
    selected_groups = []
    for corpus, language, split, count in GROUPS:
        group = [row for row in pools if (row["corpus"], row["language"], row["split"]) == (corpus, language, split)]
        if len(group) < count:
            raise ValueError("Insufficient eligible source cases for the prospective corpus/language/split quota")
        selected_groups.append((group[:count], group[count:]))
    # Source-only quota adjustment is fixed before viewing any codec output.
    selected = [row for group, _ in selected_groups for row in group]
    high_count = sum(row["high6"] for row in selected)
    for chosen, reserve in selected_groups:
        for candidate in (row for row in reserve if row["high6"]):
            if high_count >= 8:
                break
            replacement = next((i for i in reversed(range(len(chosen))) if not chosen[i]["high6"]), None)
            if replacement is None:
                break
            chosen[replacement] = candidate
            high_count += 1
    selected = [row for group, _ in selected_groups for row in group]
    out.mkdir(parents=True)
    jobs, records = [], []
    for ordinal, row in enumerate(selected):
        record = {key: value for key, value in row.items() if key != "pcm"}
        record["ordinal"] = ordinal
        records.append(record)
        for rate in (12000, 16000):
            target = c.resample(row["pcm"], row["rate"], rate)
            target_path = out / f"case-{ordinal:02d}-{rate}.s16le"
            target_path.write_bytes(target.astype("<i2").tobytes())
            for mode in ("p4", "p6"):
                jobs.append({"job_id": f"case-{ordinal:02d}-{mode}-{rate}", "ordinal": ordinal,
                             "corpus": row["corpus"], "language": row["language"], "kind": "speech",
                             "split": row["split"], "mode": mode, "sample_rate": rate, "samples": len(target),
                             "target": target_path.name, "target_sha256": c.digest(target_path), "calls": 4,
                             "auto_quiet": False, "normalize": False, "size_allowance_percent": 0})
    manifest = {"schema": 1, "set": "genuine_wideband_primary", "jobs": jobs, "source_records": records,
                "source_manifests": input_bindings, "source_preparer_sha256": c.digest(__file__),
                "quota_high6_required": 8, "quota_high6_observed": high_count, "quota_high6_met": high_count >= 8,
                **c.study_metadata(args.baseline_build)}
    c.json_write(out / "manifest-private.json", manifest)
    print(json.dumps({"stage": "wideband_primary_frozen", "cases": len(records), "jobs": len(jobs),
                      "split_counts": dict(Counter(row["split"] for row in selected)),
                      "native_rate_counts": dict(Counter(row["rate"] for row in selected)),
                      "source_supported_above6k": high_count, "source_total_seconds": sum(len(row["pcm"]) / row["rate"] for row in selected)}))


def narrowband(args):
    out = c.private_path(args.output, fresh=True)
    path = c.private_path(args.existing)
    original = c.json_read(path)
    jobs = [row for row in original["jobs"] if row["sample_rate"] == 8000]
    if len(jobs) != 108 or len({row["ordinal"] for row in jobs}) != 27:
        raise ValueError("Expected the exact27-source/4-setting narrowband regression")
    out.mkdir(parents=True)
    for name in {row["target"] for row in jobs}:
        binding = next(row for row in jobs if row["target"] == name)
        if c.digest(path.parent / name) != binding["target_sha256"]:
            raise ValueError("Existing frozen source target changed")
        shutil.copyfile(path.parent / name, out / name)
    result = {"schema": 1, "set": "narrowband_regression", "jobs": jobs,
              "source_records": original["source_records"], "original_frozen_manifest_sha256": c.digest(path),
              "source_preparer_sha256": c.digest(__file__), **c.study_metadata(args.baseline_build)}
    c.json_write(out / "manifest-private.json", result)
    print(json.dumps({"stage": "narrowband_regression_frozen", "cases": 27, "jobs": len(jobs),
                      "source_samples_per_case": 32000, "sample_rate": 8000}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("primary")
    p.add_argument("--manifest", action="append", required=True, help="Private native-source manifests in fixed source order")
    p.add_argument("--baseline-build", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=primary)
    p = sub.add_parser("narrowband")
    p.add_argument("--existing", required=True, help="The already frozen27-source/216-job target manifest")
    p.add_argument("--baseline-build", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=narrowband)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
