# LPX: learned-period excitation pilot

This is a measured **host algorithm experiment**, not an AVR optimization or
real-time admission. The active ATmega328P / AVR5 C/ASM code, CPU/ABI/toolchain
settings and Flash memory access remain unchanged.

Tiny Period models output waveforms. Before reusing its idea ahead of an LPC
filter, learn inverse-filtered excitation periods or explicitly design a
separate output path. Preserve phase continuity, nonperiodic consonants and
actual mixed prediction history. Count dictionary, phase, mode and fallback
bits; moving a dictionary to EEPROM does not make its information free.

In the bounded 12-case pilot, no learned-period gain survived existing achieved
v5 bytes and full-reference PCM/PWM quality floors. A silence-only control
explained the sole same-size selection win. One distinct learned result cost
2010 additional bytes for a small metric improvement. Existing LPX adaptive
pitch history already reuses earlier excitation, so a static book adds overhead.

Useful controls are a zero/noise ablation, complete serialized decoding without
analysis inputs, full-length comparisons, an eligible baseline and explicit
host-versus-hardware status. New firmware would need separate C/ASM parity,
complete Flash/SRAM accounting and active-interrupt timing before admission.

[Prototype, original primary references, anonymous results and limitations](../../Codecs/LPX/research/period-excitation-2026-10-27/README.md).
