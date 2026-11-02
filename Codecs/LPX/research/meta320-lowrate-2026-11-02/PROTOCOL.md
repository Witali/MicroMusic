# Explicit metadata320 prototype at 3 kbit/s

Registered before bread pilot outcomes on 2026-11-02. This isolated prototype
does not change the original worktree's pinned host-round campaign or ledger.
It investigates the user's new allowance for about 10–20% additional decoder
cost only if sound improves clearly. CPU and Flash are measured separately;
compressed bit counts do not predict the cost of more frequent LPC conversion.

## Exact syntax and reference

Use a new explicit L4HY version 9 / mode 3, 8 kHz and 320-sample spectrum and
metadata frames. Keep the existing 22-byte header, filter limits and payload
length. Each complete stored packet contains the existing ordered five-bit
gap/delta/repeat LSF code, one 15-bit scale/lag/gain tuple, and sixteen existing
P4 position/sign pulses (five bits each). Fixed fields cost 95 bits per packet,
or 2375 bit/s, excluding spectra, header and padding. Ordinary v5/P4 spends
110 bits per packet, or 2750 bit/s. The freed 375 bit/s can carry spectra; its
sound and target CPU benefit remain unmeasured until this experiment runs.

The exact host bridge repeats the tuple twice into ordinary v5/P4, preserving
spectra, all pulses, sample count and filters. Compare native common/v5-only
PCM/PWM with the independent model. The expanded file's larger size is never
advertised as the new format's size. The direct target parser is opt-in and
must match this bridge, reject malformed tails and preserve the ordinary
format defaults. Firmware changes and timing admission belong to their own
review; the host prototype does not edit C++ source or build configuration.

## Protected control and host search

Use the latest best known complete ordinary v5/P4 stream as the protected
incumbent, starting with the bread beam result and replacing it with the
completed original campaign's result if that is better. Never compare the new
format with the earlier weak uniform spectral control. Preserve original
source duration, 8 kHz playback and the declared once-per-input quiet gain.
Quiet amplification defaults to the user's accepted auto-quiet policy before
PCM16 quantization. The public bread stimulus uses its unchanged original
level; it is tuning, not a heldout proof.

The frozen common analysis grid is preQ14 13926/11469/8192, LPC bandwidth
0.97/0.94 and the established 256-sample LPC analysis window. At each of the
six pairs retain all fitting complete uniform spectral cadences 1/2/4/8 and
one adaptive contiguous-segment plan at the real complete 3 kbit/s byte cap.
The lower-density plans remain separate complete candidates for target CPU
profiling even if the densest proposal has a better quality proxy. Also fit
the protected incumbent's unchanged spectra once at its original header.
There are at most 31 new complete candidates, before deduplicating identical
header/spectrum proposals. A duplicate proposal avoids fitting; every actual
fit and every completed output attempt is counted, including duplicate final
bytes. Spectral proposals do not decide admission.

Adaptive segmentation uses the established frame energy weight and legal
LSF means. Merge adjacent segments by smallest weighted LSF proxy loss per
positive saved spectrum bit, with exact local gap/delta/repeat transition
costs and final complete serialization. This bit-level proposal search can
cross byte-padding boundaries, but the final cap always includes the header,
all 95-bit packets, exact spectra and padding. No cap padding is added.

For each proposed spectrum fit one tuple over each complete 320-sample
metadata frame. Scale proposals are the residual energy center plus/minus
two, zero/minimum codes, and the two incumbent half-frame scales. Lag proposals
include the strongest residual lag, reliable source period and its neighbors,
two separated residual alternatives, and both incumbent half-frame lags.
Deduplicate and keep legal ranges. Try every legal gain 0..14 in steps of two,
using the established clipping-aware exact integer pulse fitter. There are
at most nine scales and eight lags, hence at most 513 parameter fits per frame.
Each fit tests every one of sixteen legal positions and two signs in all
sixteen 20-sample groups. Charge the winning-block replay as additional work.
Unknown source periods remain unknown, not manufactured pitch targets.

## Complete-output admission and target frontier

Save every complete result, immutable metric record and counted attempt before
continuing. One atomic pointer identifies the protected best result; exported
WAV samples use the verified PCM16 writer and must match native PWM exactly.
The old format incumbent always remains eligible at the same actual complete
3 kbit/s cap. New candidates must preserve full PCM/PWM SSE, STOI, fixed-source
period tolerance counts and hard-clipped samples relative to that incumbent.
Rank admitted candidates with the same source-frozen paired voice/noise score.
These are finite-search conventions, not a subjective or global optimum.

Retain the complete admissible quality/size/spectral-density frontier, not only
one selected stream. The firmware owner measures full linked program+tables+
data, static SRAM/stack, active-IRQ cycles and underruns for useful candidates
at several densities. Reject a candidate that exceeds the agreed CPU cost
budget or misses real-time output even if compressed bytes fit. Compare with
the same protected ordinary v5 player, using the same toolchain, queue and IRQ
conditions. A small parser alone does not establish a small CPU increase.

Bread pilot first. If it offers a useful quality/target-cost point, freeze the
settings before the existing 27 complete four-second clips. Keep the original
voice-separated tuning/heldout split, source-bound quiet/noisy derivatives
and music/synthetic negative controls; disable STOI for non-speech. Do not
retune on heldout outcomes or count this format experiment as an old host-only
round. Private audio, paths, identifiers, logs and fingerprints stay ignored.
No publication or push is authorized by this prototype task.
