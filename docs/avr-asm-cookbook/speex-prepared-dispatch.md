# Tail-dispatch before a shared AVR prologue

Target: ATmega328P / classic AVR5, GNU ABI, AVR GCC 7.3.0, existing Os/O2/O3,
LTO, mcall-prologues and mrelax. Benefit: measured speed and Flash, unchanged
working RAM. Original project code; existing Xiph synthesis provenance remains.

When one prepared context selects between two existing ABI-compatible bodies,
pass the original arguments once and select beside their common prologue:

```asm
; Context is r20:r21; its original value survives this selection.
movw r30,r20
ldd r0,Z+(2*SPEEX_NB1_PREVIOUS)
ldd r31,Z+(2*SPEEX_NB1_PREVIOUS+1) ; final read; ZH becomes scratch
or r0,r31
breq zero_entry
; fall through to the general entry; both share setup/cleanup
```

This final LDD can reuse ZH because it has no pointer auto-update and Z is dead
until reloaded by common setup. Preserve the original pointer elsewhere, every
argument, callee-saved registers and r1. Do not substitute LD r31,Z+ or LD r31,-Z:
those aliases are undefined. The [Microchip AVR Instruction Set Manual,
DS40002198C (2024), section 6.68, printed pages 82–83](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/ReferenceManuals/AVR-InstructionSet-Manual-DS40002198.pdf#page=82)
defines the displacement form and restricted auto-update combinations. Do not
assume its availability/timing on a different AVR core. No vendor code is copied.

The predicate applies only to the producer's proven prepared contexts. Retain
the arbitrary-table general entry and an explicitly selectable equivalent C
dispatcher. Assembly still requires real supported architecture macros plus
separate explicit enablement; hardware memory selection remains independent.

Measured complete WB3.95 caller: all 10627 frames save 52 or 60 cycles, natural-
speech CPU 69.222% ->69.205%, 18 B less Flash, static/peak RAM unchanged. Both +8/+11%
IRQ runs and scheduled SPI retain exact PCM/PWM and no underruns. All 65536
predicate words and 98791 vectors/backend check tail selection, exact outputs,
read-only inputs, stack depth and GNU ABI. Full C controls are byte-identical
and compile/link only; isolated C vector/dispatch controls execute.

[Implementation](../../Codecs/Speex/AVR/src/nb1_vocoder.S),
[portable C selection](../../Codecs/Speex/AVR/src/nb1_vocoder.h),
[complete scope and reproduction](../../Codecs/Speex/AVR/WB_PREPARED_DISPATCH.md).
Evidence is ISA simulation, not board measurements or cross-architecture timing.
