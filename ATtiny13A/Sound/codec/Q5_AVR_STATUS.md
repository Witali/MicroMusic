# Q5 firmware feasibility

The best retained Vinni head-Q5 model still has no complete ATtiny13A firmware.
Its standalone audio is excluded from the firmware player. A firmware entry
requires the complete image, speech data, EEPROM, memory and deadline checks.

The original phrase is unchanged: 22272 samples at 7500 Hz. The model uses
132 frames, two Q5 reflections, six Q4 reflections, Q6 word states and eight
32-tap Q2 excitation pulses. Its measured STOI is 0.893135861645246.

`tools/pack-q5-stream.py` now serializes every numerical control and pulse tap
without loss. It selects each field's coding automatically and restores the
complete measured PCM hash. The container includes 36 bytes of header and
field descriptors and 160 bytes of pulse data.

| Exact transport | Total data | Optimistic Flash with existing arithmetic and 64 EEPROM bytes |
| --- | ---: | ---: |
| Fixed bit fields | 1236 B | 1400 B |
| Rice codes with frame differences | 1068 B | 1232 B |
| Rice, differences and explicit zero codes | 1054 B | 1218 B |

The Flash estimate adds the existing 228-byte assembled arithmetic chain and
optimistically puts any 64 bytes of data in EEPROM. It omits startup, vectors,
PWM scheduling, excitation, the stream unpacker and EEPROM access. Even this
incomplete allocation exceeds 1024 Flash bytes by 194 bytes. No HEX is emitted
and no timing or full-player qualification is claimed.

This rules out these exact representations with the current arithmetic chain;
it does not prove that every possible Q5 codec is too large. A useful next step
is to fit a small shared spectral-vector dictionary and sparse corrections
through the exact decoder, with a whole-player byte budget from the start.
Lossless packing alone has not closed the gap. Any reduced model must be
remeasured against the original and the protected examples before publication.

Reproduce from the repository root:

```powershell
python tools/pack-q5-stream.py --output build/q5-firmware-budget
python tools/test-q5-stream.py
```

The packed streams stay in ignored `build/`; the retained
[`flash-budget.json`](../research/q4-pulse-shapes/head5/flash-budget.json)
records byte counts, stream hashes and the model hash. The arithmetic proof is
[`filter-head5-best.json`](../research/word-q4/filter-head5-best.json).
