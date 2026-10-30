# Fold AVR CLR into a constant WASM write

Applicable targets: the current ATtiny13A/ATtiny88 AVR-to-WASM emitter and its
shared-memory GPR ABI, including individual instructions, accepted blocks and
register-cached bounded regions. No AVR assembly backend, compiler, SIMD
extension or native runtime rebuild is required. This concerns generated WASM
size and operand traffic; execution-speed improvement has not been measured.

Microchip [DS40002198A, section 5.39, p. 59](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
defines `CLR Rd` as `EOR Rd,Rd`: write zero, set Z, clear N/V/S and preserve
I/T/H/C. The instruction occupies one word and takes one AVRe cycle. The
original PDF is already pinned in the download registry; this implementation
was written from its documented semantics, without copying vendor code.

The previous generic EOR lowering loaded the same GPR twice, computed XOR and
derived four flags from its result. Detecting identical decoded operands allows
the result write to become:

```wat
i32.const DATA_PLUS_RD
i32.const 0
i32.store8
```

The existing flag liveness pass supplies a mask of required written bits.
Materialize only those constant bits:

```text
workingSREG = (workingSREG & (255 ^ liveWriteMask)) | (liveWriteMask & 2)
```

An empty mask emits no flag calculation. A full CLR mask is `0x1e`; a following
chained-Z comparison can require only `0x02`. This does not make untouched flags
dead, eliminate the instruction's clock or alter SREG retirement. In resumable
execution the existing commit merges untouched bits from current public SREG,
including debugger edits during suspension. A tied IRQ sees the retired state;
RESET still cancels uncommitted effects. All pre-existing clock, PC, retirement
and helper boundaries remain intact.

The [official WASM binary specification](https://webassembly.github.io/spec/core/binary/instructions.html)
assigns `0x41` to `i32.const`, `0x3a` to `i32.store8`, `0x71` to `i32.and` and
`0x72` to `i32.or`. The emitter retains its MVP memory argument `00 00`.
[Memory semantics](https://webassembly.github.io/spec/core/exec/instructions.html#memory-instructions)
store the low eight bits. A bounded region instead writes its GPR local, using
the existing dirty-register publication; it must not bypass that local cache.
Region entry still preloads its conservative register union, so this change
does not claim elimination of those region-entry loads.

Measured against `d8bf2c99`, all 48 catalog/policy modules shrink by 708–2237
bytes (0.177–1.424% of complete modules). Unaffected function bodies and all
translation manifests remain identical. Six matched compatible/physical audio
runs preserve full state, PCM and pin events with active interrupts. These are
software comparisons; they do not prove silicon behavior, real-time admission
or faster execution. See the
[integration evidence](../../web-player/reports/clr-lowering-20261030.md).

Reproduce from the repository root:

```powershell
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/avr-clr-lowering.test.mjs
node web-player/scripts/verify-clr-lowering.mjs --baseline d8bf2c99 --output build/clr-lowering-replay.json
```

The verifier loads the actual historical compiler from Git and verifies that
native bytes and all other source-graph inputs are unchanged. It compares both
catalogs, restricts changed functions to CLR-containing instructions/blocks/
regions and exercises 4096 frames at 48 kHz for each of three firmwares in both
policies. Source/catalog hashes, module sizes and output hashes are retained
without machine-specific paths or raw profiling data.
