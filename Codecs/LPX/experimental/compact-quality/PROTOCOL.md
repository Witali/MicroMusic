# P3 canonical-spectrum scoring study

Prospective plan, 2026-11-26, before pilot outcomes. The current UI's compact
profile is accuracy P3, using P4 wire symbols. It is distinct from the native
strict 3 kbit/s preset and the earlier 2 kbit/s sparse80 research. The current
task provisionally studies P3 at 8 kHz; user clarification was requested before
measurements. Any change of scope must be recorded before dependent runs.

## Concrete mechanism

`LpxLpcRefine.cpp::localCoefficients` currently constructs an artificial local
stream without the P3 accuracy policy. Whole-output packing/rendering instead
canonicalize P3 rank residuals to the even grid and apply the temporal dead zone.
The local shortlist can therefore score an untransmitted predictor. Final
whole-output validation remains protective; this is a proposal-ranking defect,
not evidence of an invalid decoded stream.

Correct the local predictor construction using the proposed stream's actual
complete canonical spectrum sequence and true preceding transmitted spectrum,
then slice/interpolate the already-canonical data. Merely setting accuracy3 on
the shortened artificial stream can lose earlier dead-zone history. Preserve
the existing trial ceilings, loss, proposal ordering and all non-P3 behavior.
No new noise criterion, pulse beam, format or decoder operation is introduced.

Before benchmarking, independently reproduce the old local/full trace mismatch
and verify the correction across canonical no-ops, long dead-zone chains,
run boundaries, start/reset, partial tails and real assembled continuation.
Cover 8/12/16 kHz and unchanged P4/P6/P8 controls. Tests must not treat isolated
continuation verification as proof of the assembled carried-state output.

## Paired comparison

- Baseline task revision: `e467dc9e`, with active LPX inputs from `644e19d0`.
  Compile original and corrected versions with the same production composition,
  compiler/options, definitions and scalar backend. Pin all source/binary hashes.
- Fresh `encodeAccuracy(reference,3,8000,calls=4,target)` for each version and
  each target. Four complete public clips: chego, otvechaesh, vinni, bread.
  Prepared 8 kHz PCM must match the retained source hashes; no candidate-fitted
  gain, delay, normalization or source-specific preprocessing.
- Pilot: chego in PCM and PWM. Matrix: all four clips in both targets, eight
  distinct cases. The pilot repeats two matrix cases; do not count it as extra
  independent material. Freeze implementation and criteria before the pilot;
  no threshold or search tuning from its outcomes.
- Report **raw corrected encoding** against original encoding. Also report a
  separately labelled **protected experimental selection** of baseline versus
  corrected output; do not silently replace a raw regression by a claimed win.

Let B0 be the original complete V9 file's bytes and C its nominal P3 policy
allocation (`max(original canonical control bytes, header + frame budget)`).
Report both. A corrected file spending C−B0 spare bytes is still larger than B0;
it cannot be called an improvement at the same actual bitrate. Protected
selection requires actual serialized size no greater than B0, not merely C.

The additional protected selection requires native/model identity, legal
syntax, stable predictor, safe synthesis level/spectrum, active-path SSE/STOI
non-regression, old-noise non-regression, existing FullBand/pitch/clipping
protection and complete quality selection. These explicit experimental floors
are stricter than the production selector's individual SSE/noise guarantees;
the production selector uses a combined objective with its existing guards.
PCM admission uses PCM; PWM uses both active PCM/PWM paths. PWM diagnostics in
PCM cases are inactive post-hoc observations. The original whole output always
remains available.

Retain bytes/hashes and actual decoded PCM for original, raw corrected and
protected outputs. Record original/corrected host time, actual allocation and
packing costs, canonical spectral holds/updates, pulse/parameter/extra changes,
native identity, SSE, STOI, full-band/temporal metrics, old noise and pitch
diagnostics. Keep byte-identical outputs and rejected proposals visible.

## Limits and next steps

This first comparison isolates predictor fidelity. P3-aware neighbor spacing,
dead-zone escape proposals or spectral refresh relocation would be distinct
operators with their own prospective plan and baseline; they must not be mixed
into a result attributed only to corrected local scoring.

Numerical improvements are not calibrated listening preference. Preserve
levels for any WAV export, use unseen material before a broad speech-quality
claim, and report small or rejected gains candidly. Source audio, generated
streams/models and binaries remain in ignored build storage; retain code and
anonymous numerical reports only.

The MCU decoder is unchanged. This adds host work, not MCU arithmetic or tables.
Changed data can still alter data-dependent timing; a new real-time/interrupt/
hardware support claim requires complete AVR playback measurements. No such
claim follows from host/native equivalence or unchanged file size alone.
