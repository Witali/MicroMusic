# LPX storage guidance and current limits

About **128 KiB of local nonvolatile storage** is a useful embedded design
reference, not a reserved media allowance or a RAM claim. **Media of at least
1 GiB on PCs or external storage** is a future streaming target. These are
nonbinding orientations, not format rules or rejection thresholds. An MCU with
external flash can have a larger media store; capacity alone does not establish
addressability or real-time playback.

The storage/API audit uses `654a95c7` on 2026-11-26. The audiobook development
change separately raises `kCompactEnsembleMaxSamples` to 160,000; prior coverage
was 64,000. Its new tests/results establish coverage, independently of storage
orientation or wire-format capacity.

## Separate the limiting layers

| Layer | Existing implementation | Meaning |
| --- | --- | --- |
| Ordinary V9 wire header | 13 bytes; 16-bit sample and payload fields. The parser accepts 1–64,000 samples and a complete input span of at most 65,535 bytes. | This bounded representation is smaller than the 128 KiB design example. That example does not widen its fields or APIs. |
| V9 Long wire header | 17 bytes; flag bit 6 selects 32-bit sample and payload fields. The parser checks a nonzero sample count and exact payload length against the supplied span. | Wider representation already exists. Field widths are not a guarantee that every representable file can be allocated, encoded or played. |
| Bounded decoder input | `begin(..., uint16_t size)` and callback `beginStream(..., uint16_t size)`. | These interfaces cannot accept a span larger than 65,535 bytes. The callback's size argument remains 16-bit even in a wide-enabled build. |
| Wide pointer decoder input | Explicit `beginWideV9(..., uint32_t size)`, supporting ordinary and Long headers. | Requires a standard-memory, non-AVR compact-V9 build with `LPX4_ENABLE_WIDE_V9=1`. Its 32-bit span is an addressing bound, not proof of GiB-scale operation. |
| Whole host encode / native CLI | `kLpxMaxSamples = 32,000,000`. | A current workspace/resource policy, separate from the Long wire fields. Memory allocation can fail below this ceiling. |
| Host encoding by windows | Up to 64,000,000 samples only for accuracy streaming with zero refinement calls; refined and other paths retain the 32,000,000-sample ceiling. | Windowed processing carries state; it is not permission to insert independent codec resets. The current final quality verification can also retain whole-record PCM arrays. |
| Browser decoder / file loader | 64,000,000 decoded samples and 100 MiB of encoded input, with additional allocation checks. | Explicit current application/ABI limits. The incremental decoder bounds output windows but still loads the complete encoded input. It is not a GiB input-streaming implementation. |
| Optional P3 fine-grid search | The audiobook development code sets `kCompactEnsembleMaxSamples = 160000`, at 8 kHz, calls 4, with a null prefix/reset context. The preceding study covered at most 64,000 samples. | This separate eligibility window is under new testing. It is neither the format limit nor proof that every eligible input benefits. |

The wire declarations and decoder API guards are in
[Lpx4HybridCore.h](../../../01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.h) and
[Lpx4HybridCore.cpp](../../../01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp).
The encoder chooses ordinary versus Long headers in
[LpxPacking.cpp](../../../01_ACTIVE_Q0_CODEC/host/LpxPacking.cpp).
Resource constants are in
[LpxHostWorkspace.h](../../../01_ACTIVE_Q0_CODEC/host/LpxHostWorkspace.h),
[codec.js](../../../../../web-player/lpx/codec.js) and
[the browser decoder ABI](../../../../../web-player/lpx/native/decoder.cpp).
Optional-search eligibility is independently checked in
[LpxAccuracy.cpp](../../../01_ACTIVE_Q0_CODEC/host/LpxAccuracy.cpp).

## Consequences for the 20-second study

At 8 kHz, 20 seconds is 160,000 samples: one existing V9 Long stream with one
17-byte header and continuous LPC, excitation-ring and postfilter history.
Dividing it into bounded files with reset state would test different encoding
and playback behavior. Use the actual completed baseline's whole file size B0;
neither 128 KiB nor the nominal P3 allowance is an extra byte budget.

The seed encoder initially reserves approximately `24 * padded_samples + 65536`
bytes, before candidate models, coefficient traces, quality analysis and other
allocations. Thus compressed file size is not an encoder RAM estimate. Nothing
here claims that a particular MCU has 128 KiB available for media, can hold the
encoder workspace, supports Long, or meets its interrupt deadline.

## Future large-storage work

GiB-scale PC or external-flash workflows need deliberate input transport,
offset/count and overflow auditing, bounded working buffers, state-preserving
playback and end-to-end tests. Larger backing storage does not automatically
widen a callback argument or remove the current browser/resource ceilings.
Beyond existing field/address ranges, an additional representation may also be
needed. No such container or new large-file implementation is introduced here.

Keep the current embedded C interface and explicitly selectable arithmetic
backends while evaluating such work. Claim MCU support only for the actual
memory/input configuration and measured interrupt-active playback. No new hard
size rejection, existing-limit increase or GiB-support claim follows from this
guidance note.
