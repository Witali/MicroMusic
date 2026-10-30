# Constant CLR lowering, 2026-10-30

The generated CPU now lowers `EOR Rd,Rd` (AVR `CLR`) to a constant zero write
and the required constant SREG bits. All 48 measured catalog/policy modules
shrink **708–2237 bytes (0.177–1.424%)**. Execution speed was not measured.

Microchip DS40002198A section 5.39 specifies zero, Z=1, N/V/S=0 and unchanged
I/T/H/C in one AVRe cycle. The optimization stays at the original ALU boundary
and accepts the existing live flag mask. A mask of zero generates no flag work;
mask 2 supplies only chained Z. Resumable retirement still merges untouched
public SREG bits, and cached regions use their existing locals/dirty flush.
See the [proof and official sources](../../docs/avr-asm-cookbook/clr-constant-lowering.md).

The baseline is actual commit `d8bf2c99b26fea2b00cdfd8ba31f84422b6d732d`.
The verifier loads its compiler from Git, validates unchanged dependencies and
executes both CPU bytecodes through the same current runtime. The two firmware
catalogs supply 12 ATtiny13A images in four policies:

| Policy | Modules | Bytes saved per module |
| --- | ---: | ---: |
| Legacy generated CPU | 12 | 718–2237 |
| Full compatible device | 12 | 708–2209 |
| Resumable physical device | 12 | 708–2209 |
| Bounded regions and live phase locals | 12 | 708–2209 |

Every module validates; manifests, function counts and function bodies outside
CLR-containing instructions/blocks/regions are identical. This size result
does not establish execution, construction or compilation speed. Conservative
region-entry GPR preloads remain; the optimization removes operand reads/XOR
within the lowered operation. The compiler still translates every Flash word;
CLR encodings in data or unreachable words also contribute to module size.

Six matched audio spans cover `rhythmic`, `lumiere-stereo` and `alicia` in
compatible and physical policies. Each executes 4096 frames at 48 kHz and
compares 16 exact checkpoints: full CPU/device state, diagnostic slots,
GPR/SREG/SRAM, EEPROM, Flash, IRQ frames, PCM and physical pin events. Across
the six spans, each variant observes **11,986 IRQs and 26,426 pin events**.
Retained PCM/pin hashes and individual sizes are in the
[JSON evidence](clr-lowering-20261030.json).

**2659/2659 checks pass:** 2598 player tests and 61 shared music/startup tests.
The 17 new focused cases cover all 32 GPRs, all byte/SREG patterns, independent
expected flags, dead/partial/full flag masks, chained Z into CPC, cached-loop
dependencies and public entry edits, suspended SREG edits, tied Timer0 IRQ and
RESET cancellation. ATtiny88's shared generated CPU is covered by focused and
shared tests; the 48 catalog size measurements above are ATtiny13A workloads.
Before editing, the selected existing baseline set passed 346/346.

The native ATtiny13A runtime remains 124614 bytes, SHA-256
`b9a8fa14a971fd5f82f8175f978e9a0b1e03f31fc8612a6892d202d7f93635a1`.
The site native WASM is also unchanged. Compiler source identity is refreshed to
`d67d0e37d909695ee35f8a90059d825f68008e42ec1ac231302c7f0bf51fa46b`,
so persistent and incremental caches cannot reuse earlier emitted code under
the new compiler identity. No extra import or per-instruction JS callback is
introduced.

Reproduce from the repository root, with TAP files retained only under `build/`:

```powershell
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/*.test.mjs > build/clr-lowering-full.tap
node --test tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs > build/clr-lowering-shared.tap
node web-player/scripts/verify-clr-lowering.mjs --baseline d8bf2c99 --full-tap build/clr-lowering-full.tap --shared-tap build/clr-lowering-shared.tap --output build/clr-lowering-replay.json
```

The report pins source/catalog/native and TAP hashes. Source/catalog text hashes
normalize CRLF to LF; native and TAP hashes cover exact bytes. Original local TAP files
for this run are `build/clr-lowering-20261030/full.tap` and `shared.tap`.
No new external file was downloaded. No official simulator session, hardware
measurement or real-time admission is claimed. The broader register/helper
optimization and all unresolved hardware criteria remain open; **24/31** plan
items are complete, with seven open.
