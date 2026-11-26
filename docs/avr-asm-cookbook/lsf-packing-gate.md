# LSF packing gate and unchanged-decoder profiling

Measured on 2026-11-26 with ATtiny88/AVR25 (no MUL) and ATmega328P/AVR5,
AVR-GCC 7.3.0, GNU++11, GNU ABI and simavr 1.6. Production source and assembly
remain unchanged. See the [research report](../../Codecs/LPX/research/lsf1-2026-11-26/README.md)
and [full CPU evidence](../../Codecs/LPX/experimental/LSF1/avr/README.md).

## Gate a new format before rewriting the decoder

An exact LSF shared-exponent/group cost model chooses native Rice for all 386
frames of eight existing files. Forced groups predict +13.16% complete bytes;
adaptive escape costs save nothing. Four one-bin proposals per file also fail
strict complete-output admission. No new decoder or speculative full AVR
matrix is implemented after that result.

Native byte reserialization, including padding, is stronger evidence than a
rounded file-length comparison. Count escape, group lengths, widths and shared
exponents before attributing savings to mantissas.

## Do not reuse the narrow native-delta proof for exponent-scaled data

The proposed groups can produce signed deltas −4096..4032 or unsigned gaps up
to 8128. A uint8 conversion before checking bounds can wrap an invalid value
into a valid-looking LSF index. Reconstruct with signed32, validate range,
strict ordering and room for the remaining bins (`value <= M-10+i`), then
commit state. This is an unimplemented design/correctness constraint, not
measured decoder code.

## Profile existing firmware without changing its instruction stream

A host-only PC histogram replays four unchanged full-file ELFs with the
original IRQ active. Complete PWM and every original timing field must remain
identical; PC-attributed cycles sum exactly to the decoder CPU count. Flat
shares charge inlined code to its containing function, so `main` is not a
measurement of multiplication alone.

Readers account for 0.51–0.74% of Tiny decode CPU and 1.14–1.70% on Mega;
LSF conversion accounts for about 3–4%. These pilots suggest that parsing alone
has limited CPU upside. They do not establish portable cycle bounds.

## Verify that a tuning selector reaches the active kernel

Eight complete-file pilots keep the source, input bytes, FIFO32/prefill24,
16 MHz/8 kHz clock, timers, gain and ISR fixed. Tiny generic multiply-unroll
4/8/16 produces exactly the same linked Flash bytes and cycles as unroll2;
the active specialized player kernels do not use that setting. Mega existing
function tuning7 increases decode cost by 10.59%, adds 172 program bytes and
raises observed stack from 24 to 42 bytes. Neither setting is selected.

All pilots have exact PWM, zero underruns and positive memory margins. Actual
manufacturer device headers, ISA macros, arithmetic backend selection and the
explicit C fallback remain unchanged. No new assembly is introduced. These
negative results reject the tested settings on the recorded workloads, not
all possible compiler or arithmetic optimizations.
