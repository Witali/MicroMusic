# Compact universal LPX player work

Task baseline: `ead0bdcb0b627532afbf2d7b52fce7f015cf6dbc`.
The target is at most 3072 program bytes for the single-stream Nano player,
excluding audio. Also reduce the shared ATtiny88 firmware, preserve exact
8 kHz PWM and compressed payloads, and retain explicitly selectable C
arithmetic. Additional dialogue infrastructure is outside the 3072-byte cap.

`steps.json` orders focused source transitions. Each retained measurement
pairs 22 actual interrupt-active playbacks per CPU with its stated comparator.
The cases include public speech, P4/P6/sparse80, changing/clustering impulses,
pitch and filter extremes, short tails, and all coordinate pairs.
Media and generated ELF/HEX/log files remain in ignored `build/`.

The successful foreground producer includes decoding, dynamic output gain
and queue publication. CPU cycles exclude IRQ execution; add the complete
IRQ cost when comparing the total budget. The host observer reads actual
ELF-resolved IN/OUT or LDS/STS accesses, without target instrumentation.
The observer extension was checked by replaying the same 44 baseline ELFs:
all preceding timing fields and output bytes remained identical.

Measurements use AVR-GCC 7.3.0 and simavr 1.6 at 16 MHz, SRAM512 profile,
FIFO32 / prefill24, ASM arithmetic/ISR, and the compiler options recorded
in local build receipts. They do not imply a physical-board measurement.
Historical WebUI receipts keep their original source and binary identities;
these paired workload receipts do not claim that new binaries equal old HEXes.

- `gain`: exact gain arithmetic saves 26 B on Nano and 6 B on Tiny.
  See the [technique and bounds](../../../../docs/avr-asm-cookbook/lpx-rom-gain.md).
- `rice`: use the same bounded prefix accumulator on AVR5 and AVR25.
  Nano saves another 10 B (3080..3081 B); Tiny binaries are unchanged.
  All 44 complete IRQ playbacks remain exact without a speed or memory loss.
- `cosine`: omit unreachable node zero from the universal AVR5 table,
  matching the private AVR25 table's bound. Nano saves another 2 B
  (3078..3079 B); Tiny binaries and every measured CPU/memory field are unchanged.
- `halt`: after the final drain, mask interrupts and stop once. The dedicated
  player never returns. This saves 4 B on both CPUs with all 44 playback/CPU
  results unchanged (Nano 3074..3075 B, Tiny 3627..3628 B). Global SREG.I
  intentionally stays zero at the permanent halt; every active IRQ still
  preserves the complete foreground context.
- `lpc`: a single-tap circular AVR5 loop saves another 58 B. Its ten extra
  control cycles use the ten cycles recovered in ROM gain. Compared with
  task start, all 22 Nano producer means and peaks are equal or lower;
  PWM, IRQ, SRAM and stack remain exact. Nano is 3016..3017 B before adding
  higher rates. Tiny stays 3627..3628 B. This step's timing comparator is the
  task-start baseline, not the faster intermediate two-tap implementation.
- `rates`: the same decoder adds file-selected 8/12/16 kHz with nearest fixed
  divisors. This feature costs 40 B on Nano / 36 B on Tiny relative to the
  optimized 8 kHz-only control. Single-stream programs are 3056..3057 B
  (2.984..2.985 KiB) / 3663..3664 B (3.577..3.578 KiB). The final Nano player
  is 60 B smaller than task start; Tiny's additional modes cost a net 26 B.
  The compatibility recipe still saves 100 B / 10 B versus task start.

`sampling-rates.json` records all 132 actual IRQ playbacks. Nano admits 22/22
at every rate; Tiny admits 22/22, 9/22 and 2/22 at 8/12/16 kHz. Unsupported
cases keep their underruns and `accepted=false`. All 44 eight-kHz outputs are
bit-exact with task start, and producer mean/peak plus full IRQ never grows.
Static SRAM stays 417 / 418 B; peak observed stack is 24 / 27 B. Audio input
bytes remain unchanged. Higher-rate fixtures are explicitly header-retagged
timing probes; real rate-aware WAV analysis/encoding is tested separately.

`rate-contract/final.json` binds seven passing source-audio frontend tests,
1,048,576 fixed/float/legacy/compatibility rate-field checks, and 20 additional
C/ASM/ISR/playlist controls with 36,128 exact samples. Both disabled-rate
all-pairs images equal the optimized pre-feature binaries byte-for-byte.
`final-gain-proof.json` repeats the four exhaustive real-target C/ASM gain
probes against the integrated player and headers. The existing 13 host
v9/math/AVR5-reference tests also pass; the former invalid 16000 Hz case now
tests invalid 16001 Hz and explicitly checks all three valid rates.

The source-bound `rice-reader-proof.json` is reproduced with:

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_rice_packet.py build/rice-packet-proof --baseline-ref 57513b10 --wsl Ubuntu
```

Omit `--wsl` on Linux. This requires no media or scientific Python packages.
The native ATmega328P observer covers 28,800 cases per old/new C/ASM backend:
all legal payload values, eight cache positions, byte bounds 0/1/2, both delta
modes and profiles 4/6/15. It checks the full private reader state, live IRQ,
ABI/r1/SP and byte-identical explicit C. Clear-error C/ASM traces match;
the predecessor's private state difference after an already-set error remains
explicitly recorded. Public `next()` guards errors before reaching that case.

`tests/verify_cosine_nodes.py build/cosine-node-proof --baseline-ref 8cf06a50
--wsl Ubuntu` similarly reproduces `cosine-node-proof.json`. All nodes
1..127 are tested 16 times per old/new C/ASM backend on the actual AVR5
instruction model, with active interrupts and context checks. Explicit C
binaries remain unchanged. Node zero is unreachable from validated spectra.

`halt-edge-proof.json` retains a separate pre-gain comparison of 30 stop/error
configurations per CPU: profiles 4/6/15, prefill boundaries, short tails,
malformed/truncated headers and packets, repeats and segment resets. PWM,
EOF/error/stop/FIFO/timer state and producer/stack measurements remain exact.
The canonical `halt` step binds the final gain/Rice/cosine composition.
An additional 4 B CRT exit-alias experiment was measured but not enabled;
the ordinary startup exit destination remains unchanged.

`lpc-ring-proof.json` binds the retained `avr5_circular_lpc.cpp` regression:
41,280 chained transitions across all 20 history phases, saturation cases
and guard bytes, with 6057 active IRQs and zero output/r1 errors. The receipt
records the exact compiler/observer commands. The general arithmetic default
remains two taps; the player builder explicitly selects one only for ASM,
universal v9, hardware-MUL targets with the optimized ROM-selected gain.

## Rebuilt WebUI images

`web-rebuild.json` records all 18 rebuilt assets against the exact task-start
publication, including a replay of each old ELF after proving it matches the
published HEX. All 345,470 PWM samples match C, the existing public WAV and
their predecessor, with zero IRQ underruns. All 26 sound/stream assets stay
byte-identical. Every image has a separately rebuilt, byte-exact ASM binary
with no floating-point runtime symbols.

| Image | Program excluding audio | Full image | Change from publication |
| --- | ---: | ---: | ---: |
| Nano single stream | 3056..3057 B | 3506..4938 B | −60 B each |
| Nano dialogue | 3339 B | 8888 B | −58 B |
| Tiny three-rate release | 3665..3666 B | 4058..5546 B | +26 B each |

Tiny's release flags differ from the generic 22-case recipe. All nine full
Tiny images fit the 6012-byte standard bootloader region and the 6656-byte
project cap. The table's Tiny growth is the explicit new rate feature cost,
not growth of sound data. The ordinary 8 kHz-only compatibility build remains
smaller than task start.

Matched full producer plus IRQ means improve by 0.275..0.422 cycles/sample on
Nano, 8.000..8.304 on Tiny and 1.319 on the dialogue; peaks never increase.
The raw Nano decoding region grows about 9.6 cycles while the faster output
gain offsets it. Queue minima and peak stack stay unchanged in the released
images. `irq-vectors.json` explains the linked Nano 35/36-cycle vector cost;
all 132 measured vector/body combinations match their predecessor costs.

The WebUI cache keys and generated speech inventory were refreshed. The full
1966-test web suite passed, followed by the added release-receipt assertion
and its two existing matrix/contract checks. The 13 host reference tests,
seven source-rate frontend tests and generated inventory check also passed.

`arithmetic-audit.json` binds the final 12 MCU/backend/gain selections, the
retained ring/gain tests, and native ATmega328 controls at all three rates.
Those control binaries equal the matching ATmega328P binaries. Explicit C
remains available with either hardware memory layout; no-gain builds keep
the general two-tap default. The complete C fallback control also produces
exact PWM and preserves the native interrupt context.
