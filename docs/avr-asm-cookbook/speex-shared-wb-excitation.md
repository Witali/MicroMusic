# Share geometry-parametrized AVR kernels through tiny ABI entries

Target: ATmega328P / AVR5 with hardware MUL, GNU ABI, AVR GCC 7.3.0,
existing Os/O2/O3 plus LTO, mcall-prologues and mrelax. Measured benefit:
program Flash. The exact C arithmetic fallback and public four-argument ABI
remain unchanged. The final combined project admission is separate from this
bounded clone experiment.

Four HB1 excitation/fold functions formerly duplicated the same arithmetic:
NB3: 4x10 at exc_10_32_table; NB4: 5x8 at exc_8_128_table; NB2: 4x10 at
exc_10_16_table; NB8: 2x20 at exc_20_32_table. Preserve the original two
quantization stages, modulo-product bits and odd-sample negation. Share the
whole loop instead of making a function call for every sample.

Each original symbol becomes an 8-byte tail entry: load table address into X,
load packed geometry into ZL, and jump to one 330-byte common body. X and Z are
caller-clobbered scratch registers and contain no ordinary C arguments in
this existing ABI. The body saves all required registers before copying the
normal output/indices/scale/gain arguments. Gain originally in r14:r15 is
copied into its established working registers before that pair retains the
table address. Two extra callee-saved bytes are pushed/restored; no extra call
or return address is added.

Pack geometry as `(width << 3) | vectors` in r12. The three low bits hold a remaining
vector count 1..5; shifting a copy right three recovers width 8, 10 or 20. DEC
reduces the low count until zero without borrowing into width bits. The last
count is tested using a caller-clobbered high register and `ANDI 7`. All widths
are even and every vectors*width equals 40, so resetting sample parity at a
row boundary preserves global output parity. Rounding bias remains a separate
constant 4 in r13 and must never be derived from the vector count.

Keep each entry in its own `.text.<symbol>` section and put the common body in a
separate section. Otherwise linker garbage collection can keep disabled
entry thunks and their large codebook tables alive. When only the ordinary
NB3 geometry is enabled (no NB4/NB2/NB8), retain the original inline kernel:
sharing one body would add overhead without removing duplication.

Measured complete all-feature WB9.8 decoder: 25,916 -> 25,024 B (-892 B). The
four original kernel bodies total 1252 B; their shared replacement totals
362 B, while changed layout/relaxation contributes the remaining 2 B in the
bare image. Production-IRQ images save 890 B: 26,352 -> 25,462 B. Two-profile bare
images save 282 B (NB4 pair) or 280 B (NB2/NB8 pair). Minimal WB9.8 and NB1-only
images are byte-identical to their matched controls. Static SRAM is unchanged.

Own instruction-cycle overhead per 40-sample call is exactly 30 for NB3/NB2,
33 for NB4 and 21 for NB8 in the tested domain, excluding interrupt work.
A frame uses four calls, costing 120, 132 or 84 extra cycles, at most 0.04125%
of a 320,000-cycle frame period. This is the cost of moving geometry control,
not a per-sample subroutine call. The common arithmetic instruction sequence
is retained.

Validation in the frozen before/after clones:

- 37,440 code/scale/gain cases per version check both isolated C and ASM against
 independent BigInt equations, all codebook rows and every one of 40 LPM
 addresses. Full signed32 gain edges and scale 0..121,000,000 boundaries are
 included. All 37,440 ASM returns preserve callee-saved registers and zero r1.
 Read-only indices/parameters and output guards pass with Timer2 IRQs active.
- 320 ready-RAM production-IRQ frames per version cover WB5.75/WB7.75 at +3%
 foreground work and WB9.8/WB12.8 at +8%. Every signed16/PWM sample is exact;
 no underruns. Minimum queues 28/21/8/9, whole-program peak stack 210 B and
 free SRAM 408/403/398/391 B are unchanged. These are bounded stream prefixes,
 not the full release corpus or an external-storage timing measurement.
- The final GC-safe bare, unit and four IRQ binaries are byte-identical to
 their already observed shared-code counterparts. Six feature combinations
 check actual garbage collection and singleton binary identity.

The measured baseline already included the root compact-divider work, before
later pitch-root and shared-LSP integration. Preserve these isolated deltas
separately from final combined measurements. ISA simulation is not a physical
board or analog-output measurement. No full C decoder was executed.

Production kernel: `src/wb_fold.S`. The equivalent existing C routines remain
in src/wb_fold.c and are selected by the existing supported-architecture plus
explicit ASM-enable contract. Source algorithm/table BSD provenance remains
Xiph Speex 1.2.1; geometry packing and tail-entry factoring are original work.

Reproduce from the worktree root:

python Codecs/Speex/AVR/tests/shared-fold/reproduce.py --avr-gcc <avr-gcc> --before-wb-fold <pinned-before-wb_fold.S> --candidate-wb-fold Codecs/Speex/AVR/src/wb_fold.S --node <node> --screen-data <four-profile-streams-and-oracles> --feature-matrix

The driver snapshots current other sources, overlays only the specified
before/after fold file, builds ASM decoder/IRQ images and isolated C/ASM
scalar probes, then invokes existing production-IRQ observation. It never
executes a complete C decoder. Probe source: unit.c and verify_unit.mjs.
The [receipt](../../Codecs/Speex/AVR/reports/wb-shared-fold-size.json) binds the frozen experiment;
reproducing against later combined sources produces new images and needs
its own receipt. A future implementation should retain compile-time geometry
guards (even width, product 40, count <= 7 and width <= 31).
