# Successive quality rounds and stopping rule

Registered on 2026-11-02 before running the follow-up rounds. The user's active
goal is to keep improving LPX sound until three consecutive rounds yield no
clear improvement. The initial frozen 27-clip search is round0; its result is
the starting incumbent, not one of three assumed failures.

## Invariants

Keep the exact complete-file 2/3 kbit/s caps, sample count, sample rate and
declared auto-quiet target from round0. Do not transpose/resample the target,
fit an output gain or change the decoder, tables or bitstream syntax. Count
every original header, full stored final packet and padding byte. Keep all
previous complete best streams; a failed experiment cannot erase them.

Each round uses the same 27 existing four-second corpus clips. The public
2.4-second phrase remains a tuning/listening example, outside confirming
corpus aggregates. The established heldout voices and their quiet/noise
derivatives remain heldout. Parameters and trial ceilings are fixed in the
operator's protocol before its outcomes are examined. No repeated tuning on
heldout results. Music and synthetic material are negative controls; STOI is
not a music-quality metric.

## Ordered operators

1. Source-period proposals with legal lag neighbors and gain floors:
   [PITCH_PROTOCOL.md](PITCH_PROTOCOL.md).
2. Existing LSF run coordinates and boundaries, with full excitation refits:
   [SPECTRAL_PROTOCOL.md](SPECTRAL_PROTOCOL.md).
3. Delayed innovation decisions with a bounded beam and unchanged metadata:
   [BEAM_PROTOCOL.md](BEAM_PROTOCOL.md).

Evaluate each round against the complete best available after its predecessor,
not an earlier weak control. A clear gain resets the no-gain count to zero.
When necessary, repeat the registered operators on the newly accepted
incumbents, or preregister another distinct bounded operator before running
it. Stop only when three actually completed consecutive rounds have no clear
gain. Infrastructure repairs, target compilation and format tests are not
quality rounds and cannot increment this count.

## Whole-output admission and evidence

Use `round_admission.py`: independent sparse80-to-v5 expansion when required,
the Python model and both common/v5-only native C receivers must agree on
all PCM/PWM samples. A new candidate must preserve full PCM/PWM SSE and STOI,
source-bound period-tolerance counts, and clipped-sample count relative to
the current incumbent. Among admitted complete candidates use the established
joint source-frozen voice/noise score, actual bytes and deterministic ordinal.
The incumbent always remains available.

All attempted work is recorded, including candidates that serialize to the
same bytes. Such duplicates do not become additional independent outcomes.
Persist immutable candidate bytes/metrics before atomically advancing the
authoritative best pointer. Checkpoint recovery verifies that referenced
stream; `selected.lpx` alone is a convenience copy, not a multi-file transaction.

For the stopping counter, a clear *numerical* gain requires at least one of:

- Mean PWM STOI on the heldout speech subset improves by at least 0.01.
- Aggregate PWM SER on that same subset improves by at least 0.3 dB.
- Source-period tolerance coverage improves by at least 5 percentage points
  across its source-voiced windows, with no selected per-case guard regression.

Report each 2/3 kbit/s budget separately. Show individual/subgroup results so
a small changed subset cannot be confused with universal benefit. Smaller
positive changes are retained and labelled numerical; they do not reset the
three-round counter. These thresholds are a prospective search-stopping
convention, not calibrated audibility thresholds. Human listening may still
find a numerical change inaudible or worse; retain that feedback separately.
Never turn STOI into a percentage of perceived quality or claim complete
pitch preservation from a period-count guard.

Any newly selected useful streams require complete linked AVR Flash,
SRAM/stack and active-IRQ exact-PWM/underrun admission before a firmware
support claim. The existing round0 receipts do not cover changed data. Keep
private audio, source identities, fingerprints and detailed journals in
ignored build storage; publish only code and anonymous numerical evidence
under the user's publication constraints.
