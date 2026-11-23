#!/usr/bin/env python3
"""Acquire a bounded, source-only FLEURS RU/EN wideband research subset.

All outputs, original audio, metadata, labels and download receipts are confined
to ignored build/wideband-corpora. Nothing is uploaded. Original published WAV
members are retained byte-for-byte; prepared WAVs have the measured native rate
and PCM16 samples with no gain fitting, trimming, alignment or denoising.

Source: https://huggingface.co/datasets/google/fleurs (CC BY 4.0).
Use the pinned revision in PROTOCOL before inspecting any codec outputs.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import tarfile
import urllib.request

import numpy as np
from scipy.signal import resample_poly
import soundfile as sf


REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
BASE = "https://huggingface.co/datasets/google/fleurs/resolve/"
PROTOCOL = {
    "schema": "lpx-fleurs-source-only-selection-v1", "revision": REVISION,
    "languages": ["ru_ru", "en_us"], "official_splits": ["train", "test"],
    "whole_utterance_seconds": [4, 8], "minimum_measured_rate": 16000,
    "source_band_requirement": "at least one 1 kHz band >=4 kHz with >1e-4 of total power after direct 16 kHz conversion",
    "order": "published tar member order; first eligible utterances per public binary gender label",
    "reserve_per_language": {"train": {"male": 2, "female": 2}, "test": {"male": 3, "female": 3}},
    "final_per_language": {"train": {"male": 1, "female": 1}, "test": {"male": 2, "female": 2}},
    "no_codec_output_selection": True, "no_gain_alignment_trimming_or_denoising": True,
    "license": "CC-BY-4.0", "card": "https://huggingface.co/datasets/google/fleurs",
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "MicroMusic-local-research/1"}), timeout=45)


class PrefixLimit(Exception):
    pass


class PrefixReader:
    def __init__(self, response, path, limit):
        self.response, self.output, self.limit = response, path.open("wb"), limit
        self.count, self.sha = 0, hashlib.sha256()

    def read(self, size=-1):
        if self.count >= self.limit:
            raise PrefixLimit("declared compressed prefix limit reached")
        size = self.limit - self.count if size < 0 else min(size, self.limit - self.count)
        chunk = self.response.read(size)
        self.count += len(chunk)
        self.output.write(chunk)
        self.sha.update(chunk)
        return chunk

    def close(self):
        self.output.close()
        self.response.close()


def band_power(pcm, rate):
    """The frozen native 512/Hann/hop256 full-band admission transform."""
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(512) / 511)
    weights = np.full(257, 2.0)
    weights[[0, -1]] = 1
    bands = rate // 2000
    labels = np.minimum(bands - 1, np.arange(257) * rate // 512000)
    powers, frames = np.zeros(bands), 0
    for start in range(-256, len(pcm), 256):
        frame = np.zeros(512)
        begin, end = max(0, start), min(len(pcm), start + 512)
        frame[begin - start:end - start] = pcm[begin:end]
        power = np.abs(np.fft.rfft(frame * window)) ** 2 * weights
        for b in range(bands):
            powers[b] += np.sum(power[labels == b])
        frames += 1
    return powers / (frames * 512 * np.sum(window * window))


def as_pcm16(payload):
    info = sf.info(io.BytesIO(payload))
    if info.channels != 1 or info.samplerate < 16000:
        return None, info, "unsupported_geometry"
    if info.subtype == "PCM_16":
        pcm, _ = sf.read(io.BytesIO(payload), dtype="int16")
    else:
        samples, _ = sf.read(io.BytesIO(payload), dtype="float64")
        pcm = np.clip(np.rint(samples * 32768), -32768, 32767).astype(np.int16)
    return pcm, info, None


def acquire(language, split, args, output):
    key = f"{language}-{split}"
    metadata = output / "metadata" / f"{key}.tsv"
    metadata_url = f"{BASE}{REVISION}/data/{language}/{split}.tsv"
    if not metadata.exists():
        with request(metadata_url) as response:
            metadata.write_bytes(response.read(4 * 1024 * 1024))
    rows = {}
    with metadata.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) != 7:
                raise ValueError("unexpected official metadata shape")
            rows[Path(row[1]).name] = {"id": row[0], "file": row[1], "declared_samples": int(row[5]), "gender": row[6].strip().casefold()}
    archive_url = f"{BASE}{REVISION}/data/{language}/audio/{split}.tar.gz"
    receipt_path = output / "receipts" / f"{key}.json"
    if receipt_path.exists():
        prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        if prior.get("complete_reserve"):
            return prior["cases"]
        attempts = output / "receipts" / "attempts"
        attempts.mkdir(exist_ok=True)
        ordinal = len(list(attempts.glob(f"{key}-*.json"))) + 1
        (attempts / f"{key}-{ordinal:03d}.json").write_bytes(receipt_path.read_bytes())
    response = request(archive_url)
    expected_bytes = int(response.headers.get("Content-Length", 0))
    reader = PrefixReader(response, output / "downloads" / f"{key}.tar.gz.partial", args.max_prefix_mib * 1024 * 1024)
    quotas = PROTOCOL["reserve_per_language"][split]
    counts, skipped, rates, cases = Counter(), Counter(), Counter(), []
    members, complete, status = 0, False, "partial_prefix"
    try:
        with tarfile.open(fileobj=reader, mode="r|gz") as archive:
            for member in archive:
                members += 1
                if not member.isfile() or not member.name.lower().endswith(".wav"):
                    continue
                row = rows.get(Path(member.name).name)
                if row is None:
                    skipped["missing_metadata"] += 1
                    continue
                gender = row["gender"]
                if gender not in quotas or counts[gender] >= quotas[gender]:
                    skipped["label_quota"] += 1
                    continue
                payload = archive.extractfile(member).read()
                pcm, info, problem = as_pcm16(payload)
                rates[str(info.samplerate)] += 1
                if problem:
                    skipped[problem] += 1
                    continue
                duration = len(pcm) / info.samplerate
                if not 4 <= duration <= 8:
                    skipped["duration"] += 1
                    continue
                divisor = math.gcd(info.samplerate, 16000)
                analysis = pcm.astype(float) if info.samplerate == 16000 else resample_poly(pcm.astype(float), 16000 // divisor, info.samplerate // divisor)
                target = np.clip(np.rint(analysis), -32768, 32767).astype("<i2")
                powers = band_power(target, 16000)
                supported = powers > np.sum(powers) * 1e-4
                if not any(supported[4:]):
                    skipped["no_supported_upper_band"] += 1
                    continue
                ordinal = len(cases) + 1
                identifier = f"fleurs-{language[:2]}-{split}-{ordinal:02d}"
                source = output / "sources" / f"{identifier}.wav"
                original = output / "originals" / f"{identifier}.wav"
                original.write_bytes(payload)
                sf.write(source, pcm, info.samplerate, subtype="PCM_16", format="WAV")
                prepared, measured_rate = sf.read(source, dtype="int16")
                assert measured_rate == info.samplerate and np.array_equal(prepared, pcm)
                item = {"source": str(source.resolve()), "corpus": "fleurs", "language": language[:2],
                        "split": "tuning" if split == "train" else "heldout", "native_rate": info.samplerate,
                        "native_samples": len(pcm), "source_pcm_sha256": hashlib.sha256(pcm.astype("<i2").tobytes()).hexdigest(),
                        "selection_receipt": {"official_split": split, "archive_member": member.name,
                          "tar_ordinal": members, "public_gender": gender, "metadata": row,
                          "original": str(original.resolve()), "original_sha256": hashlib.sha256(payload).hexdigest(),
                          "original_format": info.format, "original_subtype": info.subtype,
                          "pcm16_conversion": "none" if info.subtype == "PCM_16" else "round_to_nearest_PCM16_without_gain",
                          "target16k_source_band_power": powers.tolist(), "target16k_supported_bands": supported.tolist(),
                          "target16k_resampler": "none" if info.samplerate == 16000 else "scipy.signal.resample_poly default Kaiser 5.0; nearest PCM16, no gain",
                          "original_header_rate_measured": True}}
                cases.append(item)
                counts[gender] += 1
                print(f"{language}/{split}: retained {len(cases)}/{sum(quotas.values())}, native rate {info.samplerate}, {duration:.3f} s", flush=True)
                if all(counts[label] >= count for label, count in quotas.items()):
                    complete = True
                    break
            else:
                status = "complete_archive"
    except PrefixLimit:
        status = "partial_prefix_limit"
    finally:
        reader.close()
        write_json(receipt_path, {"protocol": PROTOCOL, "archive_url": archive_url,
                   "metadata_url": metadata_url, "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
                   "archive_status": status, "archive_expected_bytes": expected_bytes,
                   "downloaded_prefix_bytes": reader.count, "prefix_sha256_not_full_archive_hash": reader.sha.hexdigest(),
                   "tar_members_examined": members, "complete_reserve": complete, "native_header_rate_counts": dict(rates),
                   "selection_counts": dict(counts), "skipped_counts": dict(skipped), "cases": cases})
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-prefix-mib", type=int, default=128)
    parser.add_argument("--language", choices=PROTOCOL["languages"], action="append")
    parser.add_argument("--split", choices=PROTOCOL["official_splits"], action="append")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    allowed = (root / "build" / "wideband-corpora").resolve()
    output = (args.output or allowed / "fleurs").resolve()
    if not output.is_relative_to(allowed) or args.max_prefix_mib < 1:
        raise SystemExit("Output must stay under ignored build/wideband-corpora; positive byte cap required")
    for directory in ("metadata", "receipts", "downloads", "sources", "originals"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    card = output / "metadata" / "dataset-card.md"
    if not card.exists():
        with request(f"{BASE}{REVISION}/README.md") as response:
            card.write_bytes(response.read(1024 * 1024))
    write_json(output / "protocol-private.json", PROTOCOL)
    reserve = []
    for language in args.language or PROTOCOL["languages"]:
        for split in args.split or PROTOCOL["official_splits"]:
            reserve.extend(acquire(language, split, args, output))
    final, counts = [], Counter()
    for item in reserve:
        row = item["selection_receipt"]
        gender, official = row["public_gender"], row["official_split"]
        key = (item["language"], official, gender)
        if counts[key] < PROTOCOL["final_per_language"][official][gender]:
            final.append(item)
            counts[key] += 1
    for name, selected in (("sources-private.json", final), ("reserve-private.json", reserve)):
        write_json(output / name, {"schema": "lpx-native-wideband-sources-v1", "protocol": PROTOCOL, "cases": selected})
    high6 = sum(any(item["selection_receipt"]["target16k_supported_bands"][6:]) for item in final)
    print(f"Prepared {len(final)} final / {len(reserve)} reserve cases; >=6 kHz source-supported: {high6}", flush=True)


if __name__ == "__main__":
    main()
