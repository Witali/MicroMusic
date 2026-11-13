# LPX v9: simplify wire decoding without expanding compressed data

Original MicroMusic work for ATtiny88 / AVR25 without MUL, GNU AVR ABI,
AVR-GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax`, the universal FIFO44 recipe,
software product unroll2 and explicitly enabled arithmetic/ISR ASM. Portable
C remains separately selectable, including on AVR. These are simavr 1.6
measurements at requested 16 MHz / 8 kHz, not physical-board measurements.

The [wire specification](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/LPX9_FORMAT.md)
defines a 13-byte header with all variable recording parameters. Spectral
packing and DSP stay shared with v5. The new representation:

- Removes nine header bytes by using a short version identifier, the existing
  sample-count bound and format-defined packet geometry.
- Omits seven lag bits when pitch gain is zero. The product is exactly zero
  regardless of the lag/history, including separate signed rounding.
- Omits final packets that playback never reads, retaining every field that
  the current 40-sample pulse reader consumes, even for a shorter sample tail.
- Reindexes a P6 pulse pair into two low coordinate bits per position and a
  5x5 high-coordinate index. A25-byte Flash table replaces division by 20 and
  its software constant products, with the same nine-bit data cost.
- Reads each P4 position/sign as one 5-bit field instead of two reader calls.

For every valid input v5 stream, conversion never adds payload bits and removes
nine header bytes. No acoustic search, new codebook or coefficient quantization
is involved. PCM16/PWM remains exact. Ignored zero-gain lag values and unplayed
padding are not preserved as original bytes when repacking back to v5.

## Matched complete playback

[Source-bound measurements](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/v9-measurements.json)
compare eight complete public P4/P6 phrases and six synthetic controls with
changing/clustered spectra, lag 18/145, extras and boundary filter coefficients.
Each v9 full playback is checked against portable C and the actual v5 output.

| Quantity | V5 | V9 |
| --- | ---: | ---: |
| Universal program excluding verified audio | 5471..5472 B | 5384..5385 B |
| Complete image including each test stream | 5942..7370 B | 5834..7266 B |
| Static SRAM / peak observed stack | 447 / 60 B | 445 / 60 B |
| Complete ISR, hardware entry through RETI | 42 cycles | 42 cycles |
| Underruns | 0 | 0 |

The program now saves 86..88 B, in addition to smaller audio files. On the four
public phrases, compressed data shrinks as follows:

| Phrase | P4 data bytes, v5 to v9 | P6 data bytes, v5 to v9 |
| --- | ---: | ---: |
| Chego | 536 to 522 | 791 to 776 |
| Otvechaesh | 470 to 450 | 692 to 671 |
| Vinni | 1243 to 1200 | 1862 to 1820 |
| Bread | 1008 to 996 | 1899 to 1881 |

Thus these files save 12..43 B (about 0.95..4.26%). All fourteen IRQ-active mean
decode costs improve; exact before/after means, maxima and
queue minima are in the receipt. PCM/PWM bytes stay identical. Observed stack and the 42-cycle ISR are preserved. V9 static SRAM is now
445 B; the conservative margin increases from four to six bytes.
The admission remains bounded to these standalone workloads; extra application
state/IRQs and other streams need their own timing/stack check.

## Cold parser placement matters

With the shorter header, GCC/LTO partially inlined `begin()` into `main()`:
the screened main grew from 2728 to 2984 B and collided with the 512-byte stack
boundary on the first public P4 run. Marking the v9 `begin()` non-inlined keeps
cold setup out of playback's persistent frame and restores the measured 60-byte
stack. Scope this attribute to v9. Applying it to the old fixed-header player
grew some images and stack frames; the old recipe is retained.

The same compiled portable v9 decoder passes all 400 valid pulse pairs and all
112 invalid codes, 60 combinations of recording/filter settings, count 64000,
partial tails, ROM/callback switching, both memory profiles, both cursor modes
and both remaining-count strategies. An additional 16,000-sample full AVR playback
checks all 400 valid pairs with IRQs, exact v5 PWM and zero underruns.
Read to the final false `next()` and
check `error()` to validate exhaustion, including partial sample tails.

A separate data-only screening of globally selectable Rice parameters found
only 0..2 bytes of potential spectral savings on these public streams. No
runtime state/decoder machinery for that idea was added; speed/code-size
benefits were not measured. Directly storing LPC anchors was not adopted:
removing conversion alone is insufficient without proving smaller audio data.

Reproduce using the commands in the wire specification. Old v5/v8 data and
published speech recipes remain on their existing paths; selecting v9 is a
format choice, independent of CPU arithmetic and hardware memory access.

## Word metadata and synchronized C reference (2026-11-10)

V9 serializes a 16-bit count, and even invalid counts cannot exceed 65535.
Store `sampleCount_` as `uint16_t` only for v9; keep the existing 32-bit public
accessors and the version 5 field. This saves 34 program bytes and 2 static SRAM
bytes in every matched v9 build. Frame decode instructions/timing stay exact.
All variable recording parameters still come from the file; compressed data
and both PCM/PWM output streams remain byte-identical.

The [matched v9-to-v9 receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/v9-next-measurements.json)
replays the original `f7481ef9` ELFs and verifies loaded Flash bytes, compiler
recipe, original timing and waveform before comparing the new binaries. Its
current results include later exact arithmetic work: 40 B less program Flash,
lower CPU cycle totals, zero underruns, 60-byte observed stacks and 6-byte
margins. The word-only result above is historical. SRAM is 445 B including FIFO44.
These remain standalone simulator bounds, not a board/application guarantee.

The [active C reference](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/C_REFERENCE.md)
uses the same word metadata and explicitly selects C arithmetic. Its batch
builder/cache now select v9, accept the 13-byte header and drain EOF for partial
sample tails. The cache includes C arithmetic headers and the selected format.
Tests compare PCM16/PWM and invalid-count metadata, reject trailing bytes,
check old-format subprocess output, and invalidate a copied arithmetic header.
Historical reference directories remain frozen.

The observer now also reports `decode_cpu_cycles` and `decode_irq_cycles`.
At each decode boundary it subtracts completed IRQ durations, including the
calibrated four-cycle hardware entry and completed RETI, from elapsed cycles.
Thus `decode_cycles = decode_cpu_cycles + decode_irq_cycles`. Replaying an
unchanged ELF preserves every older timing/PWM field. This separates interrupt
phase changes from changes to decoder work; it does not disable interrupts.

Screening used the previous 447-byte state and bread P6, with the same compiler
and full IRQ playback. All arithmetic identities retained exact output:

| Rejected candidate | Measured reason |
| --- | --- |
| Direct bounded `/5` identity `q=(h-(h>>2)+(h>=20))>>2`,0..24 | 5429 program bytes versus 5425; mean wall time 1589.826 versus1589.430 cycles/sample |
| Keep the quotient scaled by4 | 5415 B, but mean wall time 1589.636 cycles/sample; rejected for slower decoding |
| Read both P6 amplitudes together / split P4/P6 bodies | Stack collision; also failed with a separate subframe function |
| Branch-free P4 sign | Compile-only screen grew the program from 5424 to 5540 B |
| Narrow P4 offset cast | Saves 6 B and speeds P4, but adds one CPU cycle per P6 pulse packet; not retained |

The 25-entry table and original pulse arithmetic remain. The accepted change
is the count-width reduction in the shared C header, with no arithmetic ASM
or wire-format change at that revision. Later shared arithmetic improvements
are recorded in the [current 1500-cycle attempt](lpx-universal-tiny88.md#exact-work-reduction-toward-1500-cyclessample-2026-11-10);
the mean target is not yet met on public speech.

## Shared sparse80 reader and pulse gaps (2026-11-10)

The universal v9 reader now accepts file profiles 4, 6 and 15. Profile 15
losslessly repacks the existing v8 sparse80 syntax. Share spectrum conversion,
LPC and output filtering; branch only for metadata cadence and pulse syntax.
Keep profile15 as its raw flag byte: its low bits already select six-bit
spectra and bit3 identifies sparse80. No additional persistent field is needed.

After sorting/merging a P4/P6 packet, turn its absolute positions into gaps:
`gap[i] = position[i] - position[i-1] - 1`, in reverse order. The first gap is
the first position. Decrement the current pending gap on non-pulse samples;
consume a pulse when it reaches zero. Sparse80 is the same one-entry case.
This removes sample-phase multiplication without changing pulse times, merged
amplitudes or pitch-history feedback. Narrow the excitation sum only after
proving the rounded pitch term (-28..27) plus innovation (-16..16) fits int8.
The portable C reference performs these same operations; arithmetic backend
and hardware memory access remain separate, explicitly selectable settings.

Measured target: ATtiny88 / AVR25 without MUL, 16 MHz, avr-g++ 7.3, existing
SRAM512 profile, explicit ASM enable, software-product unroll2, and the
standalone reserved-register player ABI. FIFO32/prefill24 admits the new
reader and reduces the complete IRQ from42 to38 cycles. Do not carry that
ABI into a general interrupt handler without its register contract.

| Full-player measurement | Before (`e32e0c66`) | Three-profile v9 |
| --- | ---: | ---: |
| Default FIFO | 44 | 32 |
| Maximum program excluding verified audio | 5385 B | 5605 B |
| Growth vs smallest former production program (5384 B) | — | 4.105% |
| Program with matched FIFO32 | 5528 B | 5605 B maximum (+1.393%) |
| Static SRAM | 445 B | 433 B |
| Peak observed stack / conservative margin | 60 / 6 B | 67 / 11 B |
| Complete IRQ | 42 cycles | 38 cycles |

Twenty-two complete workloads pass exact native-C/PWM comparison and zero
underruns with both timers active: the former14 cases, two public sparse80
files (including a real1.93 kbit/s file), five sparse boundary/filter controls,
and all400 P6 pulse pairs. The slowest synthetic sparse80 mean is1771 active
CPU cycles/sample including IRQ. Mean values do not bound individual frame
conversion; minimum observed queue occupancy is4. Existing P4/P6 compressed
data and output stay exact. Same-FIFO Chego mean decreases from1613 to1606
cycles; relative to the previous FIFO44 production recipe it increases from
1574 to1606. The1500-cycle target remains unmet. No physical board was measured.

The byte-level position domain, all signs, tails, maximum count, mixed-profile
input switching and strict EOF are independently tested by the selectable C
paths. The old two-profile receipts remain unchanged and source-bound to their
historical revision; the new admission verifies their exact Git contents too.
[Current source-bound measurements](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/v9-sparse80-measurements.json).

Reproduce with the two archived baseline directories (the first contains the
old14-case `current` ELFs; the second is the former program built with FIFO32):

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_attiny88_v9_sparse80.py \
  build/sparse80 BASELINE_14_CASE_DIRECTORY BASELINE_FIFO32_DIRECTORY --wsl Ubuntu
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_speech_v9.py
```

Rejected measurements: retaining FIFO44 collided with the stack; outlining
`next()` reduced Flash but slowed decoding by about54 cycles/sample and left
only3 bytes of margin. Packet-gap sharing and FIFO32 are retained instead.
This is original project code, using the existing vendor-derived register
definitions and licensing. No external assembly implementation was copied.

## Clamp excitation only when adding a pulse

On ATtiny88 / AVR25 with the GNU AVR ABI and AVR-GCC 7.3.0, the universal
compact v9 build selects this path with `LPX4_ENABLE_ASM=1`. A prediction
alone is in −28..27. The code tests the pending pulse once and clamps to
−32..31 only after adding its amplitude. It stores the decoded history code
once. The caller checks parser errors before synthesis.

For the eight legal gains, let the stored Q4 gain be `2*g`. The fixed
floor is `floor((history*g+4)/8)`. Three LSR/conditional ADD/ROR rounds
produce the unsigned quotient; subtract `32*g` for a negative history
byte. The existing gain-14 shortcut and the selectable C arithmetic are
retained. Testing all 2048 combinations of signed-byte history and legal
gain covers the handwritten AVR path.

On the same 22 IRQ-driven P4/P6/sparse80 workloads, the linked application
shrinks from 5408–5409 to 5360–5361 bytes excluding embedded audio. With
FIFO32/prefill24 at 16 MHz and 8 kHz, the largest decode CPU mean plus IRQ
falls from 1720.77 to 1664.87 cycles per sample. All PWM matches and there
are zero underruns in simavr.
[Toolchain, per-workload measurements and rejected variants](../../Codecs/LPX/research/tiny-v9-pulse-pitch-2026-11-13/README.md).

## Experimental Rice0: smaller data, no production admission

An opt-in v9 flag can change six-bit LSF delta Rice coding from k1 to k0 while
retaining gap/repeat coding and every decoded parameter. Complete-file selection
keeps exact original bytes on ties or growth. Across 318 saved files, 271 shrink
and 47 fall back, saving 19,951 bytes (4.85%) with exact C PCM/PWM output.
This is lossless entropy repacking, not an audible quality improvement.

The prototype has not met the full no-regression timing/size gate and is kept
outside production. Its private C reference retains the compact error check;
architecture/backend selection and the C fallback are unchanged. Production
sources, firmware images and the source-bound receipts above remain intact.
[Protocol, reproducible reader, native matrix and limitations](../../Codecs/LPX/research/v9-rice0-2026-11-10/README.md).
