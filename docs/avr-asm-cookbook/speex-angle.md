# Exact bounded products in a stackless cosine leaf

Classic AVR5/ATmega328P, hardware MUL, GNU ABI, AVR GCC 7.3.0; measured at
`-Os -flto -mcall-prologues -mrelax`. Original project arithmetic derived from
Xiph Speex 1.2.1's fixed-point polynomial; its source and BSD notice remain
in `Codecs/Speex/AVR/vendor/`. Explicit C remains available on AVR and is the
default when architecture or ASM opt-in does not match.

- A signed16 square needs three partial products: high×high, low×low and
  twice signed-high×unsigned-low. Double the cross product in **17 bits**;
  discarding its extra sign/carry bit breaks large and negative inputs.
- For `P13(a,b)=floor((a*b+4096)/8192)`, a proven integral offset can enter
  the bias before division. Preserve every original floor and narrowing cast.
  In this cosine, `340+P13(-10,y)` is always 300..380. Its high byte is 1,
  allowing `y*(256+a_low)` to use two MULs plus signed `y<<8`.
- Keep only the result bits the caller consumes. In the final word,
  `P13(a,b)<<2` equals `((a*b+4096)>>11)&~3`, modulo16. Omitting that mask
  silently changes quantization. Full signed32 intermediates remain bounded.
- Allocate operands within the instruction's actual register subset:
  MULSU accepts r16..23, not every high register. Its C flag carries the
  product's sign bit; see [Microchip DS40002198C (2024), 6.79](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/ReferenceManuals/AVR-InstructionSet-Manual-DS40002198.pdf#page=92).
- A pure leaf can use call-clobbered registers and avoid a save frame. T may
  hold a private branch flag and r1 a MUL result until RET; make no C call
  while r1 is dirty, clear it at the ABI boundary, and require IRQ context
  preservation of SREG/T and r1. No explicit data-memory or hardware IO is used.

The [assembled leaf](../../Codecs/Speex/AVR/src/lsp_angle.S) and
[explicit C implementation](../../Codecs/Speex/AVR/src/nb3_lsp_angle.h) are the
reusable examples. All 65,536 signed16 inputs match untouched Xiph and BigInt
on selected/forced-C paths; native default/unavailable/unknown selectors also
match. A real compiled ISR preempts 1,533 instruction boundaries, including
737 with nonzero r1. The leaf takes 123/131 cycles and zero own stack bytes.

Whole NB8 improves 102,239.323 → 99,126.806 cycles (-3.0443%), Flash
11,064 → 10,638 B. WB12.8 improves 2.3730%, Flash 20,380 → 19,948 B.
Whole-decoder/player peak stack and static SRAM do not fall: another stage
sets the peak. All 198 fresh ASM PWM images pass active IRQ with no underruns;
both WB modes also pass all 16 voices with 8% extra foreground work. Two
RAM-input test images additionally pass all 10,563 full-history frames per
WB mode with that load and production ISR/queue; input is assumed ready. These
are measured corpus/ISA results, not board or arbitrary-ISR guarantees.
[Bounds, source hashes, workloads and reproduction](../../Codecs/Speex/AVR/EXACT_ANGLE.md).

The shorter `COM high; NEG low; SBCI high,255` word negate is now used in
the reflected cosine path too. It saves one cycle there, retaining all 65,536
exact signed16 results and 1,533 IRQ checks; primitive times are now 123/130
cycles. [The combined grouped-IIR admission](../../Codecs/Speex/AVR/IIR_GROUPS.md)
records current sources, full PCM and active-PWM evidence. The earlier
123/131-cycle measurements above describe the preceding cosine stage.
