# Preserve CPU requests across an SPM/IRQ continuation

Full ATtiny13A manual `step` and instruction-counted `run` now finish a suspended
IRQ, bind changed Flash, and then perform the requested CPU instructions.
Previously they could complete only the IRQ and rebind: `run(1)` returned0,
with PC at the vector and no instruction retired. This follows the
[manual-clock SPM repair](spm-entrypoints-20261026.md); its pre-fetch guard must
still defer replacement while an IRQ continuation is active.

`run` now accumulates completed instructions and retries the remaining limit
only after a successful Flash rebind. `step` checks the native unsigned64-bit
retirement counter and retries after rebinding only when it did not advance.
A halted CPU without a code change still returns normally. Held RESET and
zero-count requests do not acquire artificial time or instruction execution.
Timed/audio loops and native C/WASM are unchanged; no hot instruction or edge
starts calling JavaScript.

The regression starts a real firmware SPM erase while Timer0 counts with its
overflow interrupt enabled. A bounded physical call stops1ps into IRQ entry
after erase completes, or1ps after the existing C2/C3 stack phases. Native
Flash generation is1, while the adapter remains bound to0 until the IRQ ends.
Both compilation policies reproduce the problem.

After the fix, one step executes the vector's RJMP to word64. `run(2)` also
executes the ISR's INC. Retirement increases by exactly1/2, one IRQ is recorded,
and the two return-address bytes are pushed only once. Remaining IRQ clocks
plus RJMP/INC costs are exact. All pause points finish at4.506/4.507ms in the
declared1MHz fixture, retaining the source phase across the1ps observation.
If firmware erases the vector itself, the same API call faults at byte0x6
immediately after rebinding; it does not silently stop or execute stale code.

The test also preserves zero-count state and RESET cancellation. These checks
use the existing digital C2/C3 convention and explicit4.5ms Flash profile;
they do not establish silicon stack phases or oscillator calibration.
Manufacturer register/vector/memory definitions come from the pinned DFP.
External ISP/HVSP/programmer support remains excluded.

[The evidence record](spm-irq-resume-20261026.json) pins baseline04699008,
its JS/native sources, the regression source and compiler identity. The identical
28 cases fail22/pass6 on the baseline and pass all28 on the repaired adapter.
All2000 default/shared-tool tests pass, no failures or skips. The native binary
remains119010bytes, SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`.
No speed or hardware-measurement claim follows. Plan status remains23/30,
seven open.

```text
node --test web-player/tests/attiny13a-spm-irq-resume.test.mjs
node --test web-player/tests/*.test.mjs tools/music-startup.test.mjs tools/avr-music-target-core.test.mjs
node web-player/scripts/generate-avr-cache-identity.mjs --check
```

The focused test accepts `MICROMUSIC_DEVICE_MODULE` as an absolute path to a
separate loader for baseline replay; keep its matching JS files and native WASM
together. The recorded baseline was reconstructed from Git in an ignored build
directory, without replacing the active checkout or changing its environment.
Official basis: [ATtiny13A DS40002307A, sections4.7.1/9/16](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
and [AVR instruction-set manual, RJMP/INC](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf).
