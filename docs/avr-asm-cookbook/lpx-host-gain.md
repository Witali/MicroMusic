# Move gain proposals off the audio CPU

Original project technique, measured with LPX Q0 on classic AVR5/ATmega328P,
GNU AVR ABI, AVR-GCC 7.3.0 `-Os`, hardware MUL. Applicable to an offline encoder
whose existing stream already carries excitation scales. No ISA instruction,
ASM routine or per-sample gain operation is added.

1. Analyze a quiet PCM16 input with the largest safe binary headroom shift.
2. Propose the inverse scale using existing bitstream fields.
3. Decode at the original level through the real fixed-point backend. Filter
   rounding, limit cycles and clipping mean this is not a linear identity.
4. Refine at that level, retaining the byte cap and an explicit failure result.
   Do not let a high intelligibility score of a biased proposal block a much
   better waveform reconstruction. Verify quiet activity separately.

The benefit is moving search work and gain management to the host, with no
extra MCU RAM or per-sample multiplication. It is **not** a measured decoder
speedup. For one 8 s Russian male stream at an unchanged 8 kbit/s cap, actual
payload increased 4.563 to 7.981 kbit/s; SER rose 0.6464 to 11.9133 dB.
The resulting AVR ASM player passes all 64,000 useful PWM samples with active
IRQs and zero underruns (512-byte queue, 384 prefill). The unchanged selectable
C path matches PCM but misses the real-time deadline on this AVR. These are
simulator results; they do not establish analog quiet-audio quality.

[Implementation, negative experiments, source licenses and workload](../../Codecs/LPX/research/quiet-speech-2026-10-26/README.md).
Keep hardware memory access and arithmetic backend selection separate.
