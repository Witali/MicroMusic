# Host scope audit before Long extension

Read-only findings at predecessor `654a95c7`, before audiobook outcomes.

The two local 64,000-sample checks in `host/LpxAccuracy.cpp` are the only new
phase limits to change: `validCompactModel` and `compactEnsembleEligible`.
Their surrounding loops use host `int`/`size_t` indices and dynamically sized
vectors. The encoder already supports up to 32,000,000 samples through its
caller-reserved workspace; no new reserve call is needed for this phase.

`LpxBitrateProfiles.cpp::proposedBytes` and `spectralPlans` already account for
17 rather than 13 header bytes above 64,000 samples. `encodeThreeK` checks its
incumbent and every returned candidate against actual `packV9` bytes. No new
budget approximation is needed. The 20-second nominal P3 allocation term is
17 + ceil(500 * 120 / 8) = 7,517 bytes; C is the maximum of this term and the
initial seed bytes. The optional phase still receives the finished B0 only.

`LpxPacking.cpp::v9Header` already sets the Long flag and writes 32-bit sample
count and payload length. `LpxAdaptiveController.cpp::verifyStream` already
calls `beginWideV9` with full-width size, compares every sample and checks final
EOF/error/finished state. Native wide-enabled builds retain 32-bit counts;
the legacy bounded entry point and wide-disabled builds are not relabeled as
Long-capable. The old research probe's 13-byte-only parser must not be reused
unchanged for new Long study artifacts.

At 160,000 samples, there are 500 spectral frames, 1,000 parameter blocks,
4,000 pulse-pair packets and 8,000 20-sample coefficient entries. None requires
a 16-bit sample cursor. The production bit writer uses a 64-bit bit count.
Whole-output SSE fits `uint64_t` even at the largest PCM16 difference.
The existing PCM synthesis carries its LPC history, de-emphasis and 256-entry
excitation ring across sample 64,000 and 65,536 without an intended reset.
The independent tests must demonstrate this rather than infer it from headers.

Calculated allocation sizes on the existing 32-bit-int host contract:

| Object | Size at 160,000 samples |
| --- | ---: |
| One PCM16 vector | 320,000 bytes |
| One coefficient trace | 160,000 bytes |
| Spectrum vector payload | 20,000 bytes |
| Parameter vector payload | 12,000 bytes |
| Main pulse vector payload | 64,000 bytes |
| Extra pulse vector payload | 32,000 bytes |
| Existing seed workspace reservation, `n*24+65536` | 3,905,536 bytes |
| Existing seed packed capacity, `17+(n/320)*64` | 32,017 bytes |
| `fitExcitation` emphasized + residual double arrays | 2,560,000 bytes |

These are component calculations, not peak RSS or WASM heap measurements.
Multiple stream/PCM temporaries coexist. The matching evaluation cache retains
at most eight scalar summaries and 64 KiB of packet keys, not candidate PCM.
No fixed-point arithmetic, decoder state size or assembly backend is changed.
