# Quality-reference listening gallery

The user ranked Vinni's six-bit coded excitation first, Q3 second, and parametric
LPC2 Improved third. This is listening feedback on that phrase. The six-bit
stream remains a separate baseline in every gallery card; numeric selection of
a smaller candidate never silently replaces it.

The final firmware requirement is **1024 bytes Flash including executable code,
plus 64 bytes EEPROM**. These larger PC streams do not meet it. Their role is
to identify quality losses before fitting a compact integer implementation.

`listening-config.json` refers to the four known phrases and twenty prepared
RU/EN recordings, with source attribution, source hashes in the probe reports,
and the same source-matched previous decode. Recreate the ignored gallery after
the fixed-profile and LPV1 probes have produced their documented build outputs:

```powershell
python tools/make-lpc2-quality-player.py --manifest ATtiny13A/Sound/research/lpc2-comparison/listening-config.json --output build/lpc2-corpus-listen
```

At local port 8146 the page is `build/lpc2-corpus-listen/`. It compares original,
previous, parametric LPC2, six-bit coded excitation, and an additional compact
candidate when different. The common engineering thresholds are STOI 0.98,
eSTOI 0.95 and raw waveform SNR 26 dB; eleven of twenty-four recordings meet
all three. Failed targets are shown explicitly. These numbers do not establish
subjective naturalness or acceptance for a specific speaker.

Every listening track receives the same 70 Hz highpass, one global RMS match
and one shared peak scale per recording. Raw WAV files remain available without
these presentation adjustments. Container links include actual headers, LPC2
parameters, block scales, codebooks and lossless wrapper overhead. Decoder code
is excluded and explicitly identified as such.

`listening-selection.json` retains actual storage alternatives and metrics.
All 120 fixed-width residual containers are reversibly packed and restored
byte for byte before their size is considered. LPV1 candidates remain raw
containers; no unimplemented extra storage saving is counted for them.
`lossless-storage.json` records the six-bit Vinni reduction 17562 → 16407 bytes
without changing a single excitation code or predictor parameter. Lossless
packing alone is far from the final 1 KB budget.
