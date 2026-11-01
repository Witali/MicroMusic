# Elide a mathematically zero component

Applicable here: ATmega328P / classic AVR5 with MUL, GNU ABI, AVR GCC 7.3.0,
mixed Os/O2/O3, LTO, mcall-prologues and mrelax. Benefit: execution speed;
138/144 B additional Flash and six extra NB stack bytes, unchanged WB stack.
Original project control-flow technique; retain Xiph BSD notices for the
existing codec arithmetic and codebooks.

For forced prediction with coefficient zero, all ancestry terms vanish even
with arbitrary signed16 history. Test the compact coefficient code before
expanding it if its complete finite mapping proves that only code zero maps
to zero. Keep innovation reconstruction, gain, state and original quantizers:

```c
if (coded_coefficient == 0) {
    /* Four subframes, two 20-word rows per subframe. */
    decode_all_zero_prediction_innovations(frame, packet, scale);
    return;
}
decode_original_nonzero_prediction(frame, packet, scale);
```

Zero prediction does not imply silent output. An amplitude threshold would
change quiet speech. Inspect the existing variable-count primitive before
adding a new loop: the same assembly body already handles a full 20-word row.
Prove the enlarged count domain, register ABI, address bounds and rounding bias
(4 here, unrelated to row length). Keep explicit C selection on AVR and use
ASM only with the supported CPU defines plus the separate enable define.

Measured on NB3.95/WB5.75: about thirty percent of natural speech frames take
the fast branch; speech CPU falls 32.00% -> 30.17% and 74.98% -> 73.19%.
Nonzero frames improve four cycles each. The arithmetic fixture is byte-identical
to the parent's and passes 37024 C/ASM/wide-reference cases, counts 0..20,
exact LPM addresses, null count-zero accesses and 42354 ABI returns. Full raw,
active-IRQ and timed SPI tests retain exact PCM/PWM with zero underruns.
No physical-board measurement or other-profile speedup is claimed.

[Production controller](../../Codecs/Speex/AVR/src/lowrate_excitation.h),
[shared ASM primitive](../../Codecs/Speex/AVR/src/innovation.S),
[explicit C fallback](../../Codecs/Speex/AVR/src/zero_innovation.h),
[bounds, complete measurements and reproduction](../../Codecs/Speex/AVR/WB_FORCED_ZERO.md).
