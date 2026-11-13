# ATmega328P hardware multiplication in the LSF converter

The direct branch bounds the polynomial coefficient to ±250,000 and the
cosine factor to ±8192. The product fits signed32, and the polynomial
coefficient fits signed24. Treat the first two bytes of the coefficient
as unsigned and the third as signed. Treat the cosine low byte as unsigned
and its high byte as signed. Six `MUL` and `MULSU` partial products
produce the low 32 bits. Terms above bit 31 drop out, and the carry chain
extends the signed partial product into the high result byte where needed.
The routine restores the AVR GCC zero register `r1` before returning.

Above the direct-branch threshold, retain the original two floors. For a
negative coefficient with a nonzero low nibble, increment the high part
and subtract 16 from the remainder to obtain the original division
toward zero. The polynomial's maximum coefficient magnitude before the
last factor is 516,096. The high part after dividing by 16 fits signed16,
so the existing hardware multiply suffices. The smaller SRAM512 loop
also reuses the ring coefficient that becomes the next multiply operand.
This is original assembly for AVR5 with the AVR GCC ABI. The hardware
route requires `LPX4_ENABLE_ASM=1` on a supported target. The ordinary C
and standard-memory paths retain their original implementations.

## Matched playback

Baseline `ddefa0c4` and candidate use AVR-GCC 7.3.0 with `-Os -flto`,
LPC2, SRAM512, a queue of 32 bytes and a prefill of 24. Both run at 16 MHz
and 8 kHz in simavr 1.6 with the complete 64-cycle C ISR. The reported
mean adds one complete IRQ to the active decoder CPU mean.

The six AVR5 ASM builds each save 40 bytes of full Flash. Program Flash
excluding embedded audio decreases from 5088–5089 to 5048–5049 bytes.
The linked ASM images no longer call `__mulsi3`. The combined mean
falls by 7.64–8.49 cycles per sample, from 852.14 to 843.65 on the heaviest
case. The peak stack drops from 71 to 66 bytes. All 74,293 PWM samples
match the baseline and the C reference, without underruns. The IRQ
observer checks that `r0` and `r1` are restored across every interrupt.

The four shared controls cover P4, P6 and sparse80. Two additional
16,000-sample controls use ordered boundary clusters in dense and
sparse80 streams. Each executes the split path 150 times. The direct
arithmetic probe compares both paths under Timer0 IRQ against the C
product and the original separate floors. All 501,460 comparisons
match, including 194,306 split cases, and `r1` is zero after each call.
Four paired Mega C images are byte-identical to baseline. Eight Nano
speech images and the dialogue match their shipped binaries. Nine
fixed-header Tiny88 images match the corresponding rebuilds from the
prior revision. [Per-load measurements](measurements.json).

The direct replacement of the 32-bit library multiply increased Flash.
The selected bounded multiply, narrower split and reused ring operand
together provide the measured reduction.

## Reproduce the four shared controls

Use a fresh ignored directory from the repository root:

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/mega-lsf-wide --target mega --baseline ddefa0c4 --wsl Ubuntu
```

Omit `--wsl Ubuntu` on Linux. The boundary inputs use both streams from
`sparse_fixture(16000, 'clusters', 16383, 11468, 18)` in
`tests/test_speech_v9.py`, converted with `tools/speech_v9.py` to v9.
