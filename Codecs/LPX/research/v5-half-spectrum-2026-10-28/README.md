# V5: omit the second-half LSF copy, 2026-10-28

The second 160-sample core frame of a 320-sample v5 packet transmits no new
LSF vector. It uses the cached LPC endpoint; the following first half refreshes
`prev_` from `cur_` before any temporal-delta decoding. Move the ten-word copy
inside the existing first-half branch in compact-only builds. Common-format
builds retain their original copy location. No extra state, arithmetic, class
layout, C/ASM backend or hardware-access change is introduced.

Baseline is `a921e3c7`, the independently measured exact cosine-grid change.
ATmega328P/enhanced AVR5 with MUL, GNU ABI, AVR-GCC 7.3.0, 16 MHz/8 kHz,
queue 512/prefill 384, segments 2, explicit ASM, unroll 1/tuning 0,
`-Os -flto -mcall-prologues -mrelax`. Original vendor headers remain in use.

Six complete normal-IRQ firmware pairs contain current-selected real audio:
64000 samples in one segment, 64060 samples in two segments including a short
partial tail, and 281632 samples in five segments, each at profiles 4/6.
The copy change saves another 14 B Flash in single-segment images and 152 B
in the two/five-segment images. This context-dependent difference includes
LTO/inlining/layout effects; it is not a universal cost of the removed loop.
Static SRAM stays 1085/1086 B. Available decode wall-cycle totals fall
0.156–0.169% (single) or 2.018–2.284% (chains). Observed after-ready stack
margin improves by four/six bytes, to 890/887 B. These are observed margins,
not a worst-case or startup-stack proof.

All six final normal-IRQ images plus four +100 IRQ-cycle controls produce
exact complete model PWM with zero underruns/errors. Decode timing statistics
cover at most the first 64000 samples, while the full longer PWM, played/
produced counts, timer ticks and underruns remain checked.

Seven focused test groups pass after this change. The new matrix compares
360 compact-only inputs with the unchanged common reference across segments
1/2/4, bandwidth expansion off/Q14 16000, both speech profiles, ten partial
lengths, and dynamic/repeated/mixed spectra. It builds 12 decoder libraries
and six snapshot executables, with 36 snapshot stream runs. The six existing
compact-only parser, malformed-input, tail, reset/copy and explicit reference
state-path tests also pass. Broader combined-source checks belong to the parent
integration, rather than being inferred from this bounded experiment.

[Exact counts, flags, hashes and measurements](measurements.json). These are
simulator results for the measured images/settings; no physical-board result
or universal speedup is claimed. This is original project work.
