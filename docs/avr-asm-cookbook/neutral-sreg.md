# Omit SREG copies for flag-neutral AVR operations

Applies to the ATtiny13A and ATtiny88 register-only lowerings for NOP, LDI,
MOV, MOVW and SWAP. Microchip DS40002198A sections 5.69/5.75/5.76/5.81/5.121
mark every SREG bit unaffected. These operations also consume no flag bits.
This technique targets memory traffic and generated code size, without an
additional optimizer pass. It uses the existing device-profile/linear-memory
ABI; no new ISA extension, CPU ABI or handwritten assembly backend is needed.
The native C/WASM interpreter remains independently selectable.

Previously each individual body loaded SREG before its effects and restored it
at completion. For a paused one-cycle NOP:

```text
SREG = 0x12; runUntilPs(1);
SREG = 0x65; runUntilPs(1000000); // declared 1 MHz oscillator
old: 0x12; corrected: 0x65
```

The old restore overwrote public debugger edits, including an I-bit change
needed for a tied Timer0 interrupt. Omit both copies for these five operations.
Also omit the pair around a basic block containing only these operations.
Keep the resumable block's SREG.I read for its pending-IRQ guard. Mixed blocks,
flag consumers, memory/I/O operations and cyclic-region handling are unchanged.
Do not infer this property merely from an empty flag-write mask: BLD reads T.

This is separate from flag liveness elimination and also applies with
`optimizeFlags:false`. Preserve original clock barriers, reset cancellation,
PC, retirement and IRQ service. Private spill slots need not retain unused
SREG snapshots; externally visible architectural state remains canonical.

Measured static size evidence: nine retained catalog firmwares, four compiler
policies, Node 22.22.3/V8 12.4.254.21-node.56, baseline 23c4b7b2. All 36 generated
modules validate; savings are 1494–8671 bytes (0.39–2.94%). This is not an execution
speed or real-time audio improvement claim. The dedicated 26-case regression
fails 19 cases before and none after; it includes every SREG input against native
C on both supported core profiles, RESET and tied Timer0 IRQ observation.
Two catalog firmwares in both verification/optimized policies also preserve
4096 frames of PCM and physical pin timestamps exactly with interrupts active.
The complete 2026-case default/shared-tool suite passes.
See [the report](../../web-player/reports/neutral-sreg-20261026.md).

Official basis: [Microchip instruction manual](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
[WASM memory instructions](https://webassembly.github.io/spec/core/syntax/instructions.html#memory-instructions).
The implementation and fixture are original project code; no vendor source
was copied or modified. Existing vendor register definitions retain their
separate pinned provenance and license.

## Extend the rule to partial flag writes

The following checkpoint covers all 123 ATtiny13A summary forms. Retain a flag
snapshot only for operations that consume flags or compute new ones. An
individual resumable instruction commits `(current & ~mask) | (computed & mask)`;
no-write forms omit that store. Explicit OUT/STS/ST aliases remain bus writes.
For example, ADD preserves current I/T, INC also preserves H/C, and RETI sets
only I. BLD and BRxx preserve latched operands without restoring all flags.
Keep existing clock/RESET guards, SEI/RETI delay and safe-block boundaries.

All 123 write masks were independently extracted from the pinned official PDF;
296 regressions fail 243 cases before and none after. All 2322 default/shared
checks pass. The two firmware captures above retain identical PCM/pin timestamps
with active IRQs against baseline 47fe829b. Conservative modules grow 656/719
bytes for the extra merge; live-local modules shrink 3664/3547 bytes in these
two workloads. This is a correctness repair with static-size observations,
without a measured speedup. Earlier size numbers above describe the preceding
five-operation checkpoint. The native C/WASM fallback is unchanged.
See [the full audit and evidence](../../web-player/reports/sreg-retirement-20261026.md).

## Rejected follow-up: omit no-input flag snapshots

With masked retirement, an ALU temporary can contain only written bits. The
candidate removes the old-bit preservation expression and an initial SREG read
from no-input writers; it preserves C/Z/T/branch inputs and SET's existing
diagnostic dependency. Apply only to individual resumable bodies: complete
flags still matter inside blocks/regions and in the compatible emitter.

On the same ATtiny13A linear-memory ABI, Node 22.22.3/V8 12.4, all 2325 candidate
checks pass and PCM/pins remain exact with IRQs active. Nine catalog firmwares
in four policies validate: 18 compatible artifacts are identical, while 18
resumable artifacts shrink 0.469–3.138%. However, two balanced actual/identity
screens on Ryzen 5 5600X establish no execution gain: all eight case medians
are below one, with possible slowdowns and substantial variance. Production
and its compiler identity are restored exactly to b8c34de4.

This is retained experimental evidence, not an available optimization or a
new supported performance profile. [Report, patch and isolated replay](../../web-player/reports/sreg-inputs-20261026.md).
