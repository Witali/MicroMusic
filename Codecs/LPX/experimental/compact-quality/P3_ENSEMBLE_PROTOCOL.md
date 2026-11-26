# Existing fine-grid encoder at the finished P3 byte ceiling

Prospective distinct arm, 2026-11-26, after the two isolated P3 arms completed
with unchanged final files. No ensemble audio case has run. This reuses an
existing encoder with a different candidate policy; it is not a new algorithm,
wire format, LSF-only refinement or gain attributed to the canonical-helper fix.

## Exact operation

Start from each SAME stored original finished P3 baseline, source and actual
complete V9 byte ceiling B0. Verify the baseline's pinned bytes/PCM/model and
the unchanged source. Copy its physical fields into two host streams and set
both host accuracy policies to4. Before search, prove these host-policy copies
have identical complete bytes, native PCM and all physical fields to the P3
baseline. Host accuracy is not a transmitted V9 field.

Call the existing `encodeThreeK(reference,B0,report,.97,&incumbentFine,
&prefixFine,target)` exactly once. These complete files are reset/noncontinuing
8 kHz P4-wire streams. Both host copies must avoid accuracy3; otherwise seed
generation would impose P3's even-grid/temporal-hold policy again. Preserve
target, sample rate/count, history, declared level and all baseline metadata
before that existing search. No output gain fitting or source normalization.

This function generates fresh source-derived spectra and excitation: up to
three existing pre-emphasis seeds, byte-aware spectral holding/merging and
bounded complete excitation refits. The incumbent is a protected output floor,
not the center of a local odd-bin search. The function may change pre-emphasis,
spectral cadence, pitch/scale and pulses. It must stay within actual B0; it is
not given the nominal P3 allocation C or a newly calculated3k allowance.

Do not add bandwidth sweeps, header/quality/joint passes, new neighbors,
decoder fields, extra corrections or empirical loss weights. Keep all original
source/receiver code and both previous experiments unchanged. A search error,
unsafe or malformed result retains the original baseline and is reported as
an error/fallback, not an improvement or a proof that every fine-grid search
fails. Pin the new adapter, source list/options and binary before a pilot.

## Different policy requires a correct checker

Do NOT pass the fine result through phase1's `checked()` helper: it forces
accuracy3 and would re-quantize legal odd bins. Use a separate checker with
accuracy4 and verify actual native/model/packed identity, ordered legal LSFs,
full EOF and unchanged declared target geometry. The original baseline remains
separately checked as P3. Odd raw rank residuals are allowed in the candidate's
ordinary P4 wire syntax; record their count and effective transmitted changes.

Before speech, independently test that host-policy relabeling leaves physical
baseline output unchanged, that odd-bin results survive pack/native replay,
and that complete strict protection rejects wrong policy, malformed geometry,
over-budget or regressing candidates. Retain the original incumbent on search
errors. No decoder or public encoder API change is required for the experiment.

## Comparison and limitations

Pilot: chego PCM and PWM. Then the fixed four-source/two-target matrix from the
earlier P3 phases. No source/criterion tuning after pilot outcomes. Report raw
ensemble and independently protected output versus the SAME original baseline.
Apply the earlier explicitly stricter complete-output floors and B0. Report
policy C separately; any actual growth is still growth even when C permits it.
The previous byte-identical corrected/grid-arm outputs are not additional
independent baselines or quality wins.

Report actual odd-bin fields, spectral update/hold count, spectral and parameter
bits, pulse/parameter/pre changes, all quality metrics and search/error/counter
data. No result can be attributed solely to finer coefficients when other
fields also change. Record actual encoding time; prior-run original timing is
only a reference, not a controlled concurrent-load speed comparison.

The same decoder syntax/arithmetic is used, but changed update cadence, packet
types, gains and saturation can affect decoding work. Report those changes;
do not claim equal AVR cycles from equal bytes. Any new real-time/interrupt/
hardware-support claim needs complete target measurements separately. Numerical
proxy gains require level-preserved listening and unseen sources before a broad
audible-quality claim. All generated media stays in ignored build storage.
