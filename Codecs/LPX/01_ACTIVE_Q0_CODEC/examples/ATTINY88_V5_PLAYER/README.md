# ATtiny88 / 16 MHz LPX v5 player

The opt-in AVR25 software arithmetic and optional short ISR play the measured
P4/P6 streams at 8 kHz without hardware multiplication. A 32-byte circular FIFO
uses 31 slots and prefills24. The existing SRAM512 workspace profile is reused.
Static SRAM is 435 bytes, including the FIFO; the selected matrix observes at
most67 bytes of stack. Do not add application RAM or IRQ load without another
complete timing/stack check.

The full-image default limit is **6.5 KiB =6656 bytes**, including compressed
audio, initialized data, startup, decoder and ISR. The builder rejects larger
images and proves that the embedded audio array exactly matches the input.
This reserves 1536 of 8192 Flash bytes; use the actual bootloader origin as
`--flash-limit` if the board reserves more. Nothing is flashed automatically.

The selected P4 example occupies 6.137 KiB; the real P6 prefix 6.268 KiB.
P6 synthetic stress images occupy 6254/6268 bytes. Complete repeated playback
with active IRQs reproduces portable C PWM exactly. Average decode costs are
about 1536/1510 cycles for the P4/P6 ROM examples and 1804/1884 cycles for the
two dense P6 stress cases. The target 1500 cycles is approached by the ROM
examples, not established as a worst-case bound. The FIFO covers individual
frame conversions exceeding 20k cycles.

OC1A/PB1 supplies62.5 kHz fast PWM. Timer0 CompareA requests a new sample every
2000 CPU cycles. The foreground drains and stops after the last sample;
Timer1 keeps the final duty. This is a standalone one-shot/reset-chain driver,
not an Arduino sketch sharing timers or interrupt vectors with a framework.

## Build and independently verify

Requirements: Python3 standard library, AVR-GCC 7.3.0/AVR-LibC, host g++,
simavr 1.6 development headers/library and libelf. Existing Linux tools can
be used from Windows with `--wsl Ubuntu`. From the repository root:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/verify_attiny88_player.py \
  web-player/audio/lpx-bread/compact.lpx build/tiny88-player
```

The verifier explicitly enables arithmetic ASM and the selected ISR. It builds
the full AVR image and a separate native **dynamic-header C reference**, runs
the actual linked ELF with both hardware timers active, and compares every
PWM byte. `verification.json` must contain `accepted:true`. It also requires
exact sample/timer counts, no underruns, empty final queue, timer stop, bounded
output intervals, positive observed stack margin and the complete Flash cap.
No firmware counters or test media arrays are inserted for timing measurement;
zero-byte ELF symbols delimit the production decode region.

For build-only use:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/build_attiny88_player.py \
  web-player/audio/lpx-bread/compact.lpx build/tiny88-build --enable-asm --asm-isr
```

Build-only outputs remain marked `timing_verified:false`. Without explicit
ASM flags, C is selected. `--c` and `--c-isr` on the verifier independently
select C arithmetic and C ISR. The measured C arithmetic does not meet8 kHz.
The C ISR is an admitted alternative for the measured P4 example.

ROM builds pin the existing stream's format flags and two fixed filter
constants; mismatches are rejected. No codec parameters, compressed bytes or
quality are changed. Generic library builds with no fixed-header defines
retain dynamic parameters and other architectures' portable interface.

The full IRQ costs 40 cycles (4-cycle hardware entry plus 36 cycles from the
vector through completed RETI). The simavr 1.6 adapter explicitly accounts for
both boundaries before admitting playback.

The short ISR reserves r2/r3 with whole-program `-ffixed-r2 -ffixed-r3`.
The builder audits **linked ELF function bodies**, including library code,
for uses outside the ISR and standard ABI save/restore helpers. Handwritten
arithmetic and ISR selection are separate, and real device/memory macros are
preserved. The official ATtiny_DFP 3.4.278 header is reused in place; a separate
header-derived object configures the observer, never the production ELF.

## Reproduce the complete matrix

Run these in Linux/WSL from the repository root:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_attiny88_matrix.py build/tiny88-matrix
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py build/tiny88-math
```

Then run the project's existing Node executable from the same checkout:

```sh
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/tiny88-math
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_fixed_header.py
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_sram512_profile.py
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_math_backend.py
```

The matrix covers real P4, an exact whole-packet real P6 prefix, P6 extra
innovations with changing/clustered spectra and lag 18/145, long reset chains,
ten partial/complete tails, C ISR, C arithmetic rejection, FIFO16 rejection,
and Flash-cap rejection. A separate full P6 timing-only run explicitly raises
the limit to 8192; its7354-byte image does not fit the requested bootloader
budget. Generated audio, logs, ELF/HEX and reference PWM stay in ignored
`build/`. [Anonymous measurements](measurements.json) retain numerical results
and source hashes without audio or private input fingerprints.

## Accepted 2/3 kbit/s speech and size optimization

`--enable-sparse80` explicitly enables v8/mode15 for 2 kbit/s speech; ordinary
v5/P4 carries the accepted 3 kbit/s selections. Both use the same decoder,
FIFO, ISR and selectable C fallback. New source streams are not repacked or
trimmed by the firmware builder.

The final 54 four-second selections were rebuilt and replayed on Tiny88:
1,728,000 exact PWM samples, active interrupts, zero underruns. All 27
2 kbit/s images fit the 6.5 KiB limit (5.826–6.227 KiB); 12 of 27 3 kbit/s
images fit. The other 15 pass timing under the explicit 8 KiB experiment cap
but occupy up to6.561 KiB and are not admitted with the bootloader reserve.
The default builder still rejects images exceeding6.5 KiB.

The bounded size changes save6–134 bytes with no increased mean decode cost
on any of these54 streams. Exact 14-step fixed-Q14 attenuation discards unused
product bits; zero history skips a whole MAC subtraction. The measured ASM
recipe also uses `-fno-inline-small-functions`; the C recipe is unchanged.
All18 older matrix configurations retain their intended acceptance/rejection.
The P4 ROM changes6418→6284 bytes and1574.49→1536.23 mean IRQ-active cycles;
its observed stack changes67→60 bytes. The real P6 prefix saves36 bytes and
30.39 cycles/sample. [Anonymous before/after measurements](lowrate-size-measurements.json)
pin the54 workloads and the exact source contexts.

With private inputs available, reproduce the paired corpus replay using
`tests/verify_attiny88_lowrate.py MANIFEST build/tiny88-lowrate --jobs 2`;
add `--wsl Ubuntu` on Windows. Only its anonymous `summary.json` is suitable
for retention; media, bindings and other outputs remain in ignored `build/`.
For complete fixed-Q14 arithmetic/ABI coverage, add `--exhaustive-fixed` to
`verify_avr25_math.mjs`: 482,710 cases per C/ASM/forced-generic backend with
active interrupts, including all signed16 states for seven coefficients.

The original bounded simavr model binding covers CPU memory, PortB and the two
timers used by this image. It is not a full ATtiny88 board model. Physical-board
and analog behavior are unmeasured;16 MHz is the requested clock, above the
ordinary device speed rating. The [cookbook](../../../../../docs/avr-asm-cookbook/lpx-avr25.md)
records techniques, correctness constraints, measured limits and references.
