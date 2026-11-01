# Speex NB1 development for ATtiny88

Development branch: `codex/speex-attiny88`. The verified decoder target remains
ATmega328P. ATtiny88 support has not been established. Preserve the existing
ATmega defaults, portable C interface, fixed-point reference, and corpus proofs.
Keep all Tiny88 specialization explicitly selectable.

## First experiment: establish the baseline and NB1 reachability

Pin the source, official device definitions, compiler, flags, and existing NB1
packets. Build the actual ATtiny88 C baseline with assembly disabled. Record
program Flash, tables, `.data`, `.bss`, decoder state, caller buffers, and the
linker's result. The generic history alone contains 305 `int16_t` elements
(610 bytes), exceeding the device's entire 512-byte SRAM. Record a real RAM
overflow; do not enlarge the linker memory region to obtain a claimed fit.

Trace NB1 initialization, frame/subframe decoding, reset, and error handling
against the existing exact upstream reference and corpus. Inventory each state
field, array index range, table, and function reached by NB1. Separate static
reachability arguments from observations on test packets. In particular, prove
which history values the vocoder path reads and how long they remain live.

**Go:** a documented NB1-only live-state budget leaves a credible path to 512
bytes including output buffering, stack, and interrupts. **Stop:** required
live state already exceeds that budget, or removing allegedly unused state
changes exact output. Report the constraint before attempting wider changes.

## Exact specialization and RAM reduction

1. Add an opt-in NB1-only build. Remove NB3 tables and code through proven
   reachability, retaining the existing default modes. Remove pitch-history
   storage or work only where the NB1 path provably never needs it.
2. Map lifetimes across initialization and every subframe. Reuse scratch storage
   only when live ranges do not overlap; preserve integer widths, arithmetic,
   reset semantics, and legal C object access. Verify exact PCM and PWM after
   each focused change, including malformed input and frame boundaries.
3. Evaluate incremental subframe/sample emission to avoid a resident 160-sample
   output buffer. Bound the output queue from measured producer timing. Include
   queue, decoder, caller state, worst observed stack, and interrupt nesting in
   the same SRAM budget; moving an array onto the stack does not save RAM.

## AVR25 arithmetic and speed

ATtiny88's AVR25 core has no hardware multiply. Profile actual hot paths before
writing software multiply/shift/add assembly. Retain an equivalent, explicitly
selectable C fallback on AVR itself. Enable assembly only with both a supported
architecture check and an explicit opt-in define; use manufacturer/toolchain
CPU macros. Respect the ABI, clobbers, zero register, and interrupt behavior.
Keep arithmetic selection separate from Flash/RAM access and storage transport.
Preserve reusable techniques and their provenance in `docs/avr-asm-cookbook/`.

Compare C and assembly on identical source, packets, clock, and memory settings.
Measure complete Flash, stack, average cycles, worst producer/output gaps, and
queue occupancy. RAM reuse is admitted only if matched decoding speed does not
regress. A larger arithmetic backend needs a measured benefit and a complete
Flash accounting.

## Admission and limits

- Require exact full PCM/PWM against the independent fixed-point reference and
  existing corpus, plus boundary, reset, malformed-packet, and C/ASM parity tests.
- Require a real Tiny88 link within 8 KiB Flash and 512 bytes SRAM, including
  firmware overhead and a defensible stack/interrupt margin. Report compressed
  audio storage separately, and include it in total Flash when stored internally.
- Establish 8 kHz playback with interrupts active on the actual AVR25 target
  profile, with exact output and zero underruns. At 16 MHz each sample period is
  2,000 cycles; buffering must cover measured bursts, not just the mean. Host or
  unpaced simulation alone does not establish real-time support.
- Stop or retain an experimental profile if fit, exactness, speed, or active-IRQ
  timing fails. Do not publish a ready Tiny88 firmware or support claim before
  all gates pass.

If exact NB1 specialization cannot meet the budget, reduced precision is a
separate, explicitly lossy experiment with new quality evaluation. It must not
replace or inherit the exact decoder's proofs. This plan authorizes no such
precision change by itself.
