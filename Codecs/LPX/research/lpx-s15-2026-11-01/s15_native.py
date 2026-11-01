"""Host-only compilation/ctypes interface to the independent S15 expander."""
from pathlib import Path
import ctypes as ct
import subprocess
from s15_format import ACTIVE
from batch_decoder import BatchDecoder


def build(output, compiler, compact_only):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    src = ACTIVE / 'src'
    flags = ['-O2', '-shared', '-fPIC', '-std=c++11', '-DLPX4_ENABLE_SPEECH=1',
             '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_ENABLE_ASM=0',
             '-DLPX4_PITCH_HISTORY_SIZE=256']
    if compact_only:
        flags.append('-DLPX4_COMPACT_ONLY=1')
    command = [str(compiler), *flags, '-I'+str(src),
               str(Path(__file__).with_name('native_s15.cpp')),
               str(src / 'Lpx4HybridCore.cpp'), str(src / 'native_batch_decoder.cpp'), '-o', str(output)]
    result = subprocess.run(command, capture_output=True)
    output.with_suffix('.build-private.log').write_bytes(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError('S15 native reference build failed; inspect private log')
    return dict(flags=flags, compact_only=bool(compact_only))


class Native:
    def __init__(self, library):
        self.decoder = BatchDecoder(library)
        self.fn = self.decoder.dll.lpx_s15_expand
        self.fn.argtypes = [ct.POINTER(ct.c_uint8), ct.c_uint32, ct.POINTER(ct.c_uint8),
                            ct.c_uint32, ct.POINTER(ct.c_uint32)]
        self.fn.restype = ct.c_int

    def expand(self, blob):
        source = (ct.c_uint8*len(blob)).from_buffer_copy(blob)
        output = (ct.c_uint8*65535)()
        n = ct.c_uint32()
        if self.fn(source, len(blob), output, len(output), ct.byref(n)):
            return None
        return bytes(output[:n.value])

    def decode(self, blob, samples, pwm=False):
        expanded = self.expand(blob)
        if expanded is None:
            return None
        method = self.decoder.decode_one if pwm else self.decoder.decode_one_s16
        return method(expanded, samples)
