# Optional V9 whole-file output gain

Bit 5 (`0x20`) of the V9 profile byte marks a two-byte, unsigned **Q4.12**
output-gain coefficient. Unity is 4096; legal stored values are 1..65535.
The low five bits remain the profile (4, 6 or 15), bit 6 retains V9 Long and
bit 7 retains extra pulses. Sparse80 still forbids the extra-pulse flag.

The gain word follows the original header: offset 13 for ordinary V9,
offset 17 for V9 Long. Total header sizes become 15 and 19 bytes. The original
payload-length field still counts only coded payload bytes, excluding gain.
All other header offsets, counts, entropy syntax and sample timing stay intact.
Truncated/zero gain words, mismatched payload lengths, trailing bytes and
nonzero final padding are rejected. Old readers reject the new profile flag;
gain-tagged files require an updated decoder. Unmarked files remain unchanged.

Gain is applied to the final postfilter Q14 sample, before PCM16/PWM conversion,
with no feedback into LPC, excitation, pitch, de-emphasis or brightness history:

```text
gainedQ14 = clamp((postfilterQ14 * gainQ12 + 2048) >> 12, -16384, 16384)
```

The shift uses the existing fixed-arithmetic convention (ties toward positive).
The signed32 product is bounded: `16384 * 65535 + 2048` fits. PCM16 and PWM then
use their existing conversion functions. Explicit floating synthesis applies
the same coefficient before its final quantization. The coefficient is constant
for the entire recording, including pauses and Long streams.

`LPX4_ENABLE_FILE_GAIN` defaults to 1 for V9 and 0 otherwise. Define it as 0
consistently in all translation units to retain the legacy reader/layout and
reject the extension. The retained coefficient costs two bytes of decoder SRAM;
it is outside the hot state and does not move existing ASM field offsets.
Hardware memory access and arithmetic backend selection remain independent.

The Web encoder defaults to unchanged level. Enabling normalization measures
the **completed decoded output**, selects one gain from target mono LUFS
(-30..-9), maximum boost (0..24 dB), and a -1 dBFS decoded sample-peak ceiling,
then writes the quantized coefficient. Defaults are -18 LUFS and at most +12 dB.
The target may be unreachable because of peak or gain limits. Shorter-than-400ms
or below-gate material retains unity. A marked unity word is valid.

P4/P6 search operates on the original input; normalizing metadata never refits
its coded payload. The 3/8 kbit/s presets reserve the two metadata bytes before
candidate selection and validate the final complete file against the same cap.
There is one continuous file and no time-varying gain or history reset.
The player and WAV export honor the coefficient automatically.

The bounded Python V9 repacker retains the gain word when repacking to V9.
It refuses a non-unity gain when converting to v5/v8, which cannot represent it.
V9 Long remains outside that bounded repacker's existing scope.

See [the loudness implementation](host/LOUDNESS.md) and
[AVR validation](../research/lpx-file-gain-2026-11-23/README.md) for measurement,
arithmetic fallbacks, MCU timing and the limits of the recorded evidence.
