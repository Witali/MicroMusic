# LSF grouping feasibility study

This directory contains a stopped packing experiment and measurements of the
unchanged current LPX decoder. **There is no new LSF1 decoder or admitted file
format.** The production codec and its defaults remain unchanged.

Eight existing P4/P6 LPX files total 8,587 bytes. Counting adaptive groups and
shared exponents for their LSF indices gives:

| Candidate | Complete-file bytes | Selected group packets |
| --- | ---: | ---: |
| Current native Rice | 8,587 | — |
| Native Rice or grouped extension, whichever is shorter | 8,587 | 0 |
| Forced grouped extension | 9,717, calculated | 383 modeled packets, plus 3 repeats |

The forced row is a bit-cost calculation, not an implemented stream/decoder.
Its tags, escape, exponent, mantissas, payload padding and header are included.
The existing native packets are reserialized byte for byte to validate useful
bit accounting. See [exact-analysis.json](exact-analysis.json).

Four bounded one-bin LSF proposals per file were also encoded using the actual
original V9 format and decoder. None passed every complete-output quality and
stability check while reducing file size. The selected output remains the
unmodified baseline: [one-bin-gate.json](one-bin-gate.json).

Consequently the new decoder and full new-format AVR matrix were stopped at
the packing gate. The separate [AVR investigation](avr/README.md) profiles the
current decoder and tests eight existing-setting CPU pilots; it admits no new
performance setting.

The [research report](../../research/lsf1-2026-11-26/README.md) explains the
grammar, corpus, limitations and reproduction. The
[Z80 transfer review](../../research/lsf1-2026-11-26/z80-transfer.md) identifies
encoder-side ideas that retain the current LPX format and AVR decoder.
