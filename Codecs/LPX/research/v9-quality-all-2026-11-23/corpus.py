#!/usr/bin/env python3
"""Private corpus orchestration and independent evaluation, not an LPX encoder.

All inputs and receipts belong below ignored build/. Only export's anonymous
allowlist is suitable for a public research summary. See PROTOCOL.md first.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import wave

for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[_key] = "1"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CODEC_REL = Path("Codecs/LPX/01_ACTIVE_Q0_CODEC")
COMMIT = "f282950c44f01793f55e2fad6c4fe5cf66cdfd2f"
SETTINGS = [(p, r) for r in (8000, 12000, 16000) for p in ("p4", "p6")] + [("k3", 8000), ("k8", 8000)]
TUNING = {0, 1, 2, 3, 8, 9, 10, 11, 16, 19}
FLAGS = ["-O3", "-std=c++11", "-ffp-contract=off", "-DLPX_ADAPTIVE_ENCODER=1",
         "-DLPX4_ENABLE_ASM=0", "-DLPX4_FLOAT_SYNTHESIS=0", "-DLPX4_ENABLE_SPEECH=1",
         "-DLPX4_ENABLE_SPEECH_COMPACT=1", "-DLPX4_COMPACT_ONLY=1", "-DLPX4_COMPACT_VERSION=9",
         "-DLPX4_SAMPLE_RATE=0", "-DLPX4_EXTENDED_SAMPLE_RATES=1", "-DLPX4_ENABLE_WIDE_V9=1"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def json_write(path, value):
    path = Path(path)
    pending = path.with_suffix(path.suffix + ".partial")
    pending.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    pending.replace(path)


def private_path(path, fresh=False):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / "build"):
        raise ValueError("Private inputs and outputs must remain under this worktree's ignored build/")
    if fresh and path.exists():
        raise ValueError("A freeze/prepare/build destination must be new; preserve earlier evidence")
    return path


def wsl_path(path):
    path = str(Path(path).resolve()).replace("\\", "/")
    if len(path) > 2 and path[1:3] == ":/":
        return "/mnt/" + path[0].lower() + path[2:]
    return path


def native_command(args, distro):
    if os.name == "nt":
        return ["wsl", "-d", distro, "--", *args]
    return args


def source_files(directory):
    return {str(p.relative_to(directory)).replace("\\", "/"): digest(p)
            for p in sorted(Path(directory).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def compile_driver(out, codec, distro):
    driver = out / "corpus_driver.cpp"
    shutil.copyfile(HERE / "corpus_driver.cpp", driver)
    units = [codec / "src/Lpx4HybridCore.cpp"]
    units += sorted(p for p in (codec / "host").glob("*.cpp") if p.name != "encode_lpx.cpp")
    binary = out / "corpus_driver"
    command = ["g++", *FLAGS, "-I" + wsl_path(codec / "src"), "-I" + wsl_path(codec / "host"),
               *(wsl_path(p) for p in units), wsl_path(driver), "-o", wsl_path(binary)]
    start = time.monotonic()
    result = subprocess.run(native_command(command, distro), capture_output=True)
    (out / "compile-private.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("Native compile failed; details retained only in private build log")
    compiler = subprocess.run(native_command(["g++", "--version"], distro), capture_output=True, check=True)
    (out / "compiler-private.txt").write_bytes(compiler.stdout)
    receipt = {"schema": 1, "binary": binary.name, "binary_sha256": digest(binary),
               "driver_sha256": digest(driver), "flags": FLAGS, "distro": distro,
               "compile_seconds": time.monotonic() - start,
               "source_sha256": source_files(codec), "compiler_sha256": hashlib.sha256(compiler.stdout).hexdigest()}
    json_write(out / "build-private.json", receipt)
    return receipt


def freeze(args):
    out = private_path(args.output, fresh=True)
    out.mkdir(parents=True)
    paths = [str(CODEC_REL / part).replace("\\", "/") for part in ("host", "src")]
    paths += [str(CODEC_REL / "tools" / name).replace("\\", "/")
              for name in ("standard_metrics.py", "voice_character.py", "pcm16_wav.py")]
    archive = subprocess.run(["git", "archive", "--format=tar", args.commit, *paths],
                             cwd=ROOT, capture_output=True, check=True).stdout
    source = out / "source"
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar.getmembers():
            destination = (source / member.name).resolve()
            if not destination.is_relative_to(source) or member.issym() or member.islnk():
                raise ValueError("Unsafe source archive member")
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(tar.extractfile(member).read())
    receipt = compile_driver(out, source / CODEC_REL, args.distro)
    receipt.update(commit=args.commit, archive_sha256=hashlib.sha256(archive).hexdigest())
    json_write(out / "build-private.json", receipt)
    print(json.dumps({"stage": "frozen_baseline_built", "source_files": len(receipt["source_sha256"]),
                      "compile_seconds": receipt["compile_seconds"]}))


def build(args):
    out = private_path(args.output, fresh=True)
    out.mkdir(parents=True)
    source = Path(args.source).resolve()
    codec = out / "source" / CODEC_REL
    codec.mkdir(parents=True)
    before = source_files(source / "host") | {"src/" + k: v for k, v in source_files(source / "src").items()}
    for part in ("host", "src"):
        shutil.copytree(source / part, codec / part)
    after = source_files(source / "host") | {"src/" + k: v for k, v in source_files(source / "src").items()}
    if before != after:
        raise RuntimeError("Source changed during snapshot; retry into a fresh build directory")
    receipt = compile_driver(out, codec, args.distro)
    print(json.dumps({"stage": "candidate_built", "source_files": len(receipt["source_sha256"]),
                      "compile_seconds": receipt["compile_seconds"]}))


def read_wav(path):
    import numpy as np
    with wave.open(str(path), "rb") as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2 or stream.getcomptype() != "NONE":
            raise ValueError("Source must be uncompressed mono PCM16 WAV")
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").copy(), stream.getframerate()


def resample(pcm, old, new):
    import numpy as np
    from scipy.signal import resample_poly
    if old == new:
        return pcm.copy()
    divisor = math.gcd(old, new)
    result = resample_poly(pcm.astype(np.float64), new // divisor, old // divisor,
                           window=("kaiser", 5.0), padtype="constant", cval=0)
    expected = (len(pcm) * new + old - 1) // old
    if len(result) != expected:
        raise AssertionError("Unexpected complete resampling length")
    return np.clip(np.rint(result), -32768, 32767).astype("<i2")


def study_metadata(baseline):
    import numpy as np
    import scipy
    import pystoi
    baseline = private_path(baseline)
    evaluator = baseline / "source" / CODEC_REL / "tools"
    return {"protocol_sha256": digest(HERE / "PROTOCOL.md"), "harness_sha256": digest(__file__),
            "wideband_protocol_sha256": digest(HERE / "PROTOCOL_WIDEBAND.md"),
            "temporal_evaluator_sha256": digest(HERE / "temporal_metrics.py"), "diagnostics_version": 2,
            "objective_evaluator_sha256": digest(HERE / "objective_metrics.py"),
            "evaluator": str(evaluator), "evaluator_sha256": source_files(evaluator),
            "baseline_build": str(baseline), "baseline_binary_sha256": digest(baseline / "corpus_driver"),
            "numpy_version": np.__version__, "scipy_version": scipy.__version__, "pystoi_version": pystoi.__version__,
            "resampling": {"algorithm": "scipy.signal.resample_poly", "window": ["kaiser", 5.0],
                           "padtype": "constant", "cval": 0, "rounding": "numpy.rint_then_pcm16_clip"}}


def prepare(args):
    import numpy as np
    import scipy
    import pystoi
    out = private_path(args.output, fresh=True)
    out.mkdir(parents=True)
    baseline = private_path(args.baseline_build)
    evaluator = baseline / "source" / CODEC_REL / "tools"
    source_map = []
    if args.set == "pilot":
        for i, relative in enumerate(("web-player/audio/originals/chego.wav",
                                      "web-player/audio/originals/otvechaesh.wav",
                                      "web-player/audio/lpx-bread/original.wav")):
            source_map.append({"ordinal": i, "source": str(ROOT / relative), "kind": "speech", "split": "public_pilot"})
    else:
        source_map = json_read(args.source_map)
        if len(source_map) != 27 or {x["ordinal"] for x in source_map} != set(range(27)):
            raise ValueError("Primary matrix must contain the exact 27 established source bindings")
    records, jobs = [], []
    for row in source_map:
        ordinal = row["ordinal"]
        source = Path(row["source"])
        pcm, rate = read_wav(source)
        original = pcm.astype("<i2").tobytes()
        if args.set == "primary":
            if len(pcm) != 32000 or rate != 8000 or hashlib.sha256(original).hexdigest() != row["source_binding"]["reference_sha256"]:
                raise ValueError("Original 27-case PCM binding mismatch")
        base = resample(pcm, rate, 8000)
        split = row.get("split") or ("tuning" if ordinal in TUNING else "heldout" if ordinal < 20 else "controls")
        record = {"ordinal": ordinal, "source": str(source), "source_file_sha256": digest(source),
                  "source_pcm_sha256": hashlib.sha256(original).hexdigest(), "source_rate": rate,
                  "source_samples": len(pcm), "kind": row["kind"], "split": split,
                  "established_binding": row if args.set == "primary" else None}
        records.append(record)
        for actual in (8000, 12000, 16000):
            target = resample(base, 8000, actual)
            name = f"case-{ordinal:02d}-{actual}.s16le"
            (out / name).write_bytes(target.astype("<i2").tobytes())
            for mode, target_rate in SETTINGS:
                if target_rate != actual:
                    continue
                jobs.append({"job_id": f"case-{ordinal:02d}-{mode}-{actual}", "ordinal": ordinal,
                             "kind": row["kind"], "split": split, "mode": mode, "sample_rate": actual,
                             "samples": len(target), "target": name, "target_sha256": digest(out / name),
                             "calls": 4, "auto_quiet": False, "normalize": False, "size_allowance_percent": 0})
    manifest = {"schema": 1, "set": args.set, "jobs": jobs, "source_records": records, **study_metadata(baseline)}
    json_write(out / "manifest-private.json", manifest)
    print(json.dumps({"stage": "targets_frozen", "set": args.set, "cases": len(records), "jobs": len(jobs),
                      "samples_by_rate": {str(rate): sum(j["samples"] for j in jobs if j["sample_rate"] == rate) for rate in (8000, 12000, 16000)}}))


def full_band(reference, decoded, rate):
    """Independent native-rate reference for the prospectively fixed guard."""
    import numpy as np
    length, hop = 512, 256
    window = np.hanning(length)
    starts = np.arange(-hop, len(reference), hop)
    weight = np.full(length // 2 + 1, 2.)
    weight[0] = weight[-1] = 1.
    band_count = rate // 2000
    band = np.minimum(np.arange(length // 2 + 1) * rate // (length * 1000), band_count - 1)
    powers = np.zeros((4, band_count), dtype=np.float64)
    padded = [np.pad(np.asarray(x, dtype=np.float64), (hop, length)) for x in (reference, decoded)]
    for start in starts:
        a, b = [np.fft.rfft(x[start + hop:start + hop + length] * window) for x in padded]
        arrays = (abs(a) ** 2, abs(b) ** 2, abs(a - b) ** 2, (abs(a) - abs(b)) ** 2)
        for i, values in enumerate(arrays):
            powers[i] += np.bincount(band, weights=values * weight, minlength=band_count)
    powers /= len(starts) * length * np.dot(window, window)
    total_reference = float(powers[0].sum())
    bands = []
    for i in range(band_count):
        source, output, complex_error, magnitude_error = map(float, powers[:, i])
        ratio = output / source if source > 0 else None
        bands.append({"low_hz": i * 1000, "high_hz": (i + 1) * 1000,
                      "source_power": source, "output_power": output,
                      "complex_residual_power": complex_error, "magnitude_residual_power": magnitude_error,
                      "normalized_magnitude_error": magnitude_error / (source if source > 0 else 1.),
                      "energy_retention": ratio,
                      "energy_retention_db": 10 * math.log10(ratio) if ratio and ratio > 0 else None,
                      "capped_amplitude_retention": min(1., math.sqrt(ratio)) if ratio is not None else None,
                      "source_supported": total_reference > 0 and source > 1e-4 * total_reference})
    return {"sample_rate": rate, "nyquist_hz": rate // 2, "fft_samples": length, "hop_samples": hop,
            "frames": len(starts), "source_power": total_reference, "output_power": float(powers[1].sum()),
            "complex_residual_power": float(powers[2].sum()), "magnitude_residual_power": float(powers[3].sum()),
            "normalized_magnitude_error": float(powers[3].sum()) / (total_reference if total_reference > 0 else 1.),
            "bands": bands}


def metrics(target, pcm, pwm, rate, speech, evaluator):
    import numpy as np
    sys.path.insert(0, str(evaluator))
    from standard_metrics import error_metrics, pwm_duties
    from voice_character import PitchSettings, track_pitch, compare_voice
    from temporal_metrics import temporal_metrics
    from objective_metrics import QualityObjective
    if not np.array_equal(pwm, pwm_duties(pcm)):
        raise AssertionError("Independent PWM transfer mismatch")
    settings = PitchSettings(rate=rate, frame_samples=rate * 80 // 1000, hop_samples=rate * 20 // 1000)
    source_track = track_pitch(target, settings)
    objective = QualityObjective(target, rate)
    answer = {}
    for key, decoded in (("pcm16", pcm), ("pwm8", (pwm.astype(np.int32) - 128) * 256)):
        answer[key] = error_metrics(target, decoded, speech=speech, rate=rate)
        answer[key]["voice"] = compare_voice(target, decoded, settings, reference_track=source_track)
        answer[key]["clipped_samples"] = int(np.count_nonzero((decoded <= -32768) | (decoded >= 32767))) if key == "pcm16" else int(np.count_nonzero((pwm == 0) | (pwm == 255)))
        answer[key]["full_band"] = full_band(target, decoded, rate)
        answer[key]["temporal"] = temporal_metrics(target, decoded, rate)
        assessed = objective.assess(decoded)
        answer[key]["objective_voice"] = assessed["voice"]
        answer[key]["objective_noise"] = assessed["noise"]
        answer[key]["objective_diagnostic"] = assessed["diagnostic"]
        band = answer[key]["full_band"]
        temporal = answer[key]["temporal"]
        total_source = band["source_power"]
        balanced = balanced_time = total_time = 0.
        for spectrum, time_data in zip(band["bands"], temporal["bands"]):
            floor = max(spectrum["source_power"], total_source * 1e-4) if total_source > 0 else 1.
            time_error = time_data["magnitude_change_residual_power_sum"] / temporal["frames"]
            balanced += spectrum["magnitude_residual_power"] / floor / len(band["bands"])
            balanced_time += time_error / floor / len(band["bands"])
            total_time += time_error
        answer[key]["v2_spectrum"] = {"total_error": band["normalized_magnitude_error"],
                "total_temporal_error": total_time / (total_source if total_source > 0 else 1.),
                "balanced_error": balanced, "balanced_temporal_error": balanced_time}
    return answer


def admission(old, new):
    failures = []
    for key in ("pcm16", "pwm8"):
        a, b = old["metrics"][key], new["metrics"][key]
        if b["error_energy"] > a["error_energy"]:
            failures.append(key + "_sse")
        if a["stoi"] is not None and (b["stoi"] is None or b["stoi"] + 1e-10 < a["stoi"]):
            failures.append(key + "_stoi")
        if b["voice"]["within_tolerance_frames"] < a["voice"]["within_tolerance_frames"]:
            failures.append(key + "_source_period_matches")
        if b["clipped_samples"] > a["clipped_samples"]:
            failures.append(key + "_clipping")
        if a["voice"]["reference_period_frames"] != b["voice"]["reference_period_frames"]:
            failures.append(key + "_source_period_membership")
    return {"passed": not failures, "failures": failures}


def speech_safety_admission(old, new):
    failures = []
    if new["metrics"]["pcm16"]["clipped_samples"] > old["metrics"]["pcm16"]["clipped_samples"]:
        failures.append("pcm16_clipping")
    for key in ("pcm16", "pwm8"):
        a, b = old["metrics"][key], new["metrics"][key]
        if a["stoi"] is not None and (b["stoi"] is None or b["stoi"] < a["stoi"] - 1e-12):
            failures.append(key + "_stoi")
        if "objective_diagnostic" in a and "objective_diagnostic" in b:
            if b["objective_diagnostic"]["within"] < a["objective_diagnostic"]["within"]:
                failures.append(key + "_source_period_matches")
            if b["objective_diagnostic"]["collapsed"] > a["objective_diagnostic"]["collapsed"]:
                failures.append(key + "_collapsed")
    return {"passed": not failures, "failures": failures}


def v2_admission(old, new):
    from objective_metrics import score
    failures = list(speech_safety_admission(old, new)["failures"])
    for key in ("pcm16", "pwm8"):
        a, b = old["metrics"][key]["v2_spectrum"], new["metrics"][key]["v2_spectrum"]
        for metric in ("total_error", "balanced_error", "balanced_temporal_error"):
            if b[metric] > a[metric] + 1e-12:
                failures.append(key + "_" + metric)
    baseline = score(old["metrics"], old["metrics"])
    candidate = score(new["metrics"], old["metrics"])
    if candidate["score"] is None or candidate["score"] > baseline["score"] + 1e-12:
        failures.append("selection_score")
    return {"passed": not failures, "failures": failures, "baseline": baseline, "candidate": candidate}


def spectral_admission(old, new):
    failures = []
    for key in ("pcm16", "pwm8"):
        a, b = old["metrics"][key]["full_band"], new["metrics"][key]["full_band"]
        if b["normalized_magnitude_error"] > a["normalized_magnitude_error"] + 1e-12:
            failures.append(key + "_total_magnitude_residual")
        for i, (x, y) in enumerate(zip(a["bands"], b["bands"])):
            if x["source_power"] != y["source_power"] or x["source_supported"] != y["source_supported"]:
                raise AssertionError("Source-frozen spectral membership changed")
            if not x["source_supported"]:
                continue
            if y["normalized_magnitude_error"] > x["normalized_magnitude_error"] + 1e-12:
                failures.append(key + "_band_" + str(i) + "_magnitude_residual")
            if y["capped_amplitude_retention"] + 1e-12 < x["capped_amplitude_retention"]:
                failures.append(key + "_band_" + str(i) + "_attenuation")
    return {"passed": not failures, "failures": failures}


def run(args):
    import numpy as np
    folder = private_path(args.manifest).parent
    manifest = json_read(args.manifest)
    out = private_path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    encoder = private_path(args.encoder)
    build_receipt = json_read(encoder.parent / "build-private.json")
    if digest(encoder) != build_receipt["binary_sha256"]:
        raise ValueError("Encoder binary changed after build")
    if args.phase == "baseline" and digest(encoder) != manifest["baseline_binary_sha256"]:
        raise ValueError("Baseline must be the exact frozen encoder")
    if args.phase == "candidate" and not args.baseline:
        raise ValueError("Candidate jobs require frozen baseline receipts and caps")
    evaluator = Path(manifest["evaluator"])
    if source_files(evaluator) != manifest["evaluator_sha256"]:
        raise ValueError("Independent evaluator changed after target freeze")
    if digest(HERE / "PROTOCOL.md") != manifest["protocol_sha256"]:
        raise ValueError("Protocol changed after target freeze")
    if digest(__file__) != manifest["harness_sha256"]:
        raise ValueError("Harness changed after target freeze; prepare a new frozen target manifest")
    for field, name in (("wideband_protocol_sha256", "PROTOCOL_WIDEBAND.md"),
                        ("temporal_evaluator_sha256", "temporal_metrics.py"),
                        ("objective_evaluator_sha256", "objective_metrics.py")):
        if field in manifest and digest(HERE / name) != manifest[field]:
            raise ValueError("Prospective wideband protocol/evaluator changed after freeze")
    jobs = manifest["jobs"][:args.max_jobs] if args.max_jobs else manifest["jobs"]
    if not 0 <= args.shard_index < args.shard_count:
        raise ValueError("Require0<=shard-index<shard-count")
    jobs = [job for index, job in enumerate(jobs) if index % args.shard_count == args.shard_index]
    completed = []
    for job in jobs:
        path = out / job["job_id"]
        receipt_path = path.with_suffix(".json")
        old = json_read(Path(args.baseline) / (job["job_id"] + ".json")) if args.baseline else None
        if receipt_path.exists():
            prior = json_read(receipt_path)
            if prior["encoder_sha256"] != digest(encoder) or prior["target_sha256"] != job["target_sha256"]:
                raise ValueError("Existing job belongs to a different experiment")
            for suffix, hash_key in ((".lpx", "stream_sha256"), (".s16le", "pcm_sha256"), (".u8", "pwm_sha256")):
                if digest(path.with_suffix(suffix)) != prior[hash_key]:
                    raise ValueError("Completed private artifact changed")
            completed.append(prior)
            continue
        target_path = folder / job["target"]
        if digest(target_path) != job["target_sha256"]:
            raise ValueError("Prepared target changed")
        cap = old["driver"]["legacy_cap"] if old and job["mode"].startswith("p") else 0
        command = [wsl_path(encoder), "encode", job["mode"], str(job["sample_rate"]), str(job["calls"]), str(cap),
                   wsl_path(path.with_suffix(".s16le")), wsl_path(path.with_suffix(".u8"))]
        start = time.monotonic()
        result = subprocess.run(native_command(command, args.distro), input=target_path.read_bytes(), capture_output=True)
        (path.with_suffix(".stderr-private.json")).write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError("Native job failed; private numeric error receipt retained")
        driver = json.loads(result.stderr)
        if driver["samples"] != job["samples"] or driver["sample_rate"] != job["sample_rate"] or len(result.stdout) != driver["file_bytes"]:
            raise AssertionError("Native job geometry mismatch")
        if old and (driver["final_cap"] != old["driver"]["final_cap"] or driver["legacy_cap"] != old["driver"]["legacy_cap"]):
            raise AssertionError("Candidate changed the complete frozen budget")
        path.with_suffix(".lpx").write_bytes(result.stdout)
        target = np.fromfile(target_path, dtype="<i2")
        pcm = np.fromfile(path.with_suffix(".s16le"), dtype="<i2")
        pwm = np.fromfile(path.with_suffix(".u8"), dtype=np.uint8)
        if len(pcm) != len(target) or len(pwm) != len(target):
            raise AssertionError("Incomplete native decode")
        measured = metrics(target, pcm, pwm, job["sample_rate"], job["kind"] == "speech", evaluator)
        receipt = {"schema": 1, "phase": args.phase, "job": job, "driver": driver, "metrics": measured,
                   "target_sha256": job["target_sha256"], "encoder_sha256": digest(encoder),
                   "stream_sha256": digest(path.with_suffix(".lpx")), "pcm_sha256": digest(path.with_suffix(".s16le")),
                   "pwm_sha256": digest(path.with_suffix(".u8")), "total_job_seconds": time.monotonic() - start}
        if old:
            receipt["admission"] = admission(old, receipt)
            receipt["admission_scope"] = "Legacy waveform floors are diagnostic only in revision2"
            receipt["speech_safety_admission"] = speech_safety_admission(old, receipt)
            if "v2_spectrum" in old["metrics"]["pcm16"]:
                receipt["v2_admission"] = v2_admission(old, receipt)
            receipt["spectral_admission"] = spectral_admission(old, receipt)
            receipt["baseline_receipt_sha256"] = digest(Path(args.baseline) / (job["job_id"] + ".json"))
        json_write(receipt_path, receipt)
        completed.append(receipt)
        print(json.dumps({"stage": "job_completed", "ordinal": job["ordinal"], "mode": job["mode"], "rate": job["sample_rate"],
                          "file_bytes": driver["file_bytes"], "encode_seconds": driver["api_encode_seconds"],
                          "total_seconds": receipt["total_job_seconds"], "admitted": receipt.get("admission", {}).get("passed")} ), flush=True)
    name = "run-private.json" if args.shard_count == 1 else f"run-shard-{args.shard_index}-of-{args.shard_count}-private.json"
    json_write(out / name, {"schema": 1, "phase": args.phase, "manifest_sha256": digest(args.manifest),
               "encoder_sha256": digest(encoder), "completed": len(completed), "prospective_jobs": len(manifest["jobs"]),
               "shard_index": args.shard_index, "shard_count": args.shard_count,
               "job_receipts": [r["job"]["job_id"] + ".json" for r in completed]})


def export(args):
    folder = private_path(args.results)
    if (folder / "run-private.json").exists():
        run_receipt = json_read(folder / "run-private.json")
    else:
        shards = [json_read(path) for path in sorted(folder.glob("run-shard-*-private.json"))]
        if not shards:
            raise ValueError("No completed run receipts")
        keys = ("phase", "manifest_sha256", "encoder_sha256", "prospective_jobs", "shard_count")
        if any(any(row[key] != shards[0][key] for key in keys) for row in shards):
            raise ValueError("Incompatible completed shards")
        run_receipt = dict(shards[0], job_receipts=[name for row in shards for name in row["job_receipts"]])
    receipts = [json_read(folder / name) for name in run_receipt["job_receipts"]]
    groups = {}
    for row in receipts:
        job = row["job"]
        name = f'{job["split"]}/{job["mode"]}/{job["sample_rate"]}'
        group = groups.setdefault(name, {"jobs": 0, "samples": 0, "file_bytes": 0, "encode_seconds": 0.,
                                       "legacy_waveform_floors_passed": 0, "legacy_spectral_floors_passed": 0,
                                       "v2_admission_passed": 0, "v2_scored_cases": 0,
                                       "v2_baseline_score_sum": 0., "v2_candidate_score_sum": 0.,
                                       "component_worsened_cases": {}, "pcm16": {"reference_energy": 0., "error_energy": 0., "stoi_sum": 0., "stoi_cases": 0,
                                                               "source_period_frames": 0, "within_tolerance_frames": 0, "clipped_samples": 0},
                                       "pwm8": {"reference_energy": 0., "error_energy": 0., "stoi_sum": 0., "stoi_cases": 0,
                                                              "source_period_frames": 0, "within_tolerance_frames": 0, "clipped_samples": 0}})
        group["jobs"] += 1
        group["samples"] += job["samples"]
        group["file_bytes"] += row["driver"]["file_bytes"]
        group["encode_seconds"] += row["driver"]["api_encode_seconds"]
        group["legacy_waveform_floors_passed"] += bool(row.get("admission", {}).get("passed"))
        group["legacy_spectral_floors_passed"] += bool(row.get("spectral_admission", {}).get("passed"))
        decision = row.get("v2_admission")
        if decision:
            group["v2_admission_passed"] += decision["passed"]
            if decision["candidate"]["score"] is not None:
                group["v2_scored_cases"] += 1
                group["v2_baseline_score_sum"] += decision["baseline"]["score"]
                group["v2_candidate_score_sum"] += decision["candidate"]["score"]
            for path, values in decision["candidate"]["relative_components"].items():
                for component, ratio in values.items():
                    label = path + "/" + component
                    group["component_worsened_cases"].setdefault(label, 0)
                    group["component_worsened_cases"][label] += ratio is None or ratio > 1 + 1e-12
        for key in ("pcm16", "pwm8"):
            data, dest = row["metrics"][key], group[key]
            for field in ("reference_energy", "error_energy", "clipped_samples"):
                dest[field] += data[field]
            if data["stoi"] is not None:
                dest["stoi_sum"] += data["stoi"]
                dest["stoi_cases"] += 1
            dest["source_period_frames"] += data["voice"]["reference_period_frames"]
            dest["within_tolerance_frames"] += data["voice"]["within_tolerance_frames"]
            spectral = data["full_band"]
            bands = dest.setdefault("full_band", {"frames": 0, "nyquist_hz": spectral["nyquist_hz"], "bands": [
                {"low_hz": b["low_hz"], "high_hz": b["high_hz"], "source_supported_cases": 0,
                 "source_power_frame_sum": 0., "output_power_frame_sum": 0.,
                 "complex_residual_power_frame_sum": 0., "magnitude_residual_power_frame_sum": 0.}
                for b in spectral["bands"]]})
            bands["frames"] += spectral["frames"]
            for b, destination in zip(spectral["bands"], bands["bands"]):
                destination["source_supported_cases"] += b["source_supported"]
                for field in ("source_power", "output_power", "complex_residual_power", "magnitude_residual_power"):
                    destination[field + "_frame_sum"] += b[field] * spectral["frames"]
            if "temporal" in data:
                temporal = data["temporal"]
                summary = dest.setdefault("temporal", {"frames": 0, "source_active_frames": 0,
                          "source_noisy_unvoiced_frames": 0, "bands": [{"low_hz": b["low_hz"], "high_hz": b["high_hz"]} for b in temporal["bands"]],
                          "high_bands_from_hz": {}})
                for field in ("frames", "source_active_frames", "source_noisy_unvoiced_frames"):
                    summary[field] += temporal[field]
                def add_numeric_summary(destination, source):
                    for field, value in source.items():
                        if field in ("low_hz", "high_hz", "framewise_private"):
                            continue
                        if field == "noisy_unvoiced":
                            add_numeric_summary(destination.setdefault(field, {}), value)
                        elif isinstance(value, (int, float)):
                            destination[field] = destination.get(field, 0) + value
                for b, destination in zip(temporal["bands"], summary["bands"]):
                    add_numeric_summary(destination, b)
                for cutoff, values in temporal["high_bands_from_hz"].items():
                    if values is not None:
                        add_numeric_summary(summary["high_bands_from_hz"].setdefault(cutoff, {}), values)
    # Deliberate allowlist: no paths, source names, source hashes or media.
    answer = {"schema": 1, "phase": run_receipt["phase"], "completed_jobs": len(receipts),
              "prospective_jobs": run_receipt["prospective_jobs"], "complete": len(receipts) == run_receipt["prospective_jobs"],
              "groups": groups}
    if args.output:
        json_write(args.output, answer)
    else:
        print(json.dumps(answer, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze", help="Archive exact Git baseline and build native driver")
    p.add_argument("--commit", default=COMMIT)
    p.add_argument("--output", required=True)
    p.add_argument("--distro", default="Ubuntu")
    p.set_defaults(func=freeze)
    p = sub.add_parser("build", help="Snapshot a candidate's host/src and build the same driver")
    p.add_argument("--source", default=str(ROOT / CODEC_REL))
    p.add_argument("--output", required=True)
    p.add_argument("--distro", default="Ubuntu")
    p.set_defaults(func=build)
    p = sub.add_parser("prepare", help="Freeze complete targets once for all encoders")
    p.add_argument("--set", choices=("pilot", "primary"), required=True)
    p.add_argument("--source-map", help="Private established 27-case mapping; mandatory for primary")
    p.add_argument("--baseline-build", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=prepare)
    p = sub.add_parser("run", help="Run one native job at a time, independent actual-rate evaluation")
    p.add_argument("--manifest", required=True)
    p.add_argument("--encoder", required=True)
    p.add_argument("--phase", choices=("baseline", "candidate"), required=True)
    p.add_argument("--baseline", help="Frozen baseline receipt directory for candidate caps and gates")
    p.add_argument("--output", required=True)
    p.add_argument("--distro", default="Ubuntu")
    p.add_argument("--max-jobs", type=int, default=0, help="Pilot/debug limit; never reported as a complete run")
    p.add_argument("--shard-index", type=int, default=0, help="Deterministic job shard; coordinate numerical workers")
    p.add_argument("--shard-count", type=int, default=1)
    p.set_defaults(func=run)
    p = sub.add_parser("export", help="Allowlisted anonymous numeric summary")
    p.add_argument("--results", required=True)
    p.add_argument("--output")
    p.set_defaults(func=export)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
