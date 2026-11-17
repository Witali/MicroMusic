# Compact universal LPX player work

Task baseline: `ead0bdcb0b627532afbf2d7b52fce7f015cf6dbc`.
The target is at most 3072 program bytes for the single-stream Nano player,
excluding audio. Also reduce the shared ATtiny88 firmware, preserve exact
8 kHz PWM and compressed payloads, and retain explicitly selectable C
arithmetic. Additional dialogue infrastructure is outside the 3072-byte cap.

`steps.json` orders focused source transitions. Each retained measurement
pairs 22 actual interrupt-active playbacks per CPU with its predecessor.
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
