# Z80 study: transferable ideas for current LPX

This is a technical review requested by the user of the available Z80 codec
conversation, which describes LP20 versions 16–19. Its earlier numerical
claims and linked sandbox source archives are not independently reproduced in
this repository. No private conversation transcript, source audio, chat
identifier or attachment is retained here. Only general engineering findings
and comparisons with the current local implementation follow.

## Favor encoder work that preserves the decoder and stream

The strongest transferable principle is to optimize excitation with the actual
integer synthesis and PWM path inside the encoder's scoring loop. A better
choice of existing symbols can improve quality at the same byte count without
adding AVR work. If that improves the quality/size frontier, lower byte budgets
can then be tested against the original quality floor.

This principle is already substantially implemented in current LPX:

- [LpxQuality.cpp](../../01_ACTIVE_Q0_CODEC/host/LpxQuality.cpp) scores both PCM
  and PWM, voiced periodicity, spectral shape and harmonic/off-harmonic energy.
- [LpxFullBand.cpp](../../01_ACTIVE_Q0_CODEC/host/LpxFullBand.cpp) measures full
  spectral and temporal errors; its admission check guards supported-band error
  and retention on both output paths.
- [LpxPitchGuard.cpp](../../01_ACTIVE_Q0_CODEC/host/LpxPitchGuard.cpp) rejects new
  octave errors using source and incumbent periods.
- [LpxPulseLookahead.cpp](../../01_ACTIVE_Q0_CODEC/host/LpxPulseLookahead.cpp)
  searches pairs of existing pulses with a 160-sample horizon and whole-output
  admission. [LpxRefinement.cpp](../../01_ACTIVE_Q0_CODEC/host/LpxRefinement.cpp)
  already searches pitch, gain and scale with pulse refitting, while
  [LpxLpcRefine.cpp](../../01_ACTIVE_Q0_CODEC/host/LpxLpcRefine.cpp) proposes
  quantized LSF runs with local pulse adaptation.

Consequently, adding a second global harmonic/noise metric or a pitch estimator
is not a new transfer. The specific missing experiment is **voiced-aware local
proposal ranking**. Pulse-lookahead shortlisting currently uses local waveform
SSE, then applies whole-output quality gates. It may never propose a pulse pair
with a better audible-noise pattern if that pair ranks poorly by local SSE.

A bounded future experiment could retain the existing SSE finalists and add a
small shortlist using source-frozen F0/voicing confidence and excess
interharmonic energy on both PCM and PWM. Reuse existing analysis/masks rather
than duplicate them. Preserve the incumbent, exact V9 byte budget, and all
whole-output checks. Test held-out recordings and listening examples before
claiming a better quality/size tradeoff. This experiment is **not implemented
or measured here**.

## Distinguish codebook hypotheses from an admitted AVR codec

The Z80 study also explores excitation dictionaries selected from decoder
history context, scaled shapes, factored dictionaries and a harmonic generator.
These are design candidates, not drop-in changes to current LPX. Current LPX
already reuses periodic excitation through its pitch-history predictor.

A context-dependent dictionary can use information available at both ends
without transmitting a separate context index. It still requires identical
decoder arithmetic/state, learned vectors, new symbol interpretation and
validation on unseen recordings. A codebook learned for one recording does
not establish a universal codec improvement. The table/code/header cost must
be counted alongside compressed audio, especially in ATtiny88's 8 KiB Flash.
The Z80 study's failed simple vector factorization is a reason to gate this
direction early, rather than assume fewer mathematical entries mean a smaller
working implementation.

## Keep compression, program layout and CPU claims separate

Packing excitation vectors into unused ROM-table regions reduces a specific
decoder image; it does not reduce audio stream bits. Table-pointer scheduling
and a Z80 register allocation are ISA-specific. Their AVR equivalents require
actual target measurements and exact rounding/state preservation.

Likewise, LZMA2 compression of a computer-side archive does not demonstrate a
streaming AVR compression gain. Count the directly playable stream, tables,
program, working memory and full decode cost. Do not compare SNR/STOI across
different source recordings, sample rates, LPC orders or source-trained tables
as if they were a common benchmark.

The current decision therefore remains: retain the best existing LPX baseline,
stop the unsuccessful LSF grouping branch, and prefer bounded encoder-only
experiments before another format or AVR decoder rewrite.
