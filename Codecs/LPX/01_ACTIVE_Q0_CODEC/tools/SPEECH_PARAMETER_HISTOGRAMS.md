# Parameter measurements before a new format

`speech_parameter_histograms.parameter_histograms(streams)` accepts valid v5
byte streams and returns anonymous aggregate scale/lag/gain histograms. The CLI
accepts local stream files and `--output report.json`; it stores no input names,
paths, media hashes or individual stream fingerprints in that report.

Each stream starts a new parameter history. Counts distinguish every stored
160-sample parameter packet from packets that begin before actual EOS. The
mandatory unplayed final packet is never silently removed. Gain is counted in
stored `gain/2` units; lag absolute codes use `lag-18`, while lag deltas remain
sample differences. The output includes tuple repeats, individual field repeats,
absolute-value histograms and signed delta histograms.

Two arithmetic sketches expose marker cost without selecting a format:

- A tuple marker keeps the first 15-bit tuple absolute. Every later tuple uses
  one flag bit and, when changed, its existing 15 absolute bits.
- Independent field markers keep the first tuple absolute, then use one bit per
  field plus its existing 5/7/3 absolute bits when that field changes.

These counts concern the parameter layer only. They exclude a new format's
header, decoder, padding and other packet fields. Delta distributions do not
define a delta syntax. There is no new encoder/decoder format, no MCU change and
no measured firmware saving. Format work remains gated on the separate search,
objective and marginal-allocation results, followed by actual complete-image
Flash, SRAM and active-IRQ validation.
