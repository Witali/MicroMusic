# Opt-in source-period excitation alternative

`reseed_speech_excitation.reseed(reference, blob, decoder, *, source_lags,
horizon=160, gain=14, periodicity_weight=0)` constructs a raw v5 alternative.
It is not imported by existing encoder defaults and does not change the MCU.

The caller supplies one reliable source lag per audible 160-sample block:
18..145 selects that lag, while 0 retains the original pitch tuple. Out-of-range
periods are rejected, never silently clamped. `gain=None` retains original
gains; otherwise the supplied even gain is used only on selected source blocks.

Base pulses are fitted causally against the complete original-level PCM using
40/80/160/320/640-sample exact integer lookahead. Future fields not yet fitted
remain from the input stream. Each audible 20-sample pulse is tested at every
legal position/amplitude, so the bound is at most 33 local renders per pulse
for profile 4 or 321 for profile 6, including the unchanged control.

The optional local periodicity term uses the supplied fixed delay and a
DC-centered normalized difference, added to local MSE relative to source energy
with a one-PCM-unit power floor. Constant or vanished output pays periodicity
error 1. A candidate pitch tracker cannot hide missing periodicity. This term
does not distinguish every harmonic ambiguity; a separate full-reference
criterion and listening assessment must control admission.

Spectrum, scale codes, header filters, extra pulses and mandatory unplayed tail
fields remain unchanged. Canonical serialization is required not to grow;
noncanonical input may become smaller. Original samples, gain and duration are
not changed. Complete candidate PCM/PWM must match the original integer model
and supplied native decoder. Tests check both common and v5-only layouts.

The returned report always says `raw_alternative=true` and
`quality_adopted=false`: source-period forcing and greedy local fitting can
worsen whole-record SSE/STOI or voice character. It must not replace the input
automatically. Seven focused test groups cover exact reachable pitch correction,
perfect rollback, quiet relative ranking, output collapse, malformed settings,
input ownership, native mismatch, deterministic results and stored-tail bounds.
