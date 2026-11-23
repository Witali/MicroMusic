"""Verify the optional shared expanded search against its retained candidate.

Run from the repository root with an independently built native helper, e.g.
python web-player/scripts/check-lpx-expanded.py --encoder build/lpx-native-encode
Only generated signals and the repository's public speech sample are used.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import time
from array import array
from pathlib import Path


def run(encoder, pcm, profile, mode, allowance=0, calls=0):
    args = [encoder, str(profile), "8000", mode, str(calls)]
    args.append(str(allowance))
    started = time.perf_counter()
    result = subprocess.run(args, input=pcm.tobytes(), capture_output=True, check=True)
    reports = [json.loads(re.sub(r"\bnan\b", "NaN", line)) for line in result.stderr.decode().splitlines()]
    return result.stdout, reports[0], reports[1], time.perf_counter() - started


def guarded(candidate, baseline):
    assert candidate["score"] <= baseline["score"] + 1e-12, "voice/noise score"
    for a, b in zip(candidate["error"], baseline["error"]):
        assert a <= b, "PCM/PWM squared error"
    for a, b in zip(candidate["stoi"], baseline["stoi"]):
        if math.isfinite(b):
            assert math.isfinite(a) and a >= b - 1e-12, "PCM/PWM STOI"
    for a, b in zip(candidate["within"], baseline["within"]):
        assert a >= b, "voiced period diagnostic"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", default="build/lpx-native-encode")
    parser.add_argument("--full", action="store_true", help="Also test public speech after all four parity stages")
    args = parser.parse_args()
    cases = []
    for n in (1, 19, 20, 39, 40, 159, 160, 161, 319, 320, 321, 641):
        cases.append((f"tail-{n}", array("h", (round(6000 * math.sin(i * .14) + 1000 * math.sin(i * .31)) for i in range(n))), 0))
    cases += [("silence", array("h", [0]) * 641, 0),
              ("clipping", array("h", (32767 if i & 1 else -32768 for i in range(641))), 0),
              ("quiet", array("h", (round(3 * math.sin(i * .14)) for i in range(961))), 0),
              ("pause-transition", array("h", (round(9000 * math.sin(i * .14)) if 640 <= i < 1280 or i >= 1920 else 0 for i in range(2561))), 0)]
    if args.full:
        sys.path.insert(0, str(Path("Codecs/LPX/01_ACTIVE_Q0_CODEC/tools").resolve()))
        from wav_lpc import load_wav
        public, _ = load_wav("web-player/audio/originals/chego.wav")
        pcm = array("h", public)
        cases.append(("public-speech", pcm, 4))
    rows = []
    for name, pcm, calls in cases:
        for profile in (4, 6):
            _, original_report, _, _ = run(args.encoder, pcm, profile, "adaptive", calls=calls)
            for allowance in (0, 25):
                control, control_report, baseline, _ = run(args.encoder, pcm, profile, "adaptive", allowance, calls)
                actual, report, measured, seconds = run(args.encoder, pcm, profile, "extended", allowance, calls)
                guarded(measured, baseline)
                assert report["cap"] == original_report["cap"] * (100 + allowance) // 100, "complete-control budget"
                assert measured["bytes"] <= report["cap"], "complete compact-size cap"
                assert actual[:2] == b"L9", "one V9 stream"
                rows.append({"case": name, "profile": profile, "allowance": allowance,
                             "changed": actual != control, "seconds": round(seconds, 3),
                             "local": report["expandedLocal"], "full": report["expandedFull"]})
                print(json.dumps(rows[-1]), flush=True)
    print(json.dumps({"checks": len(rows), "changed": sum(row["changed"] for row in rows)}))


if __name__ == "__main__":
    main()
