#!/usr/bin/env python3
"""Pin/check the host quality evaluator's Octave-compatible FIR coefficients.

Development dependency: pystoi 0.4.1 (MIT), NumPy and SciPy. The runtime only
reads the generated double constants. Upstream algorithm and license:
https://github.com/mpariente/pystoi/blob/v0.4.1/pystoi/utils.py
../host/LICENSE-pystoi.txt

The coefficients include resample_poly's multiplication by the interpolation
factor. Padding/alignment and ascending-input accumulation are implemented in
LpxStoi.cpp. Analysis FIRs retain PCM16 units in double precision.
"""
import argparse
from importlib.metadata import version
from pathlib import Path

import numpy as np
from pystoi.utils import _resample_window_oct


FILTERS = (
    ("stoi-resample.inc", 5, 4, "8 kHz to 10 kHz"),
    ("stoi-resample-12k.inc", 5, 6, "12 kHz to 10 kHz"),
    ("stoi-resample-16k.inc", 5, 8, "16 kHz to 10 kHz"),
    ("quality-resample-12k.inc", 2, 3, "12 kHz to 8 kHz analysis"),
    ("quality-resample-16k.inc", 1, 2, "16 kHz to 8 kHz analysis"),
)


def coefficients(up, down):
    taps = _resample_window_oct(up, down)
    return taps / np.sum(taps) * up


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()
    if version("pystoi") != "0.4.1":
        raise SystemExit("Use pinned pystoi 0.4.1")
    host = Path(__file__).resolve().parents[1] / "host"
    for name, up, down, description in FILTERS:
        path = host / name
        taps = coefficients(up, down)
        if args.check or name == "stoi-resample.inc":
            # The original 8 kHz text is deliberately never regenerated.
            found = np.array([float(line.rstrip(",")) for line in
                              path.read_text().splitlines() if not line.startswith("//")])
            # libm/NumPy builds can differ in the final floating-point bit.
            if found.shape != taps.shape or not np.allclose(found, taps, rtol=0, atol=2e-16):
                raise SystemExit(f"Coefficient mismatch: {name}")
        else:
            comment = (f"// pystoi 0.4.1 Octave-compatible {description} FIR; "
                       "MIT, see LICENSE-pystoi.txt.\n")
            path.write_text(comment + "".join(f"{tap:.17g},\n" for tap in taps), newline="\n")
        print(f"{name}: {len(taps)} pinned double coefficients")


if __name__ == "__main__":
    main()
