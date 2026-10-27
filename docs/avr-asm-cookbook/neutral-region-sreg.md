# Omit an unused working SREG copy in bounded WASM regions

Applies to the full ATtiny13A AVR-to-WASM emitter, its resumable ABI and optional
`boundedRegions:true` policy. The generated module uses MVP WASM; the native
peripheral runtime and portable C arithmetic are unchanged. This is an emitter
memory-traffic/code-size improvement, not handwritten AVR assembly.

A bounded register-only region already checks pending interrupts and proves
that its selected execution budget ends before the next observable event.
It previously also loaded a working SREG copy and stored it back even when no
region instruction consumed or changed a flag. Compute this dependency once
when emitting the region. Omit the working copy only if every node is independent
of SREG; direct internal emitter callers retain the conservative default.

For the recorded native ABI, the omitted fragments are:

```wat
i32.const 51487
i32.load8_u
local.set 7
;; region body
i32.const 51487
local.get 7
i32.store8
```

The initial SREG.I read remains: an otherwise flag-neutral region must still
decline when an enabled IRQ is pending. BRxx and BLD consume flags and retain
the complete working copy, as does every flag writer. The eligible instruction
set is NOP/LDI/MOV/MOVW/SWAP, RJMP, CPSE and register-bit SBRC/SBRS.

The flag contract comes from the pinned
[Microchip AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
and [ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf).
The existing official instruction-mask audit supplies the write masks;
`needsFlagSnapshot` additionally accounts for flag reads. A zero write mask
alone is insufficient to select this optimization.

Keep the region's original entry guards, strict deadlines, cycle totals,
staged GPR effects, native clock call, cancellation, retirement and IRQ handling.
Read public register edits again on the next entry. Reuse incremental region
bodies only for unchanged instruction/control dependencies; SPM still invalidates
affected code. There is no new public option or host callback.

The focused suite executes all256 incoming SREG values under both local
policies, CPSE/SBRC/SBRS exits and two-word skips, public edits, pending/delayed
IRQ, continuations, adjacent physical deadlines and RESET. It compares actual
WASM bodies to the conservative emitter: the remaining bytes are identical.
Existing bounded-region checks additionally exercise clock-before-commit,
peripheral/CLKI boundaries, package re-entry and SPM invalidation.

Measured static results at this ABI: the synthetic neutral region body shrinks
722 to704 bytes, removing one SREG load and one store per accepted invocation.
Its full module shrinks18 bytes with either phase-local policy. Among36 catalog
artifacts, only `alicia` with bounded phase locals changes:296007 to295989 bytes;
the other35 artifacts are byte-identical. Address LEB encoding can change this
byte count under another ABI. This evidence does not establish a general speed
gain or a browser real-time profile. See the
[integration and measurement record](../../web-player/reports/neutral-regions-20261027.md).
