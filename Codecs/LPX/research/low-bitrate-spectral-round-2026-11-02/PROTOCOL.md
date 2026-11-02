# Saved-spectrum refinement round

Prepared on 2026-11-02 before this round's outcomes. This is a research-only
operator, separate from the frozen active 2/3 kbit/s encoder and from the pitch
proposal experiment. Do not change active dependencies or launch another CPU
job while the current corpus workers are running. The root coordinator supplies
the shared full-output admission harness and round order.

## Frozen inputs and boundaries

- Use each existing saved selected stream as the immutable incumbent. Reuse
  its complete declared PCM16 target after the already selected whole-input
  gain. This module does not amplify, normalize, trim or resample input.
- Keep rate, sample count, pre-emphasis, zero brightness, format and decoder
  arithmetic unchanged. The 2 kbit/s container is sparse80 version 8 / mode 15;
  the 3 kbit/s container is plain v5/P4 without optional extra pulses.
- The exact complete byte cap remains `floor(samples * kbps / 64)`. Count the
  header, exact bounded-Rice spectra, fixed excitation fields, all stored
  packets and final bit padding. Do not trade a larger file for quality here.
- Scope is the current 19,200-sample public tuning example and 32,000-sample
  corpus records, all aligned to 320 samples. Nonaligned-tail fitting is a
  separate issue; do not claim this round fixes or evaluates it.
- No change is made to the decoder, its tables, the active host search, or the
  web UI. Saved incumbent bytes remain eligible even if every refit loses.

## Proposal generation

Read the incumbent's scalar LSF vectors and identify contiguous equal-vector
runs. Consider two kinds of changes, each anchored to the same saved stream:

1. Add -1 or +1 to one scalar across an entire existing run, retaining legal
   strict vector ordering and the existing five-/six-bit range.
2. Move an existing boundary by -1 or +1 complete 320-sample frame, assigning
   that frame the neighboring run's vector. Keep both original runs nonempty.

There is no cumulative coordinate descent within this round. A proposal that
becomes equal to its neighbor may naturally save Rice bits; otherwise the
operation preserves the existing holds rather than introducing arbitrary new
spectral update points.

Rank only to choose which full refits to attempt. Analyze the unchanged target
with the incumbent pre-emphasis and fixed LPC bandwidth 0.97; quantize with the
existing profile-specific scalar quantizer. Weight each 320-sample desired LSF
vector by `1 + RMS(target frame)`, matching the established spectral proposal
proxy. Rank by the change in full weighted LSF squared distance, then exact
complete layout bytes, start frame, scalar/boundary index and signed direction.
This proxy is not an audio acceptance criterion or a perceptual score.

Discard illegal, unchanged, duplicate-spectrum or over-cap proposals. Reserve
two slots for each family, then fill unused slots from the other family's
remaining ranked proposals. At most four distinct changed spectra receive a
full excitation refit. Fix proposal IDs/order before any reconstructed quality
is observed: coordinate proposals first, boundary proposals second, each in its
own ranked order. Keep this bound and ranking unchanged during evaluation.

## Full refits and admission

For every shortlisted spectrum, rebuild the complete coefficient trajectory
and rerun the existing expanded-lag, hard-clip-guard excitation search from
zero state over the entire target. The shared harness supplies the same
source-period lag array used for all comparable refits. Do not add or force a
new pitch proposal in this spectral round. Header filters remain fixed.

Serialize the complete result and check the real byte cap. Record every refit
attempt and all its parameter/pulse/commit replay counts, including duplicate
final streams. De-duplicating native decoding must not erase attempted work.
The module returns the full search PCM as an expected reconstruction for the
independent harness; it does not admit or select a result itself.

The root harness retains the exact saved incumbent, independently decodes each
whole contender through the model and common/v5-only native reference bridge,
and checks PCM/PWM equality. Re-evaluate complete-output PCM/PWM SSE and STOI,
source-bound period diagnostics, clipping and the frozen joint voice/noise
score. Use the same admission policy as the other registered rounds and state
its reference explicitly. Do not substitute local SSE, LSF proxy improvement,
or a changed pitch mask for that full-output decision. The incumbent remains
eligible; any tradeoff must be reported, not silently called an improvement.

Compare both rates on the existing voice-separated tuning/evaluation split,
with quiet/noisy derivatives kept on the same side as their parent source.
Keep music/synthetic cases as negative controls with STOI disabled. The public
example is a tuning stimulus and is excluded from confirming corpus summaries.
Freeze this operator before observing evaluation outcomes. Do not retune this
round using those outcomes or call the clips independent new speakers.

For useful changed streams, complete target-firmware Flash, SRAM/stack,
interrupt timing and underrun admission remains a separate required step.
Numerical proxies and a finite search do not establish subjective quality or
a global optimum. Preserve private media, identifiers, paths and source hashes
only under ignored build storage. Publish anonymous aggregate evidence only.

## Reused code and limits

The active `refine_speech_lpc.py` already offers local scalar neighbors with
exact 480-sample interpolation patches and local excitation adaptation for
v5/P4/P6. This round does not copy its local-acceptance loop: at these tight
caps, preserving whole spectral holds/boundaries and refitting from zero is a
small complementary experiment. It uses the existing host quantizer, exact
Rice byte accountant, coefficient trajectory and excitation search. No new
decoder backend or trained codebook is introduced.

Status: protocol and module prepared; no refit jobs or quality outcomes yet.
