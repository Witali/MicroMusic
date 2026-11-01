# ATtiny13A: preflight indirect SRAM spans before batching CPU phases

An explicitly selected `sramBlocks:true` compiler option combines consecutive
LD/ST instructions into a resumable memory-only block. It requires
`resumable:true`, defaults to false, and is disabled by the verification
configuration. This is a generated-WASM optimization for the full ATtiny13A
runtime, not a change to firmware or AVR assembly arithmetic backends.

## Semantics and lowering

The primary references are Microchip's
[DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
sections 5.66–68 and 5.114–16, and the ATtiny13A
[DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
instruction summary and data-memory map. Internal SRAM LD/ST takes two CPU
cycles and preserves SREG. ATtiny13A uses only the low pointer byte. Undefined
auto-update aliases must keep the original instruction fault path. Addresses
come from the manufacturer-derived device profile, not a second register map.

The generated module uses WebAssembly MVP byte operations:
`i32.load8_u` (0x2d), `i32.store8` (0x3a), integer address arithmetic and the
existing native WASM phase bridge. The
[official binary instruction specification](https://webassembly.github.io/spec/core/binary/instructions.html)
defines their encoding. Register bytes and SRAM share the runtime's linear
memory; no JavaScript callback is introduced.

For example, five `LD Rd,X+` instructions keep five ordered byte loads,
destination writes and low-X increments, but can replace their individual
clock phases with one ten-cycle native call. SRAM effects are published only
after that complete span. SREG needs no working copy or writeback.

## Proof required before entering the span

For each pointer, accumulate its pre-decrement/post-increment delta and the
minimum/maximum effective offsets across the entire span. At entry require:

```text
RAMSTART - minimumOffset <= initialPointer <= RAMEND - maximumOffset
```

These unmasked bounds deliberately reject wrapping candidates. No register,
SRAM byte or clock changes on rejection. Every accepted access is ordinary
SRAM; register-file and I/O aliases keep their original bus phases. Loads into
any pointer register are excluded, as are auto-update source/destination
aliases. Other register dependencies execute in original order. ALU, LPM and
two-word LDS/STS instructions never join these spans. Branch/skip targets split
blocks, and the existing instruction table remains callable at every PC.

The existing strict physical/deadline, IRQ/delay, active-continuation, cycle and
uint64 retirement guards still apply. CLKI continues to supply zero block
budget. A rejected span uses individual generated instructions; a reset/fault
after clock entry must never replay a prefix through that fallback. Host edits
at a partial instruction remain visible through its original continuation.

## Measured scope, 2026-11-01

The untimed census samples 50,000 retired instructions per firmware, with 588
paired full-state/pin checkpoints. Rhythmic and Lumière execute 5,291/5,892
memory instructions, dominated by indirect loads; neither executes LDS/STS.
The HQ4 Tiny prefix executes 292 direct SRAM accesses out of 295 memory
instructions. This motivates indirect spans, not a general memory speed claim.

Two serial four-label Williams series contain 192 timed captures and 96 equal
warmups, with fresh chips and one unchanged native runtime. At 12,000 frames,
48 kHz, Node 22.22.3/V8 12.4 on the recorded host, median baseline/candidate ratios
are 1.165x/1.126x for Rhythmic and 1.134x/1.229x for Lumière; 30 of their 32
trial pairs favor the candidate. HQ4 ratios 0.976x/1.011x establish no benefit.
Identity controls are noisy, so exact percentages are not guaranteed.

The generated code sections grow by 1,347/1,802/1,257 bytes respectively;
complete modules grow by 1,680/2,241/1,591 bytes. Native memory, imports, ABI and
both distributed WASM files are unchanged. These results concern host execution
speed, with no working-memory saving or browser real-time/underrun claim.

All 2706 default tests pass, including 33 new SRAM cases. Actual native phase
traces prove combined calls from both public runners. Tests cover all pointer
byte values, full SRAM endpoints, every SREG value, compiler-option combinations,
dependency/fault fallbacks, partial host edits, physical ties, IRQ/reset,
protected windows, both held CLKI levels, counters, caches, packages and actual
SPM with monolithic/incremental recompilation. Thirteen baseline/candidate
workloads retain exact state, PCM and observed pins; 48 catalog/policy modules
keep their historical default bytes. Six further active-IRQ audio comparisons
retain 4,936,786 exact pin events including every external CLKI transition.
This closes no hardware measurement item.

See the [full report and reproducible commands](../../web-player/reports/sram-blocks-20261101.md),
[raw census](../../web-player/reports/sram-instruction-trace-20261101.json), and
[tests](../../web-player/tests/attiny13a-sram-blocks.test.mjs).
