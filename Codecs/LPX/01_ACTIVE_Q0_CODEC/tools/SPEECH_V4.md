# Experimental fixed-rate speech v4

This is a lossy speech prototype, enabled only with `LPX4_ENABLE_SPEECH=1`.
It does not change the v2/v3 formats or their defaults. The public
`Lpx4HybridCore` interface, Flash access and selectable C/AVR5 ASM arithmetic
remain shared. Neither a floating-point decoder nor trained tables are added.
Compile the core and every consumer with the same speech flag: enabling it
adds two state bytes to the class. Arithmetic selection is still independent.

The 20-byte little-endian header uses the existing `<4sBBHIHHHH` layout:
`L4HY`, version 4, profile 4 or 6, 8000 Hz, exact sample count (1..64000),
pre-emphasis Q14, brightness Q14, frame 320, parameter block 160. A complete
final packet is mandatory. Exactly `20+ceil(samples/320)*(20 or 30)` bytes
are accepted; no partial packet or trailing extension is accepted.

Each 40 ms packet is LSB first, without intermediate byte alignment:

| Field | 4 kbit/s | 6 kbit/s |
|---|---:|---:|
| Ten ordered scalar LSF indices | 10×5 bits | 10×6 bits |
| Reserved zero bits | 0 | 6 |
| Two sets of energy, lag, gain | 2×(5+7+3) | 2×(5+7+3) |
| Sixteen pulses (one per 20 samples) | 16×(4+1) | 16×(5+4) |
| Total | 160 bits | 240 bits |

After the spectrum, each set of parameters is followed immediately by its
eight pulses. LSF is `(index << (10-bits)) + (1 << (9-bits))`. Indices must
strictly increase. The first 20 ms uses the existing two-anchor interpolation
from the preceding packet's spectrum; the second 20 ms holds the endpoint.
The initial frame holds its initial spectrum. This changes spectral time
resolution and quantization, not just residual precision.

Energy is the existing scale table at `index*8`; lag is `18+code`, gain is
`2*code` in Q4 (0..14). The existing signed 6-bit excitation history and
saturation are retained. At 4k, position code `i` maps to `i+(i+2)/4` with
integer division (16 positions across the 20 samples), sign selects -8/+8.
At 6k, position is 0..19 (20..31 invalid), amplitude is signed two's-complement
4-bit (-8..7). Positions reset every 20 samples. Two pulses are loaded per
existing 40-sample sparse subframe. A pulse after the exact sample tail is
padding and produces no output. There is no CRC; syntactically valid bit
changes can change audio without detection. Restart uses a fresh header and
zero state; arbitrary packet seeking without state is not supported.
The MCU validates parameters as they are consumed. Unread fields after the
exact sample tail are not validated, even though the final packet's full byte
length is mandatory. Python `unpack` validates all fields, including padding.

The Python encoder averages two LPC analyses per packet, quantizes ordered
LSF values, proposes pitch/energy through inverse filtering, then searches
energy, pitch gain and pulse location/amplitude through exact closed-loop
integer synthesis. It is a bounded greedy search, not a globally optimal
CELP encoder. No codebooks are trained. Input is at most 8 seconds.

Example (with the project's Python dependencies and native g++ configured):

```
python tools/speech_v4.py input.wav build/speech4 --profile 4
python tools/speech_v4.py input.wav build/speech6 --profile 6
```

Payload rates are exact only for whole 320-sample packets. Include the header
and final padding when reporting file bitrate: a 4-second clip is 4040/6040
bit/s; an 80 ms clip is 6000/8000 bit/s. Output has no inserted sample shift.
Packet collection is 40 ms; centered LPC analysis needs future input (up to
48 samples beyond a packet at the default 256-sample window). The offline
search itself has unbounded wall-clock latency and is not a real-time encoder.
AVR playback additionally prefills its configured sample queue. Supported
real-time decoding claims require active-IRQ measurements, not the bitrate.

Quality measurements and simulator conditions are recorded separately in
`../../SPEECH_4_6_8_PLAN_RU.md` and the speech research report. No human
listening rating is inferred from SER/STOI.
