# Persistent native oracle for research strict2k

This test-only bridge makes the existing Windows Python/NumPy research tools
able to call two unchanged Linux native C receivers through persistent WSL
stdin/stdout pipes. It installs no Python packages or compiler, changes no
encoder/decoder/default, and launches no search. P3 accuracy tests are separate.

`common` enables the existing speech/compact parsers. `v5-only` additionally
selects `LPX4_COMPACT_ONLY=1`. Both explicitly select portable C, fixed integer
synthesis and compact version5. Research sparse80/version8 inputs must pass
through the existing independent `speech_sparse80.expand()` bridge to v5/P6,
exactly as `encode_low_bitrate_speech.py` and `RoundAdmission` already require.
These receivers intentionally do not silently accept sparse80 directly.

Build once with the installed WSL Ubuntu/g++ (or directly on Linux):

```powershell
python Codecs/LPX/experimental/compact-quality/sparse2/native_receiver.py
```

The Python used for the test must already have NumPy and the existing research
dependencies available. An existing portable interpreter can use an explicit
local packages path without installation:

```powershell
python Codecs/LPX/experimental/compact-quality/sparse2/test_receiver.py --packages C:/Work/MicroMusic/build/codec-python
```

The test builds fresh binaries and pins source/header/table hashes, compiler,
options, binary hashes and results under ignored `build/compact-quality/sparse2`.
Opening a receiver checks the exact source and binary fingerprints. Rebuild
explicitly after a source change; the adapter has no automatic compiler/backend
fallback. Example use after adding this folder to Python's import path:

```python
from native_receiver import NativeReceiver
with NativeReceiver('common') as common, NativeReceiver('v5-only') as only:
    pcm = common.decode_one_s16(expanded_v5, samples)
    duty = only.decode_one(expanded_v5, samples)
```

`decode_one_s16`, `decode_one`, `decode_many_s16` and `decode_many` preserve the
existing BatchDecoder array/None contract. Invalid codec streams return None;
transport corruption raises an exception. `decode_result` additionally exposes
declared/produced/decoded count, rate, native error, finished state and payload
length. Successful output requires exact EOF after the declared sample count.
This means the existing receiver's `next`/`error`/`finished` contract, not a new
strict canonical parser: legacy version5 ignores nonzero unused final padding
bits. The test records that behavior; the independent Python compact unpacker
rejects those bits before native replay in the strict2k admission pipeline.
Both ends use framed little-endian binary fields and never write logs/audio to
the protocol stdout. Requests cap ROM bytes at65535 and expected samples at one
million. Malformed transport lengths close the server without oversized input
allocation; a partial request is a process error, while clean stdin EOF exits0.
Each process resets the native decoder per request and remains alive across
valid/invalid codec streams. One lock serializes an owner's request/response;
different receivers have independent processes. Bulk methods use several IPC
messages, not the old shared-library batch ABI, so their performance differs.

Synthetic tests compare PCM and PWM with the independent sparse80->v5 model
across tails, filters and changing lag/gain. They check error recovery, metadata,
binary framing/EOF, interleaving and construction of one synthetic protected
`RoundAdmission` baseline without a new proposal. No actual MCU/interrupt timing,
AVR admission, physical-board result or sound-quality gain is implied.
