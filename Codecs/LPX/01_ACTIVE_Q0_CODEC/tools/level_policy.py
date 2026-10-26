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


def preserves_activity(reference,decoded,floor_db=DEFAULT_LEVEL_FLOOR_DB):
    """Reject sustained >=30 ms mutes, using the same relative dB setting.

    This evaluates a fully decoded candidate; it never modifies its samples.
    The recording floor identifies active input windows. A window is muted
    when output power is below the same dB ratio of that input window.
    """
    x=np.asarray(reference,dtype=np.float64);y=np.asarray(decoded,dtype=np.float64)
    if x.ndim!=1 or x.shape!=y.shape or not len(x):raise ValueError('Equal nonempty mono arrays required')
    starts=np.arange(0,len(x),80);lengths=np.minimum(80,len(x)-starts)
    source=np.add.reduceat(x*x,starts)/lengths;output=np.add.reduceat(y*y,starts)/lengths
    muted=(source>=relative_energy_floor(x,float(floor_db)))&(output<source*10.**(floor_db/10.))
    run=0
    for value in muted:
        run=run+1 if value else 0
        if run>=3:return False
    return True
