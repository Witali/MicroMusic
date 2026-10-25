# Frozen comparison protocol, 2026-10-25

Base: `f1225f13`, current LPX4 Q0 decoder and optional compact metadata.
Purpose: close the missing Opus/Vorbis/Speex comparison, explicitly measuring
signal-to-error ratio and maximum sample deviation as requested by the user.
No subjective-quality or MOS claim follows from waveform metrics.

## Corpus

- Sixteen new four-second speech windows: the eight previously attributed
  RU/EN speakers, starting two seconds after each earlier LPX window. These
  are new regions, not new speakers. Verify original hashes from the retained
  Speex corpus before loading. Preserve attribution and source URLs.
- Two quiet (-24 dB) and two seeded white-noise (15 dB SNR) versions.
- Three licensed acoustic-music excerpts if accessible, plus deterministic
  harmonic music, chirp, transients and silence. Record source/recipe and
  hashes; never use or store MIDI. Downloaded audio stays in ignored build.
- All codec inputs are the same mono PCM16 at 8 kHz. This tests narrowband
  coding; it does not rank fullband music reproduction.

## Rate and encoder policy

- Audio-packet budgets corresponding to 8, 12, 16 and 24 kbit/s over the
  reference duration. Count complete file size, codec setup/comments and
  container overhead separately. Required Vorbis setup is not free storage.
- LPX: legacy/regularized/flat analysis and frozen lambda grid; native Q0
  validation, zero packing, scale aliases, exact existing-mode repacking
  and opt-in compact metadata. Keep all valid candidates and select within
  each actual byte cap. Record a genuine no-fit result at infeasible rates.
  The grid is 0/.001/.003/.01/.03/.1/1/10. Exact excitation search is a final
  pass over the selected candidate. No-fit describes this bounded encoder
  search, not a mathematical impossibility of the LPX format at that rate.
- Bounded unified search uses one round, LSF80/beam128/header40/global8,
  128 global states, beam4. Keep original candidates and record the budget.
- Opus: libopus complexity10, VBR, 20-ms frames; test audio and voip modes.
  Vorbis: libvorbis bitrate control. Speex: libspeex complexity10, ABR;
  additionally retain native CBR mode points to expose bitrate granularity.
- Fit standard-codec audio-packet bytes to the same ceiling; preserve the
  actual achieved rate and any underspend. Approximate matches are not
  called equal. Separately compare under complete-container LPX byte caps
  on the high-rate shortlist.
- Standard encoders receive an 80-ms zero tail to flush delay. It is counted
  in their bytes. No source gain normalization or fitted gain is allowed.

## Metrics and validation

- Full-reference SER = 10 log10(sum(x*x)/sum((x-y)*(x-y))), RMSE, maximum
  absolute error, its signed value, position/time and percentage of peak
  full scale (32768). Subtract in widened integers to avoid int16 overflow.
- Report unaligned output and separately a bounded 0..60-ms cross-correlation
  delay correction for standard codecs. LPX has no transport/algorithmic
  offset. Compare the same complete reference duration; fail short output.
- STOI is for speech only. Silence/perfect reconstruction uses explicit
  null/infinite-status metadata rather than fabricated finite SER values.
- Compare PCM16 before PWM and a common fixed 8-bit PWM conversion. Confirm
  this conversion against LPX's native PWM output; include the quantized
  reference floor. No analog/hardware measurements are implied.
- Confirm selected LPX PCM with its independent model and portable decoder;
  profile selected LPX streams as full AVR ELF with active audio IRQ. Report
  AVR-admitted and non-admitted candidates separately. Standards run on the
  host; do not infer their AVR timing from host runtime.
- Test metric extrema, delay handling, Ogg packet accounting and byte caps.
  Retain numeric reports, commands, source/tool hashes and failure reasons;
  media and build artifacts stay ignored. Keep focused commits per change.
- Prepare an anonymous listening shortlist and its attribution/key. Human
  listening scores remain unavailable until actually collected.

## Status

- [x] Protocol recorded before measuring the new corpus.
- [x] Shared metric/container tests, including cache input/binary invalidation.
- [x] Corpus preparation and source verification: 27 four-second cases.
- [ ] Rate/quality matrix and actual-byte comparison.
- [ ] LPX native/PWM/AVR validation.
- [ ] Retained results, limits and listening shortlist.
