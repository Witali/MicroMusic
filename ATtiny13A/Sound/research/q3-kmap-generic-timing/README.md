# Generic Q7 timing diagnostic

This preserved prototype is rejected for playback. Its complete image fits memory but does not finish every sample at9.6MHz/7.5kHz. It does not replace any accepted firmware.

The retained588-byte stream covers the complete22,272-sample Vinni input. EEPROM is32 bytes of packed pulse templates plus two16-entry signedQ7 coefficient maps. The floor core assembles to432bytes (rounded counterpart436bytes); the tested full image is1022Flash+64EEPROM. All runtime stages use the initial variable-length bit-serial Q7 product.

Three-engine verification agrees with the integer oracle for the first5,507 PCM samples, with zero value mismatches, then rejects the missed output deadline. The maximum measured completion time is1,663cycles against the1,280-cycle sample period. A prefix match and a size pass are not a real-time playback pass.

The frozen assembly reproduces original imageSHA256 `e3ab03492d8a37d9bb17f60d3a818ba60feab79ed7272832b6a097a079d662e9`. The attached build report records source hashes for this reproduction; comments differ from the initial exploratory file, but the assembled image is byte-identical. No hardware test was performed.

Reproduce from the repository root (provide installed AVR/Node paths):

```text
python ATtiny13A/Sound/research/q3-kmap-generic-timing/reproduce.py --stream ATtiny13A/Sound/research/q3-kmap-generic-timing/speech.hq --table ATtiny13A/Sound/research/q3-kmap-generic-timing/table.json --samples 22272 --output build/q3-kmap-generic-timing-reproduction --avr-bin AVR_BIN --node NODE
```

The expected process outcome is nonzero and `status: verification-failed`; inspect the explicit timing error in `build.json`. The source oracle is `codec/q3_kmap.py` from commit`cfef498`. A later fast-path/unrolled implementation must be qualified and committed separately.
