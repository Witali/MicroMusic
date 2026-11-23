# Prospective low-rate quality study

The incumbent is exact public commit `ba02e453`, including the existing V3
search. The new proposal generator must preserve the same V9 format, complete
budgets, decoder arithmetic and memory requirements. Archive and build this
incumbent from Git rather than from changing working files.

## Development and new holdout

The three public phrases remain tuning material. The established 27-case
corpus and the entire previous 24-case wideband study are now known development
or regression material. Their former held-out results cannot establish new
independent generalization.

Freeze 12 unseen complete 4–8-second utterances from the existing official
native-rate reserves, before any new holdout encoding:

- Three Russian and three English FLEURS sources, in frozen reserve order.
- Six VCTK sources from distinct speakers, also in frozen reserve order.
- Native source rate at least 16 kHz; exact original prepared PCM binding.
- Exclude all 24 actual prior-primary source identities, PCM hashes and
  original source bindings. For VCTK, also exclude all prior-primary speakers
  and allow each new speaker only once. FLEURS has no published speaker ID in
  the retained metadata, so claim unseen utterances rather than speaker
  independence there.

Also audit old-27 and public-pilot provenance: compare retained original
member/basename bindings, available file/PCM hashes and exact direct-to-8-kHz
prepared PCM hashes. Those older records lack stable speaker identifiers, so
no detected binding overlap does not prove speaker independence from them.

Eligibility and order depend only on the source. Do not replace cases because
of codec output. Preserve whole utterances, level and complete sample count;
do not crop, denoise, fit gain or align an output to improve its metrics.
Private media, identities, transcripts, provenance, hashes and detailed records
remain under ignored `build/` in this task worktree. Only anonymous numeric
aggregates and general code/protocol are suitable for tracked evidence.

## Matrix and encoding

Prepare the 3-kbit/s targets directly from each native source to 8 kHz, using
the existing rational polyphase reference preparation and PCM16 rounding.
Prepare P4 16-kHz targets directly from the same original sources. Never route
16-kHz references through 8 kHz. These are also part of the primary matrix.

The primary new holdout has 24 jobs: 12 complete strict-3-kbit/s jobs at 8 kHz
and 12 P4 jobs at 16 kHz. The strict whole-file cap is
`floor(samples*3*1000/(8*8000))`. P4 uses the frozen incumbent's explicit
original complete cap.
Both encoders receive identical prepared bytes. Use four search calls, no
size allowance, preserve level and no automatic quiet gain throughout.
Retain the exact current-V3 incumbent as a candidate.

Preparation and baseline compilation may precede the proposal freeze, but no
new holdout baseline or candidate encoding may run until the owner freezes the
algorithm and constants. Snapshot the candidate source/binary before the run;
do not tune from the new holdout. Coordinate at most three numerical workers
across the team; this corpus task initially uses one.

## Unchanged independent evaluation

Reuse the metric equations from `v9-quality-all-2026-11-23` verbatim: actual-rate
STOI, complete PCM/PWM errors, native-rate pitch observations, the separate
antialiased 8-kHz production view, native 512/256 symmetric-Hann spectral and
temporal measurements, source-only noisy/unvoiced masks and envelope/onset
diagnostics. Keep the original score weights, zero-loss floors and complete
admission rules. No new thresholds, fitted output gain or alignment.

Decode every output completely with the native C reference, checking exact
sample count/rate, clean EOF and fixed PWM transfer. Preserve all cases and
metric memberships, including missing results and failed independent gates.
Report all eight objective groups, SSE/SER/RMSE and peak errors, PCM clips,
PWM rails, native-pitch lost/gained/missing/octave observations, per-band errors
and noisy/burst peaks. Keep individual regressions visible when averages fall.
Objective scores are not perceived-quality percentages or validated true F0.

The 3-kbit/s test supports frequencies only through its actual 4-kHz Nyquist
limit. P4 at 16 kHz covers the actual 8-kHz limit. Neither this
bounded cohort nor its controls establish arbitrary-file memory/runtime or
additional MCU real-time support.
