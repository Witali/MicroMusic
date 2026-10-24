# Experimental long-frame HQ4

This separate decoder removes the existing HQ4 stream's 256-sample maximum
frame hold. It is research infrastructure, not a selected public speech model.
The current public HQ4 and Tiny images are unchanged.

The need arose while examining a complete 16.812-second input: even with no
coefficient updates, the existing HQ4 format needs at least 493 frames and
990 stream bytes. Its 406-byte decoder leaves only 617 stream bytes. The user
subsequently selected just the final phrase, so full-recording encoding was
stopped; no claim is made that the long recording has been compressed acceptably.

The lattice, excitation and sample timing retain the existing arithmetic.
Two registers hold a 16-bit frame counter. Extended headers use bits 5:0 for
duration divided by 64, with zero retaining the old 256-sample alias. The EOF
marker is still 0xff, so valid holds are 64..3968 samples in steps of 64.
All existing short HQ4 headers remain byte compatible. The total recording
length is not represented by a 16-bit field and may exceed 65535 samples.

The decoder is **442 bytes** including one-shot stopping, compared with 406
bytes for the selected HQ4 decoder. It leaves **581 stream bytes** plus one
EOF byte in 1024-byte Flash. It uses no EEPROM. Longer holds save frame headers
but reduce the rate of pitch, energy and spectral changes; they are most
plausible for long silences or stable sounds. There is no intelligibility claim.

`../long_hq4.py` implements strict pack/unpack. `tools/encode-long-hq4.py`
accepts explicit JSON `frames` and `durations`; it does not analyze recordings.
It rejects oversized images and independently verifies the assembled image
against the exact integer decoder, including a full phrase of centered silence.

Reproduce parser checks and the assembled synthetic study from the repository
root (add the local toolchain paths where necessary):

```text
python tools/test-long-hq4.py
python tools/encode-long-hq4.py --self-test --output build/new-speech/long-duration-synthetic --avr-bin PATH_TO_AVR_BIN --node PATH_TO_NODE
```

Five parser/roundtrip tests cover every duration and pitch mode, all coefficient
update modes, existing retained streams and malformed/truncated input. The
synthetic assembled test covers all 62 duration codes, noise and both pitch
paths, all excitation modes and coefficient update classes. Its 124992-sample
phrase crosses 65535 samples. All **249984** speech/tail samples match in the
reference, optimized WASM and unoptimized WASM engines. The 752-byte image has
309 stream bytes. No interrupts or samples are lost; sample intervals are
1279..1281 cycles and the tested minimum foreground slack is 673 cycles.
This is a measured bound for this synthetic model, not a worst-case bound for
arbitrary coefficient patterns. It has not been tested on physical hardware.

The retained machine-readable result is
`ATtiny13A/Sound/research/long-hq4/synthetic-build.json`. Generated HEX, ELF,
binary, disassembly and PCM stay under ignored `build/`.
