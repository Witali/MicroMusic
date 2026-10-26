"""Shared host-encoder level policy; this is a soft error floor, not a gate.

The default power floor is 30 dB below the whole recording's RMS power.
Scaling the recording scales the floor too, down to one squared integer
sample unit needed by the fixed-point input representation. No samples are
muted, normalized or amplified here. The MCU decoder does not use this policy.
"""
import numpy as np
from numba import njit

DEFAULT_LEVEL_FLOOR_DB = -30.0


@njit(cache=True)
def relative_energy_floor(reference, floor_db=DEFAULT_LEVEL_FLOOR_DB):
    if not len(reference) or not np.isfinite(floor_db) or floor_db > 0:
        raise ValueError('Expected nonempty audio and a finite relative floor <= 0 dB')
    power = 0.0
    for value in reference:
        sample = float(value)
        power += sample * sample
    if not np.isfinite(power):
        raise ValueError('Audio energy must be finite')
    return max(1.0, power / len(reference) * 10.0 ** (floor_db / 10.0))
