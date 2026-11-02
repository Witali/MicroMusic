"""Write integer PCM16 units without an implicit 32-bit amplitude conversion."""
from pathlib import Path
import tempfile
import wave

import numpy as np


def write_pcm16_wav(path, samples, rate=8000):
    """Write mono PCM16, verify exact samples, then replace the destination.

    Signed/wider integer inputs contain PCM16 units, not full-scale PCM32.
    Reject floating/normalized inputs and out-of-range values instead of
    silently changing their scale. No gain adjustment is performed.
    """
    data = np.asarray(samples)
    if (data.ndim != 1 or not len(data) or data.dtype.kind not in 'iu'
            or int(data.min()) < -32768 or int(data.max()) > 32767):
        raise ValueError('Expected nonempty mono integer samples in PCM16 units')
    if isinstance(rate, bool) or not isinstance(rate, (int, np.integer)) or not 1 <= rate <= 192000:
        raise ValueError('Expected an integer WAV sample rate')
    payload = data.astype('<i2').tobytes()
    destination = Path(path)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.wav.partial', delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        with wave.open(str(pending), 'wb') as output:
            output.setparams((1, 2, int(rate), len(data), 'NONE', 'not compressed'))
            output.writeframes(payload)
        with wave.open(str(pending), 'rb') as reopened:
            if (reopened.getnchannels(), reopened.getsampwidth(), reopened.getframerate(),
                    reopened.getnframes(), reopened.getcomptype()) != (1, 2, rate, len(data), 'NONE'):
                raise AssertionError('Written WAV format differs from PCM16 input')
            if reopened.readframes(len(data)) != payload:
                raise AssertionError('Written WAV samples differ from PCM16 input')
        pending.replace(destination)
    finally:
        pending.unlink(missing_ok=True)
