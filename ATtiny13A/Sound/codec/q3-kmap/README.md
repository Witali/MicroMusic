# K1/K2 coefficient-map AVR experiment

This separate tagged format gives the first two lattice stages sixteen signedQ7 values each. The encoder chooses their indices and values automatically. The other six stages retain the old signedQ3 coefficients. The complete EEPROM layout is32 bytes of packed4x16 pulse templates, then16 K1 map bytes and16 K2 map bytes. Program the Flash and EEPROM images together.

These measured capacities include the decoder, speech, EOF byte and linker alignment:

| Multiplication | Rounding | Decoder bytes | Maximum speech bytes | EEPROM bytes |
|---|---|---:|---:|---:|
| Stage-selected Q3/Q7 | Floor |458|565|64|
| Stage-selected Q3/Q7 | Nearest |464|559|64|
| Unrolled Q7 | Floor |470|553|64|
| Unrolled Q7 | Nearest |474|549|64|

Every maximum image assembles and verifies at1024 Flash bytes. A builder success also requires the fitted stream to finish its sample work before the7.5kHz deadline at9.6MHz. Memory capacity alone does not establish that deadline for arbitrary coefficients.

The [music multiplication recipe](../AVR_ASSEMBLY_RECIPES.md#recipe-unrolled-small-multiplication-from-our-music-firmware) uses conditional additions without DEC/BRNE loops. Its literal byte-product implementation depends on the smaller music operands. Here the optional unrolled implementation uses seven unsigned rotate/add steps, then corrects the result for the adjusted sample sign. This produces the complete signedQ7 result, including sample−128, without copying the music routine's unsafe byte-product assumption.

On identical edge-test PCM, the stage-selected floor profile needs458 bytes and has204 cycles of minimum slack. The loop-free profile needs470 bytes and has117 cycles. For nearest rounding the corresponding results are464/186 and474/84. A second comparison uses exactly the same550-byte stream and EEPROM for the complete22,272-sample performance fixture: the PCM hashes are equal, with136 cycles of minimum slack for stage-selected multiplication and114 for unrolled Q7. Their total Flash sizes are1010 and1022 bytes. The deterministically coalesced input is a timing fixture, with no quality claim. Thus unrolling Q7 fixes the initial generic multiplier's speed problem, but the stage-selected version is both smaller and faster on these speech coefficients.

The literal16-bit, three-bit Horner adaptation was also assembled and checked in92,160 scalar cases. It adds24 bytes to either stage-selected core:458→482 and464→488. With floor rounding and coefficient magnitude1, the existing product takes26–27 cycles including RET, while Horner takes38–39; at magnitude7 the existing product takes56–57 and Horner still38–39. Add3 cycles for RCALL. Nearest rounding adds1 cycle to each of these measurements. This explains why applying the music routine's unrolling to every small Q3 coefficient is not selected. The [benchmark report](../../research/q3-kmap-avr-qualification/music-unroll.json) and [reproduction tool](../../../../tools/probe-q3-kmap-music-unroll.py) retain both comparisons; the literal Horner result is an arithmetic/core-size test, with no complete-player deadline claim.

Both implementations inline coefficient-pair reading. The old generic reader called a helper eight times per full update; the new reader handles the mapped first pair directly and decodes the remaining pairs without those call/return costs. The [rejected432-byte generic prototype](../../research/q3-kmap-generic-timing/README.md) remains independently reproducible, with its original binary hash and missed sample deadline.

Six [AVR tests](../../../../tools/test-q3-kmap-avr.py) pass. They check829,440 actual signed products in three engines, including every byte input and every stable signedQ7 coefficient, plus1,536 waveform lookups with and without an interrupt between the lag shift and nibble selection. Twelve full images verify119,616 PCM samples exactly, covering index0, EEPROM address63, partial/repeat frame updates, extended durations, both rounding rules, legacy uniform-map compatibility and all four maximum Flash images. No physical-chip test is claimed. The retained [qualification report](../../research/q3-kmap-avr-qualification/report.json) fingerprints the source and images.

The selected full22,272-sample quality-study candidate uses458 decoder bytes and562 speech bytes:1022 Flash plus64 EEPROM. All66,816 phrase-and-silence samples match in the three engines, its four wrap counters are zero, and its minimum measured slack is135 cycles. This is a memory/execution qualification; the separate quality study retains better existing speech.

Build a model with the [builder](../../../../tools/build-q3-kmap.py):

```text
python tools/build-q3-kmap.py --stream SPEECH.hq --table MODEL.json --samples 22272 --output build/q3-kmap-check --avr-bin AVR_BIN --node NODE
```

Use `--rounded` for nearest rounding or `--unrolled` for the loop-free profile. The table input can also be the raw64-byte EEPROM image. JSON models must use schema `hq4-q3-kmap-v1`, with `pulsebook` shaped4x16 and `coefficient_maps` shaped2x16. Pulse values are−7..7; map values are−127..127. Nibble0 is valid only for the two mapped stages. Nearest rounding resolves exact halfway cases toward positive infinity; the established byte-negation behavior is preserved.
