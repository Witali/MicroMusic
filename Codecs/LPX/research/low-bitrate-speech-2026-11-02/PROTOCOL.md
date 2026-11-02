# Bounded 2/3 kbit/s speech search

Frozen before corpus evaluation on 2026-11-02. The public 19200-sample example
is a tuning stimulus and is excluded from the confirming corpus summary.

The complete-file caps are `floor(samples * kbps / 64)` bytes: all headers,
spectra, parameters, innovations, terminal packets and padding count. Sparse80
uses existing explicit version 8/mode 15 syntax at 2 kbit/s; version 5/P4 is used
at 3 kbit/s. Neither changes rate, pitch, output duration or integer synthesis.
No 1.5 kbit/s profile is part of this experiment.

The finite host grid is preQ14 `{13926,11469,8192}` crossed with LPC bandwidth
`{.97, .94}`. Every pair proposes ordinary uniform spectral holds and an
energy-weighted adaptive contiguous LSF segmentation. Neighboring segments
merge by smallest LSF proxy loss per real saved byte until the serialized
budget fits. This proxy only proposes spectra; whole exact decoded outputs
decide final admission. There is no trained or clip-specific codebook.

The unchanged uniform 13926/.97 control is saved first. Its excitation tests
one open-loop residual lag, five neighboring scales plus 0/1 and gains 0/6/10/14.
New proposals also test the reliable source-period integer and its neighbors,
two separated residual lag alternatives, every legal gain 0..14 in steps of 2,
and a dominating hard-clipping penalty while fitting innovations. Every
position/sign is tested through exact closed-loop integer synthesis: 16*2 per
20 samples for P4, 64*2 per 80 samples for sparse80. The clipping penalty is never
used to alter reported audio or metrics.

Keep every complete intermediate stream before continuing. Retained input
seeds are redecoded and rescored against the exact target, never trusted from
old metrics. Select minimum mean PCM/PWM voice-plus-noise score only after
nonincreasing full PCM/PWM SSE, nondecreasing STOI and source-bound period
tolerance counts, and nonincreasing hard-clipped sample count relative to the
control. The control always remains eligible. These objective proxies are not
a calibrated listening score or evidence of global optimality.

Corpus selection uses all 27 existing four-second PCM16/8 kHz references,
keeping their complete 32000 samples. They are the established corpus described
in `research/q0-lowrate-2026-10-25/corpus.json`: 16 clean speech windows,
two quiet, two noise15, three acoustic music and four synthetic controls.
The first reported subset is original corpus ordinals 0/8/16/19 for tuning
and 4/12/17/18 for evaluation; these correspond to old P4 record ordinals
20/28/36/39 and 24/32/37/38 in the v1 source binding. Each subset group has
two clean speech windows, one quiet and one noise15 window. Remaining clean
speech retains the established voice split: ordinals 0..3 and 8..11 tune;
4..7 and 12..15 evaluate. Music/synthetic cases are negative controls, with
STOI disabled. These are 27 clips from an established corpus, not 27 newly
independent speakers. No parameter tuning follows evaluation. One declared
auto-quiet gain precedes all compared candidates; its value and source
bindings remain private.

For each clip/rate report actual complete bytes, full PCM/PWM SER/STOI, fixed
source-period tolerance counts, clipping, finite trial counts and CPU/wall
cost. Common native C decoding of the exact v5 reference expansion must agree
sample-for-sample with the independent model for every contender. Recheck
selected and control through v5-only native C. Decoder source and format
defaults stay unchanged. Firmware timing, full Flash, SRAM and active-IRQ
underruns are a separate admission performed on actual linked players.

Originals, generated private media, identifiers, hashes, logs and absolute
paths stay in ignored build storage. Publish only code and anonymous numeric
evidence. The public example can be exported separately after the applicable
publication approval. A failed fit or unchanged output is retained as such.
