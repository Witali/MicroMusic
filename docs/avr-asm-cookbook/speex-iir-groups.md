# Cache coefficients according to their last use

Classic AVR5 / ATmega328P, hardware MUL/MOVW, GNU ABI, AVR GCC 7.3.0;
measured with `-Os -flto -mcall-prologues -mrelax`. Original project technique;
existing Speex/AVR201 provenance stays with the sources. Explicit C remains
selectable on AVR; unsupported or non-enabled ASM defaults to C.

When a circular-history loop has a fixed multiple of its length, process one
whole group before resetting its cursor. A private subroutine shares the
large arithmetic body without checking wrap on each output:

```asm
    .rept 40/IIR_ORDER-1
    rcall .Liir_group
    .endr
    ; External epilogue clears r1 and restores the saved registers.
.Liir_group:
    ; Count exactly IIR_ORDER outputs through the shared body.
    ; Then rewind Y once and return to the private assembly caller.
```

Immediate rounding biases free the old constant register for the count.
The obsolete cursor-limit/count pair holds a fourth coefficient instead.
MULSU can read r16:r17 directly, avoiding a scratch MOVW; operands in lower
registers still need copies into its supported r16..23 range.

Reuse that high pair differently during warm-up: the last **old** coefficient
changes only after the last warm output. Preload it from ages, not new `den`,
and use it on every warm sample. After warm-up the same pair receives the
first new coefficient. This is exact across changing coefficients and full
signed16 data, with no additional stored state.

The [shared assembled kernel](../../Codecs/Speex/AVR/src/iir_kernel.inc) saves
247 cycles/order-10 block and 238/order-8 block. Separate prototypes measure
the cursor hoist, grouped loops, fourth cache, direct operands and old-tail
cache. The latter alone saves another 36/28 cycles without increasing size.
The private RCALL costs two stack bytes on this target. r1 may stay dirty
across private RET, with no C call; clear it at the external ABI boundary and
require IRQ restoration of interrupted r1/SREG. Other return-address widths
and ABIs need their own measurements.

Full NB8 improves 1.0278%, WB12.8 0.8117%, including a separate exact
three-instruction cosine negate. Flash falls 4/6 B, static SRAM is unchanged;
whole WB stack grows two bytes. Direct C/ASM/BigInt and transposed tests pass,
including 75,479 IIR IRQ boundaries and dirty-r1 private returns.
[Workloads, PCM/PWM admission and reproduction](../../Codecs/Speex/AVR/IIR_GROUPS.md).

Final sources pass 198 production PWM images with active interrupts and zero
underruns. Both WB modes also pass 10,563 full-history frames each through
the production ISR/queue with ready RAM packets and 8% extra foreground work:
minimum queues 6/5, free SRAM 437/429 B. This is simulator evidence; transport
latency and physical hardware were not measured.

## Second old-age cache: measured isolated candidate

The following continuation is now assembled and measured in isolated kernels.
It is **not integrated into the production decoder or admitted for playback**.
The explicitly selectable production C fallback is unchanged.

During warm-up, r12:r13 retain only the state base. Rewind Y with a fixed
subtraction once after warm-up and use the freed pair for the second-last old
coefficient age. That age remains constant for the first `order-1` outputs.
After output `order-2`, `IIR_FINISH 1` leaves the newly written
`den[order-2]` in r18:r19: forward it directly into the cache before the final
warm output. Reading the old age for that last output would be incorrect.

```asm
    ; Preload old age[order-2] into r12:r13; warm count is order-1.
    clt
    ; The existing warm body uses cached r12:r13 and finishes the age write.
.Lwarm_phase:               ; Reached when its warm counter becomes zero.
    brts .Lsteady_setup
    movw r12,r18            ; Newly written den[order-2], not the old age.
    set
    inc r3                  ; Exactly one final warm output.
    rjmp .Lwarm_sample
.Lsteady_setup:
    sbiw r28,2*IIR_ORDER    ; Return Y to its base without retaining that base.
```

CLT initializes the T phase explicitly. The MAC/finish arithmetic leaves T
untouched; GNU AVR compiled interrupts must preserve the interrupted SREG,
including T and a possibly nonzero r1. There is no added private call, stack
slot, buffer or state field. Existing arguments, aliases, modulo-32 summation,
rounding, saturation and coefficient ageing remain intact.

With the same AVR GCC 7.3.0 options and existing both-order primitive fixture:

| Kernel | Before min/max cycles | Candidate min/max cycles |
| --- | ---: | ---: |
| Order 8, forty outputs | 11416 / 11657 | 11404 / 11645 |
| Order 10, forty outputs | 13762 / 14003 | 13744 / 13985 |

The combined isolated image grows 24 B (3672 -> 3696 B). Static SRAM and
stack are unchanged: 20 B own ASM stack, 32 B whole fixture peak. Both
fixtures pass 7374 cases / 14748 C+ASM calls and 294960 samples per path,
including all 256 state low-address bytes, in-place/separate buffers, changing
coefficients, complete signed16 input/negation, exact guards and ABI/r1 returns.
The forced C object files are byte-identical between the builds.

The candidate IRQ probe passes 75463 instruction-boundary injections, including
50077 interrupted nonzero-r1 states. All 32 registers, SREG, PC and SP return
unchanged; the interrupted and uninterrupted instruction traces match. This
is a boundary-preemption proof, not production timer latency or queue admission.
Four order-eight plus four order-ten invocations would save 120 cycles/WB frame
before linker/caller effects; **that whole-decoder saving is predicted, not
measured**. Active production PWM/IRQ and whole-corpus PCM/reset checks are
still required before integration.

The [isolated screen driver](../../Codecs/Speex/AVR/tests/screen_iir_second_cache.py)
preserves the exact source transformation and pins both normalized kernel
hashes. It copies sources into ignored build directories, preserving production
files, then uses the existing isolated C/ASM/BigInt and boundary-IRQ probes:

```sh
python Codecs/Speex/AVR/tests/screen_iir_second_cache.py --avr-gcc avr-gcc --node node
# Audit already executed, hash-verified images without rerunning measurements:
python Codecs/Speex/AVR/tests/screen_iir_second_cache.py --phase audit
```

The [retained screen](../../Codecs/Speex/AVR/reports/iir-second-cache-screen.json)
and ignored `build/iir-second-cache-screen/summary.json` bind LF-normalized source hashes,
exact firmware/C-object/header hashes, measured limits and IRQ results. Binary
and manufacturer-header hashes use exact bytes. Other cores, toolchains,
return-address widths and ISRs need their own evidence.
