# Fuse WB5.75/WB7.75 excitation and high-band folding

Baseline: `307fe278`; runtime: `603ddcbd`. Target ATmega328P / classic AVR5,
16 MHz, 2 KB SRAM, GNU ABI, AVR GCC 7.3.0, explicit ASM, existing Os/O2/O3
stages and LTO/mcall-prologues/mrelax. Matched full images enable all lower
rates (`--low-rates 7`) and NB4; they differ only by the tested packet width.

## Reuse the arithmetic, change vector geometry

The old high-band producer called the ten-sample zero-innovation procedure
four times, wrote forty intermediate words, then loaded/folded them in place.
Use the existing `WB_EXCITATION` template already serving WB9.8/WB12.8:

```asm
WB_EXCITATION speex_wb_excitation_nb2_40_avr,4,10,exc_10_16_table
WB_EXCITATION speex_wb_excitation_nb8_40_avr,2,20,exc_20_32_table
```

NB2 + HB1 gives WB7.75; NB8 + HB1 gives WB5.75. Width 20 can be traversed directly
instead of splitting each row into two ten-sample calls. Every vector has even
width, so local alternating parity matches frame parity. The template asserts
forty samples and even width. The shape rounding bias remains **4**, including
when vector count is 2; it must not be coupled to the vector count.

Keep every original quantizer, signed16 intermediate and modulo32 scale:

```c
innovation = ((int64_t)shape * scale + 262144) >> 19; /* Wide reference. */
t = (int16_t)(((int32_t)29491 * innovation) >> 15);
r = (uint16_t)(((uint32_t)t * (uint32_t)gain + 256) >> 9);
out = odd ? (int16_t)(uint16_t)(0u-r) : (int16_t)r;
```

For signed8 shape and scale 0..121000000, innovation fits signed16. The actual
AVR template uses the existing byte-product implementation, not a new wide
multiply. Values stay in registers through shape reconstruction and both HB1
steps, with one final output store. This removes 80 intermediate SRAM byte
loads and 80 extra byte stores per subframe, 640 byte accesses per frame.
Tables, packet parsing, LPC/IIR/QMF state, output publication and synthesis
delay are unchanged. No new working buffer or heap is introduced.

`speex_wb_excitation_low40_c` retains separate C reconstruction/folding and
remains explicitly callable on AVR. Its arithmetic uses the portable reference
helpers even in an ASM build. The existing architecture plus separate ASM-enable
selector chooses the backend; hardware Flash access remains independent. Each
new ASM leaf is gated by its own NB2/NB8 feature define. Public codec interfaces
are unchanged; only the internal low-rate controller is renamed/selected.

The small ASM mode dispatcher is inline at its sole production call site.
This lets the compiler reuse the existing mode branch and removes a separate
five-argument ABI boundary. Arithmetic remains in out-of-line ASM procedures.
An outlined dispatcher was also measured and retained for comparison.
The old ASM forty-word fold and old controller are absent from the selected
production images after section garbage collection; test/reference code stays
available in the source. Both new leaves are present in the all-feature images.

## Independent arithmetic and memory evidence

An isolated mailbox compares four paths: a two-pass ASM reference, explicit C,
the new inline dispatch behind a test-only ABI boundary, and each direct ASM
leaf. It passes **52256 cases**: 18784 NB2 and 33472 NB8, all table rows at every
vector position, all 32 caller scales within 49 unique scales/boundaries, 15 gain
edges, 183 structured signed32 gains and 4096 random cases per mode.

BigInt independently evaluates all three quantizers above. Firmware codebook
bytes match the pinned Xiph source. Actual LPM addresses equal the expected
forty addresses for every case. SRAM hooks check exact index-read bounds and
observe 0 output reads / 80 output byte writes in each fused call, versus 80/160
in the two-pass reference. Output/indices guards and 156768 monitored GNU
callee-saved/r1 returns pass. Valid overlapping gain/mode argument registers
are retained while other saved registers are randomized.

The standalone two-pass reference uses 608 -> 604 MULs/subframe for NB2 and
604 -> 602 for NB8 after fusion, primarily eliminating destination-address work.
Its controller takes 5720..5746 -> 4901..4927 cycles for NB2 and 5651..5679 ->
4875..4903 for NB8. Direct new leaves take 4870..4896 and 4845..4873 respectively.
These include RET. The test-only dispatch wrapper is absent from production;
complete-image measurements below include real inlining and caller effects.
No C decoder is executed or timed; isolated C vector arithmetic is tested.

## Complete-image measurements

Both old and new images pass each full 18-stream/10627-frame corpus, 42508 matched
raw decoder frames total, plus reset checks. Each mode covers 6467 natural RU/EN
frames, 4096 coverage and 64 padding frames. Every PCM word matches the unchanged
independent compact-WB reference. Each recording's rounded mean and maximum
improve by exactly 3252 cycles for WB5.75 and 3428 for WB7.75.

| Bare decoder | WB5.75 before | WB5.75 fused | WB7.75 before | WB7.75 fused |
| --- | ---: | ---: | ---: | ---: |
| Speech cycles/frame | 243193.286 | 239941.286 | 243463.107 | 240035.107 |
| Decoder CPU at 16 MHz | 75.998% | 74.982% | 76.082% | 75.011% |
| Complete-corpus mean cycles | 243995.715 | 240743.715 | 244605.527 | 241177.527 |
| Complete-corpus max cycles | 254975 | 251723 | 250547 | 247119 |
| Flash | 25158 B | 25394 B | 25158 B | 25394 B |
| Static SRAM | 1289 B | 1289 B | 1294 B | 1294 B |
| Peak stack | 219 B | 199 B | 219 B | 199 B |
| Free SRAM at peak | 540 B | 560 B | 535 B | 555 B |

Speech means weight rounded recording means by frame count. Relative speech
time improves 1.34% / 1.41%, with 236 B additional Flash and 20 B less peak stack.
Static SRAM is unchanged. A matched three-stream/384-frame screen also compares
the outlined and selected inline dispatch: inlining saves another 124/128
cycles/frame, 22 B Flash and 3 B stack, beyond fusion itself. The small dispatcher
has a single production caller; no arithmetic routine is duplicated to inline it.

| Continuous output | Frames | Extra cycles/frame | Min queue | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| WB5.75 IRQ, ready RAM | 10627 | 9600 (3%) | 14 | 406 B | 0 |
| WB7.75 IRQ, ready RAM | 10627 | 9600 (3%) | 20 | 401 B | 0 |
| WB5.75 scheduled SPI | 2200 | 0 | 23 | 403 B | 0 |
| WB7.75 scheduled SPI | 1800 | 0 | 29 | 398 B | 0 |

Each output run preserves full recording history and exact s16/PWM. Timers and
interrupts remain active; output intervals stay within 990..1010 cycles. IRQ
images occupy 25854 B Flash, with 1430/1435 B static SRAM and 212 B observed stack.
SPI captures use 25920 B Flash, 1427/1432 B static SRAM and 218 B stack. Actual
SPI/CS reads 33000/36000 bytes starting at 0xff80, crossing 64 KiB through the
unchanged shared W25Q128 model. These are ISA-simulator measurements, not board
or analog measurements. Ready RAM excludes transport; SPI has no added load.

Both APIs pass 1024 mixed frames with 6144 NB / 7168 WB rejected calls, padding
and reset. WB observes 820 calls per new leaf: 495280 NB2 MULs and 493640 NB8 MULs.
Other modes, rejected packets and the NB API execute no new high-band leaf.
Fully enabled pure NB2.15 and four minimum NB8/NB11/WB9.8/WB12.8 images rebuild
byte-identically, retaining their earlier evidence. This stage does not claim
fresh full all-feature WB3.95/WB9.8/WB12.8 timing; mixed API tests do check their
PCM among mode switches.

Single-feature NB8-only/WB5.75 and NB2-only/WB7.75 ASM images pass 384-frame screens
and omit the unused kernel. Their Flash sizes are 19274/18430 B. Corresponding C
images compile/link only, 22354/21936 B, with no ASM leaf. All-feature C SPI
controls compile/link only, 31256 B each. The self-contained 21-source C11 export
links without assembly. The existing compact Q7/16-tap QMF is unchanged; exact
PCM here refers to that established compact profile, not full 64-tap Xiph QMF.

## Reproduce and audit

`reports/low-fusion-admission.json` binds the exact sources, baseline admission,
reports and firmware hashes. Before-source hashes are checked against the
parent admission. The screen manifest hashes the first 128 frames from the same
three source streams per mode. Older reports stay unchanged; generated firmware,
PCM, logs, DLLs and the WASM model are not committed.

```sh
python Codecs/Speex/AVR/tests/build_low_fusion.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_low_fusion.mjs Codecs/Speex/AVR/build/low-fusion-unit
python Codecs/Speex/AVR/tests/build_low_fusion_admission.py --avr-gcc avr-gcc --baseline-root <parent-codec-root> --low-corpus <low-corpus> --spi-corpus <spi-corpus>
python Codecs/Speex/AVR/tests/run_low_fusion_admission.py --phase before --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat for phases after, irq and transport-api.
python Codecs/Speex/AVR/tools/build_wb.py --export-c <new-export-dir> --low-rates 7 --enable-nb4
python Codecs/Speex/AVR/tests/check_refill_c_export.py --clang <windows-clang> --export <new-export-dir>
python Codecs/Speex/AVR/tests/audit_low_fusion.py --corpus <low-corpus>
```

The outlined comparison is a retained experiment; full accepted admission does
not require rebuilding that variant. Template/control/register adaptations are
original project work; retain the existing Xiph codebook/algorithm BSD notices.

## Remaining unmeasured candidates

- NB8 coefficient 0 is now implemented and measured in the subsequent
  [zero-prediction stage](WB_FORCED_ZERO.md), with exact innovation/state.
- A dedicated one-tap nonzero NB8 kernel may eliminate the unused outer
  products and history loads from the reused three-tap primitive.
- The forced-prediction identity `(x*(c<<7)+4096)>>13 == (x*c+32)>>6`, c 0..63,
  permits a smaller exact product; measure an explicit C/AVR implementation.
- `innovation.S` groups unrelated functions in one section. Investigate linker
  reachability and shared-label ownership before splitting sections; do not
  discard the common zero10/variable-count body or change its ABI/timing blindly.
