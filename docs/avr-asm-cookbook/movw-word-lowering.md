# Lower AVR MOVW to a WASM word copy

Applicable targets: the existing ATtiny13A and ATtiny88 AVR-to-WASM emitters,
with their current register-memory ABI. MOVW is available on these devices;
this does not add it to AVR cores that lack the instruction. No C compiler,
WAT assembler, SIMD extension, extra runtime import or native rebuild is needed.

Microchip [DS40002198A, section 5.76, pp. 97–98](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
specifies an unchanged source pair, a copied destination pair, unchanged SREG,
one word and one AVRe cycle. Both pairs start at an even register from r0 to
r30. The [ATtiny13A data sheet DS40002307A, p. 167](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
also lists MOVW with no flag changes and one cycle. These two pinned original
PDFs were already registered in the project download manifest.

The [official WebAssembly binary specification](https://webassembly.github.io/spec/core/binary/instructions.html#memory-instructions)
assigns `0x2f` to `i32.load16_u` and `0x3b` to `i32.store16`. Their
[execution semantics](https://webassembly.github.io/spec/core/exec/instructions.html#memory-instructions)
use the defined byte order, zero-extend the loaded word and store the low 16
bits. The alignment immediate is a hint; this ordinary access does not require
an actually aligned address. The emitted MVP memory argument is `01 00`
(alignment exponent 1, offset 0), with the existing default memory.

For example, `MOVW r19:r18,r17:r16` becomes the equivalent of:

```wat
i32.const DATA_PLUS_18
i32.const DATA_PLUS_16
i32.load16_u align=2
i32.store16 align=2
```

The constants above stand for the existing shared-memory register addresses.
The previous lowering emitted two byte loads and two byte stores; the new
lowering emits one word load and one word store. Low/high register order is
preserved because the two-byte representation has the same ordering. Legal
register pairs either coincide or do not overlap. Both accessed bytes remain
within the 32-byte GPR file, including the r31:r30 pair; no I/O register or
memory-mapped side effect is involved.

Keep the original two-local lowering inside a bounded region that caches
registers in WASM locals. Reading raw memory there would bypass earlier local
updates, and writing raw memory would bypass its exit publication. The block
local-remapping parser must also recognize both new memory opcodes and retain
their immediate bytes.

The optimization changes only the copy at its existing ALU boundary. Individual
resumable MOVW executes its clock first and then reads its register source;
public edits during suspension must therefore remain visible after continuation.
It must not move the copy across a clock, reset, interrupt or public-state exit.
SREG, exact cycles, retirement, cached-region behavior and source/destination
sentinels are correctness constraints, not optional performance tradeoffs.

The [focused tests](../../web-player/tests/avr-movw-lowering.test.mjs) exercise
all 256 legal source/destination pairs with independent expected register bytes,
including identical pairs and high/low patterns. The
[historical-module verifier](../../web-player/scripts/verify-movw-lowering.mjs)
loads the actual pre-change compiler from Git, verifies unchanged dependencies
and native bytes, and compares emitted catalog artifacts plus full CPU/device,
PCM and physical pin observations on identical spans with active IRQs.

See the [retained integration report](../../web-player/reports/movw-lowering-20261027.md)
for measured emitted sizes and completed checks. The benefit concerns bytecode
size and memory-operation count. Execution speed, hardware behavior and real-time
audio admission are not inferred from the smaller instruction sequence.

## ADIW/SBIW register-pair arithmetic

The same uncached word access now applies to ADIW/SBIW on the supported
ATtiny13A/ATtiny88 emitters. Microchip DS40002198A sections5.3/5.98 specify
pairs starting at r24/r26/r28/r30, immediates 0..63, two AVRe cycles, updated
S/V/N/Z/C and preserved I/T/H. Retain the existing flag equations, masks,
16-bit wrap and phase boundaries; only pair loading/storing changes.

The ordinary path uses one unsigned `i32.load16_u` and one `i32.store16`,
replacing two byte loads, their shift/OR and two byte stores. Both bytes stay
inside the GPR file. Odd ABI bases are valid with the ordinary alignment hint.
Register-cached regions keep their current byte locals, so earlier local
updates and exit publication remain intact. Individual resumable arithmetic
still reads operands at retirement, after its two-cycle clock barrier; public
pair edits during a pause remain visible and untouched SREG bits retain their
current values. RESET cancels the word store, and a tied IRQ sees its result.

The [arithmetic tests](../../web-player/tests/avr-word-lowering.test.mjs) cover
all 512 encodings, every retained I/T/H pattern, carry/sign boundaries, dead
flags, cached/uncached paths, partial execution and held/unequal CLKI.
The existing independent oracle also checks every 16-bit value and all 64
immediates. A [historical comparison](../../web-player/scripts/verify-word-lowering.mjs)
checks 48 catalog/policy artifacts and eight active-IRQ music cases. Twenty
modules shrink by 23–184 bytes; all register-cached region bodies and unaffected
functions remain byte-identical. Native WASM/ABI are unchanged. This reduces
bytecode size and GPR memory operations, without a measured speed claim.
See the [evidence](../../web-player/reports/word-lowering-20261101.md).
