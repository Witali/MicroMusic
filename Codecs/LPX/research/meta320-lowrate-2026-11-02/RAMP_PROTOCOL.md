# Costed raw-scale interpolation experiment

Registered before fitting outcomes. This is a distinct synthesis experiment
after the rejected metadata320 and existing-header tuning pilots. Keep the
original pinned host-round campaign, formats and stopping ledger unchanged.
The user's decoder-cost allowance is a ceiling for a useful measured result,
not permission to accumulate unmeasured costs across experiments.

## Explicit version 10 semantics

Version 10/mode 4 uses plain v5/P4 spectra, 160-sample metadata and 20-sample
innovations. Version 10/mode 15 uses sparse80 spectra, 320-sample metadata and
80-sample innovations. Headers remain22 bytes and payload bits are unchanged
from the respective old syntax. This is deliberately new synthesis: replacing
the version byte is a payload adapter, not an arithmetic-equivalent expansion.

At each metadata tuple decode raw target `scale_table[code*8]`. The previous
endpoint is the preceding target; for the first tuple previous equals target,
including when target is zero. At each20-sample phase k=1..8 use
`(previous*(8-k) + target*k + 4) >> 3`, then the existing exact Q4 caching when
enabled. Sparse80 holds the target after its first 160 samples until its next
tuple. Interpolate raw steps, never table indices. Raw steps0..4016 keep the
weighted sum plus4 within signed16 range. Spectrum, pitch arithmetic, pulse
limits, postfilters and PWM transfer stay unchanged. The target implementation
updates its cache per 20 samples and adds four cold SRAM bytes, with no new
per-sample arithmetic. Actual Flash and throughput remain measured quantities.

## Protected input and finite host candidates

Use the latest accepted ordinary v5/P4 or sparse80 complete stream as the
immutable protected incumbent, at exactly3 or2 kbit/s including headers and
all stored terminal packets. Keep the complete declared target at its already
chosen once-per-source quiet gain. Use the same established source pitch
windows640/160. The initial fitting study uses320-aligned complete targets;
the independent model/parser tests separately exercise every partial tail.

There are exactly five new complete attempts per incumbent. First convert
only the version byte to the explicit ramp format, holding every payload and
filter byte unchanged. Then independently refit metadata and legal pulses
through the new exact ramp recurrence, crossing waveform/clipping-aware loss
with current-block/one-block-lookahead parameter selection. Spectra, preQ14 and
brightQ14 remain byte-identical. All candidates start from zero true state;
the selected target raw step carries into the following metadata frame.

For a full refit use residual-energy scale center plus/minus two, zero/minimum
codes, and the incumbent tuple's scale, deduplicated and clamped. This gives
at most eight scale proposals. Lags include strongest residual lag, finite
source period and its -1/+1 neighbors, two separated residual alternatives,
and the incumbent lag: at most seven legal lag proposals. Test every legal
gain 0..14 in steps of two, omitting repeated gain-zero work at other lags.
There are at most400 parameter fits per metadata frame. Each fit exhaustively
chooses the existing position/sign pulse in every20-sample P4 or80-sample
sparse group, carrying full integer history. Charge the winning-block replay
and every duplicate final output attempt. For the lookahead branch, score each
current tuple's fitted block together with the next complete block rendered
using the incumbent's frozen future tuple/pulses, but the candidate's current
raw target as that future block's previous endpoint. Discard the speculative
future state; commit only the current winning block and refit the next block
normally. This isolates the endpoint dependency without claiming an optimal
future fit. The final block has no invented tail/lookahead. Count every such
future sample/group render separately. Do not retune these bounds after
observing the public stimulus or heldout results.

## Independent admission and target measurements

The old incumbent always remains eligible. Every complete attempt is checked
against an independent per 20 raw-step model and two actual version 10 C paths:
raw-step and Q4-cached arithmetic, both with ASM explicitly disabled. Do not
use an old v5 expansion to claim ramp arithmetic equivalence. Pin source,
compiler, options and native-library hashes; verify the current C++ source
before and after fitting. The firmware owner separately checks target ASM/C
equivalence, all stored-tail validation and default-off compatibility.

Keep the same full PCM/PWM SSE, STOI, fixed-source period tolerance and hard-
clipping guards relative to the protected incumbent. Rank admitted results by
the existing paired source-frozen voice/noise score. Save all complete bytes,
metrics and counted attempts with one recoverable atomic best pointer; export
only verified native-exact PCM16 WAV. No output gain fitting or transposition.

Bread tuning first. If useful, freeze settings and compare on the established
27 complete four-second clips with the existing voice split, quiet/noisy
derivatives and non-speech controls. Useful candidates require complete Flash,
static SRAM/stack, active-IRQ output/underruns and producer throughput measured
against the same root-approved ordinary baseline. Measure the combined cost
of enabled features; do not stack separate20% allowances. A useful sound gain
and B/A<=1.20 are both required before promotion. Objective proxies are not
listening scores, and this finite study does not prove global optimality.

No broad run, adoption, publication or push is triggered by preparing this
protocol. Private media, input identities, paths, fingerprints and detailed
logs remain in ignored build storage.
