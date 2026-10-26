# LPX: bounded exact packing versus total firmware size

ATmega328P/AVR5,16MHz/8kHz, AVR-GCC7.3 -Os with local O2=7, explicit
ASM, unroll9, queue512/prefill384, active IRQ, v3mask24 plus explicit
speech/compact flags. The AVR-LibC hardware definitions and existing C/ASM
arithmetic are unchanged. These are simulator measurements, not board data.

V5 packs the exact same ordered scalar LSF values as v4. Prefixes select
repeat, unsigned gaps, or zigzag temporal deltas. Fixed Rice parameters are
k1/k2 for gaps and k0/k1 for deltas on profiles4/6; quotient8 escapes to
a bounded literal. The decoder uses existing previous/current LSF state,
not a codebook. Added state is one byte. Pure repacking preserves every
base field and every PCM/PWM byte. No new handwritten ASM is introduced.

For two positions0..19, encode `pair=p0+20*p1` in9 bits. After checking
pair<400, this portable C expression gives the second position exactly:

```c
uint8_t second = ((uint16_t)(uint8_t)(pair >> 2) * 205u) >> 10;
uint8_t first = pair - second * 20;
```

`pair>>2` is0..99 and its product with205 fits unsigned16. The identity
follows from floor(pair/20)=floor(floor(pair/4)/5); the reciprocal is exact
only over this bounded domain. All400 combinations are tested against
division/modulo. This avoids requiring a general16-bit division helper;
an isolated speedup for this expression alone is not claimed.

Optional extra sparse innovations must merge with primary pulses at an
equal position before q saturation. Sorted insertion uses at most three
entries in the old ten-entry arrays. A second pulse at the same position
must not simply be appended: the old sparse loop consumes one event there.

Four common4-second speech clips: exact files average1666.75/2485.75 bytes
instead2020/3020, saving17.49%/17.69%. With refined base excitation and
additional innovations, averages are1873.5/2647.75 bytes while full SSE/STOI
improve in every case. Max absolute error is not monotonic; three points
worsen. No lossless claim applies to these excitation changes.

Under the shared v5-enabled binary, mean wall cycles/sample are
948.53→954.09→954.74→957.33 for4k and
950.92→955.63→956.40→959.64 for6k (baseline/exact/refined/enhanced).
All32 full PWM runs and enhanced8-second ASM/+100IRQ controls have zero
underruns. C fallback is exact but costs2771/2775 cycles/sample and underruns.
SRAM1105 includes queue/harness; observed stack123 after ready, margin820.

Smaller data does not necessarily mean smaller firmware. Shared code is
9171..9172 bytes excluding stream versus8334 in the previous v4-only build.
For one4-second recording, enhanced total Flash grows by691.5/465.5 bytes
on average despite the smaller files. Exact packing still costs484/303.5
more bytes of complete firmware at that duration. Cost amortization across
longer/multiple recordings is an estimate, not a measured combined image.
Final-source feature-off controls use8326 bytes, so the isolated enable
cost on that source is846 bytes plus one SRAM byte.

No hardware arithmetic or ABI shortcut is needed. All consumers must agree
on the compact class-layout flag. Default remains C without explicit ASM,
including on AVR; Flash access is selected independently. Full legacy
91-stream regression remains exact with zero underruns. The existing speed
loop is closed; these measurements concern a new format/quality tradeoff.

Original project implementation; no external codebook/code was adapted.
[Format](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/SPEECH_COMPACT.md),
[measurements and limits](../../Codecs/LPX/research/speech-compact-2026-10-26/README.md).
