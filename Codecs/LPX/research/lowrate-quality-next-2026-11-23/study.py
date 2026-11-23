#!/usr/bin/env python3
"""Prepare a new source-only holdout and reuse the frozen evaluation harness.

No runtime encoder is implemented in Python. This wrapper archives/builds the
native C++ API, prepares source references and delegates unchanged evaluation
to the previous study. Media and private manifests must stay under build/.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "v9-quality-all-2026-11-23"
sys.path.insert(0, str(SHARED))
import corpus as c

BASELINE = "ba02e453"


def original_key(row):
    receipt = row["selection_receipt"]
    if row["corpus"] == "fleurs":
        return ("fleurs", row["language"], receipt["official_split"], receipt["archive_member"])
    return ("vctk", receipt["member"])


def speaker_keys(row):
    if row["corpus"] != "vctk":
        return set()
    receipt = row["selection_receipt"]
    member = PurePosixPath(receipt["member"])
    return {("vctk_member_speaker", member.stem.split("_")[0]),
            ("vctk_anonymous_speaker", receipt["anonymous_speaker"])}


def original_hash(row):
    receipt = row["selection_receipt"]
    return receipt.get("original_sha256") or receipt.get("flac_sha256")


def known_bindings(paths):
    hashes, basenames, speakers, receipts = set(), set(), set(), []
    for path in map(Path, paths):
        path = path.resolve()
        manifest = c.json_read(path)
        bindings = []
        def walk(value, key=""):
            if isinstance(value, dict):
                for name, item in value.items():
                    walk(item, name)
            elif isinstance(value, list):
                for item in value:
                    walk(item, key)
            elif isinstance(value, str):
                if "sha256" in key and re.fullmatch("[a-fA-F0-9]{64}", value):
                    hashes.add(value.lower())
                if key in ("source", "reference", "original", "member", "archive_member", "path", "file"):
                    bindings.append(value)
                    basenames.add(PurePosixPath(value.replace("\\", "/").split("?")[0]).stem.lower())
                    speakers.update(s.lower() for s in re.findall(r"(?i)(?<![a-z0-9])p[0-9]{3}(?![0-9])", value))
        for row in manifest["source_records"]:
            walk(row)
        receipts.append({"path": str(path), "sha256": c.digest(path),
                         "cases": len(manifest["source_records"]), "source_bindings": bindings})
    return hashes, basenames, speakers, receipts


def freeze(args):
    # The shared test driver is part of the baseline recipe too. Refuse silent
    # drift while another worker edits production source in this worktree.
    relative = str((SHARED / "corpus_driver.cpp").relative_to(c.ROOT)).replace("\\", "/")
    original = subprocess.run(["git", "show", BASELINE + ":" + relative], cwd=c.ROOT,
                              capture_output=True, check=True).stdout
    if hashlib.sha256(original).hexdigest() != c.digest(SHARED / "corpus_driver.cpp"):
        raise ValueError("Shared native driver differs from the pinned baseline")
    args.commit = BASELINE
    c.freeze(args)


def prepare(args):
    out = c.private_path(args.output, fresh=True)
    old_path = Path(args.previous_primary).resolve()
    old_manifest = c.json_read(old_path)
    old = [row["source_record"] for row in old_manifest["source_records"]]
    if len(old) != 24:
        raise ValueError("Expected all 24 actual prior-primary bindings")
    excluded_pcm = {row["source_pcm_sha256"] for row in old}
    excluded_original = {original_hash(row) for row in old}
    excluded_original.discard(None)
    excluded_keys = {original_key(row) for row in old}
    excluded_speakers = set().union(*(speaker_keys(row) for row in old))
    known_hashes, known_basenames, known_speakers, known_receipts = known_bindings((args.known_regression, args.known_public))
    candidates, manifest_bindings = [], []
    available, rejected = Counter(), Counter()
    for path in map(Path, (args.fleurs_reserve, args.vctk_reserve)):
        path = path.resolve()
        source_manifest = c.json_read(path)
        if source_manifest["schema"] != "lpx-native-wideband-sources-v1":
            raise ValueError("Expected frozen original-rate reserve manifests")
        manifest_bindings.append({"path": str(path), "sha256": c.digest(path)})
        for row in source_manifest["cases"]:
            source_member = row["selection_receipt"].get("archive_member") or row["selection_receipt"].get("member")
            basename = PurePosixPath(source_member).stem.lower()
            original_speakers = {value.lower() for key, value in speaker_keys(row) if key == "vctk_member_speaker"}
            if (row["source_pcm_sha256"] in excluded_pcm or original_hash(row) in excluded_original
                    or original_key(row) in excluded_keys or speaker_keys(row) & excluded_speakers):
                rejected["prior_primary_source_or_speaker"] += 1
                continue
            pcm, rate = c.read_wav(Path(row["source"]))
            if (rate < 16000 or rate != row["native_rate"] or len(pcm) != row["native_samples"]
                    or not 4 <= len(pcm) / rate <= 8):
                rejected["source_geometry"] += 1
                continue
            actual_hash = hashlib.sha256(pcm.astype("<i2").tobytes()).hexdigest()
            if actual_hash != row["source_pcm_sha256"]:
                raise ValueError("Reserve source PCM changed")
            if (actual_hash in known_hashes or original_hash(row) in known_hashes
                    or c.digest(Path(row["source"])) in known_hashes
                    or basename in known_basenames or original_speakers & known_speakers):
                rejected["known_regression_or_public_binding"] += 1
                continue
            target8 = c.resample(pcm, rate, 8000)
            if hashlib.sha256(target8.astype("<i2").tobytes()).hexdigest() in known_hashes:
                rejected["known_prepared_pcm_duplicate"] += 1
                continue
            item = {"source_record": row, "pcm": pcm, "rate": rate,
                    "corpus": row["corpus"], "language": row["language"], "target8": target8}
            candidates.append(item)
            available[row["corpus"] + "/" + row["language"]] += 1
    selected, used_pcm, used_speakers = [], set(), set()
    for corpus, language, count in (("fleurs", "ru", 3), ("fleurs", "en", 3), ("vctk", "en", 6)):
        group = []
        for item in candidates:
            row = item["source_record"]
            if item["corpus"] != corpus or item["language"] != language:
                continue
            if row["source_pcm_sha256"] in used_pcm or speaker_keys(row) & used_speakers:
                continue
            group.append(item)
            used_pcm.add(row["source_pcm_sha256"])
            used_speakers.update(speaker_keys(row))
            if len(group) == count:
                break
        if len(group) != count:
            raise ValueError("Insufficient unseen complete sources for the fixed language/speaker quota")
        selected.extend(group)
    out.mkdir(parents=True)
    (out / "sources").mkdir()
    jobs, records = [], []
    for ordinal, item in enumerate(selected):
        row = item["source_record"]
        local_source = out / "sources" / f"native-{ordinal:02d}.wav"
        shutil.copyfile(row["source"], local_source)
        if c.digest(local_source) != c.digest(Path(row["source"])):
            raise AssertionError("Native-source snapshot changed bytes")
        records.append({"ordinal": ordinal, "source_record": dict(row, source=str(local_source)),
                        "reserve_source_path": row["source"], "native_source_file_sha256": c.digest(local_source),
                        "native_rate": item["rate"],
                        "native_samples": len(item["pcm"]), "corpus": item["corpus"],
                        "language": item["language"], "split": "heldout"})
        for rate, mode in ((8000, "k3"), (16000, "p4")):
            target = item["target8"] if rate == 8000 else c.resample(item["pcm"], item["rate"], rate)
            name = f"holdout-{ordinal:02d}-{rate}.s16le"
            (out / name).write_bytes(target.astype("<i2").tobytes())
            jobs.append({"job_id": f"holdout-{ordinal:02d}-{mode}-{rate}", "ordinal": ordinal,
                         "corpus": item["corpus"], "language": item["language"], "kind": "speech",
                         "split": "heldout", "mode": mode, "sample_rate": rate, "samples": len(target),
                         "target": name, "target_sha256": c.digest(out / name), "calls": 4,
                         "auto_quiet": False, "normalize": False, "size_allowance_percent": 0})
    baseline = c.private_path(args.baseline_build)
    build = c.json_read(baseline / "build-private.json")
    if build.get("commit") != BASELINE:
        raise ValueError("New study must use the exact current V3 baseline commit")
    metadata = {"schema": 1, "set": "lowrate_unseen_holdout", "jobs": jobs, "source_records": records,
                "source_manifests": manifest_bindings, "previous_primary_manifest": str(old_path),
                "previous_primary_manifest_sha256": c.digest(old_path),
                "previous_primary_cases_excluded": len(old), "lowrate_protocol_sha256": c.digest(HERE / "PROTOCOL.md"),
                "known_regression_and_public_provenance": known_receipts,
                "known_speaker_overlap_limit": "Older regression/public provenance has no stable speaker ID; binding/hash checks cannot prove speaker independence.",
                "lowrate_preparer_sha256": c.digest(__file__), "baseline_commit": BASELINE,
                "shared_metric_equations_unchanged": True, **c.study_metadata(baseline)}
    c.json_write(out / "all-prepared-private.json", metadata)
    c.json_write(out / "primary-manifest-private.json", dict(metadata, matrix_partition="primary_24"))
    for label, mode in (("strict3", "k3"), ("p4-16k", "p4")):
        manifest = dict(metadata, jobs=[job for job in jobs if job["mode"] == mode], matrix_partition=label)
        c.json_write(out / (label + "-manifest-private.json"), manifest)
    summary = {"stage": "unseen_holdout_sources_frozen", "cases": len(records),
               "previous_primary_excluded": len(old), "available_unseen_source_counts": dict(available),
               "known_provenance_records_checked": sum(row["cases"] for row in known_receipts),
               "known_provenance_hash_bindings": len(known_hashes),
               "recognized_old_vctk_speaker_bindings": len(known_speakers),
               "known_source_overlap_exclusions": rejected["known_regression_or_public_binding"] + rejected["known_prepared_pcm_duplicate"],
               "source_rate_counts": dict(Counter(row["native_rate"] for row in records)),
               "cohort_counts": dict(Counter(row["corpus"] + "/" + row["language"] for row in records)),
               "distinct_new_vctk_speakers": sum(row["corpus"] == "vctk" for row in records),
               "whole_duration_min_seconds": min(row["native_samples"] / row["native_rate"] for row in records),
               "whole_duration_max_seconds": max(row["native_samples"] / row["native_rate"] for row in records),
               "whole_duration_total_seconds": sum(row["native_samples"] / row["native_rate"] for row in records),
               "primary_jobs": 24, "strict3_jobs": 12, "p4_16k_jobs": 12, "holdout_encodes_started": 0}
    c.json_write(out / "availability-anonymous.json", summary)
    print(json.dumps(summary))


def run(args):
    manifest = c.json_read(c.private_path(args.manifest))
    if manifest["lowrate_protocol_sha256"] != c.digest(HERE / "PROTOCOL.md") or manifest["lowrate_preparer_sha256"] != c.digest(__file__):
        raise ValueError("New prospective protocol/preparer changed after source freeze")
    if manifest["baseline_commit"] != BASELINE:
        raise ValueError("Unexpected baseline")
    c.run(args)


def prepare_public(args):
    """Reuse exact prior V3 targets/outputs, retaining generation provenance."""
    out = c.private_path(args.output, fresh=True)
    previous = Path(args.previous_public).resolve()
    old_manifest = c.json_read(previous)
    old_results = Path(args.previous_v3_results).resolve()
    if len(old_manifest["jobs"]) != 24:
        raise ValueError("Expected the complete three-phrase/eight-setting tuning matrix")
    out.mkdir(parents=True)
    reference = out / "baseline-reference"
    reference.mkdir()
    for name in {row["target"] for row in old_manifest["jobs"]}:
        binding = next(row for row in old_manifest["jobs"] if row["target"] == name)
        if c.digest(previous.parent / name) != binding["target_sha256"]:
            raise ValueError("Public prepared target changed")
        shutil.copyfile(previous.parent / name, out / name)
    names, generation_hashes = [], set()
    for job in old_manifest["jobs"]:
        name = job["job_id"]
        original = c.json_read(old_results / (name + ".json"))
        for field in ("mode", "sample_rate", "samples", "calls", "auto_quiet", "normalize", "size_allowance_percent", "target_sha256"):
            if original["job"][field] != job[field]:
                raise ValueError("Old V3 output belongs to different public settings or input")
        for suffix, key in ((".lpx", "stream_sha256"), (".s16le", "pcm_sha256"), (".u8", "pwm_sha256")):
            source = old_results / (name + suffix)
            if c.digest(source) != original[key]:
                raise ValueError("Previous V3 stream/decoded output binding changed")
            shutil.copyfile(source, reference / source.name)
        receipt = {key: value for key, value in original.items() if key not in
                   ("admission", "speech_safety_admission", "spectral_admission", "v2_admission", "baseline_receipt_sha256", "admission_scope")}
        receipt.update(phase="baseline", job=job, original_generation_phase=original["phase"],
                       original_generation_receipt_sha256=c.digest(old_results / (name + ".json")),
                       baseline_equivalence_commit=BASELINE, previous_v3_reference_reused=True,
                       baseline_api_timing_is_historical=True)
        # Keep the true generation-binary hash; do not relabel an old encoding
        # as newly generated by the ba02 executable.
        generation_hashes.add(original["encoder_sha256"])
        c.json_write(reference / (name + ".json"), receipt)
        names.append(name + ".json")
    metadata = {"schema": 1, "set": "lowrate_public_tuning", "matrix_partition": "public_tuning",
                "jobs": old_manifest["jobs"], "source_records": old_manifest["source_records"],
                "previous_public_manifest_sha256": c.digest(previous),
                "baseline_commit": BASELINE, "lowrate_protocol_sha256": c.digest(HERE / "PROTOCOL.md"),
                "lowrate_preparer_sha256": c.digest(__file__), "baseline_reference_generation_hashes": sorted(generation_hashes),
                "baseline_reference_scope": "Exact target/stream/decoded bindings from the previous V3; generation and historical timing are retained.",
                **c.study_metadata(args.baseline_build)}
    c.json_write(out / "manifest-private.json", metadata)
    c.json_write(reference / "run-private.json", {"schema": 1, "phase": "baseline", "completed": 24,
                 "prospective_jobs": 24, "job_receipts": names,
                 "manifest_sha256": c.digest(out / "manifest-private.json"),
                 "encoder_generation_hashes": sorted(generation_hashes), "reference_reused": True})
    print(json.dumps({"stage": "public_tuning_reference_bound", "cases": 3, "jobs": 24,
                      "target_stream_pcm_pwm_bindings_verified": 24, "historical_generation_provenance_preserved": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze-baseline", help="No audio encoding; archive/build exact ba02e453")
    p.add_argument("--output", required=True)
    p.add_argument("--distro", default="Ubuntu")
    p.set_defaults(func=freeze)
    p = sub.add_parser("build-candidate", help="Run after the owner freezes the proposal source")
    p.add_argument("--source", default=str(c.ROOT / c.CODEC_REL))
    p.add_argument("--output", required=True)
    p.add_argument("--distro", default="Ubuntu")
    p.set_defaults(func=c.build)
    p = sub.add_parser("prepare", help="Freeze unseen source-only selection and actual-rate targets")
    p.add_argument("--previous-primary", required=True)
    p.add_argument("--fleurs-reserve", required=True)
    p.add_argument("--vctk-reserve", required=True)
    p.add_argument("--known-regression", required=True)
    p.add_argument("--known-public", required=True)
    p.add_argument("--baseline-build", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=prepare)
    p = sub.add_parser("prepare-public", help="Bind copied public targets and exact prior V3 reference outputs")
    p.add_argument("--previous-public", required=True)
    p.add_argument("--previous-v3-results", required=True)
    p.add_argument("--baseline-build", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=prepare_public)
    p = sub.add_parser("run", help="New holdout only after owner freeze; public tuning may precede it")
    p.add_argument("--manifest", required=True)
    p.add_argument("--encoder", required=True)
    p.add_argument("--phase", choices=("baseline", "candidate"), required=True)
    p.add_argument("--baseline")
    p.add_argument("--output", required=True)
    p.add_argument("--distro", default="Ubuntu")
    p.add_argument("--max-jobs", type=int, default=0)
    p.add_argument("--shard-index", type=int, default=0)
    p.add_argument("--shard-count", type=int, default=1)
    p.set_defaults(func=run)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
