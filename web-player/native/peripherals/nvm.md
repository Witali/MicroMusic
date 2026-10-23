# ATtiny13A nonvolatile memory controller

The independent C module owns EECR/EEDR/EEARL/SPMCSR and binds the CPU's
existing 1024-byte Flash and 64-byte EEPROM arrays. It allocates no memory,
calls no JavaScript, and advances programming and protection windows in O(1).
It is an integration module; adding these files does not wire it into avr.c.

Official references checked:

- [Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/ATtiny13A-Data-Sheet-DS40002307A.pdf),
  chapter 5, chapter 16, and chapter 17, especially Tables 5-1, 16-1, 17-2,
  17-3, 17-4 and 17-5.
- [Microchip AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/devicedoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
  sections 5.72 (LPM) and 5.112 (SPM).

## Integration contract

1. Call `nvm_init` with existing arrays, explicit timing and actual fuse/lock
   bytes. Init preserves both arrays. Factory fuses are 0x6a/0xff; high fuse
   bit 4 must be zero for SPM to change Flash. Firmware can read fuse/lock
   bytes without programming that fuse.
2. Dispatch owned I/O addresses through `nvm_read_io`/`nvm_write_io`; mirror
   reads into any shared register view used by generated IN/SBIC/SBIS code.
   Use mask 0xff for byte stores and a single-bit mask for SBI/CBI, which must
   not replay the strobes of other bits. Return values are additional CPU
   stall cycles, separate from the originating instruction: EERE=4, EEPE=2.
3. Pass both monotonic CPU cycle count and elapsed nanoseconds. The cycle
   count must not restart on an MCU reset; it tracks elapsed CPU clock edges.
   Programming time uses the calibrated RC oscillator independently of CPU
   division. Advance elapsed time while CPU clocks stop or sleep. Schedule
   the minimum of `nvm_next_event_cycle` and `nvm_next_event_ns`, converted
   into the scheduler's own time domain. UINT64_MAX means no pending event.
4. Call `nvm_lpm` before an ordinary Flash read. A result of 1 supplies the
   fuse/lock byte; 0 selects normal LPM; -1 diagnoses an unsupported fuse
   address. LPM's CPU register effects, Z increment, and three cycles belong
   to the CPU. Call `nvm_spm` at the SPM effect edge with Z and R1:R0.
5. For Flash ERASE/WRITE, immediately leave the translated CPU block. Advance
   timers and other devices while `nvm_cpu_halted` holds; perform completion
   through `nvm_advance`. Before fetching the next AVR instruction, check
   `flash_generation`, invalidate decoded opcodes/idle-loop recognition for
   dirty pages and retranslate the CPU module. Dirty bits identify 32-byte
   pages (bit 31 is bytes 992..1023). Generation changes at completion even
   if content is identical. It cannot be acknowledged by clearing dirty bits.
6. Route `nvm_ready_irq` into the interrupt arbiter as a level. Accepting the
   IRQ does not acknowledge or clear it. `nvm_reset` clears temporary page
   data and controls but allows an active program operation to complete,
   assuming adequate supply voltage. Its pending payload is separately held.

The module exposes EEPROM atomic/erase/write modes, EEPROM/Flash interlock,
page erase/load/write/clear, timed command expiry and fuse/lock LPM. Starting
EEPROM programming discards loaded Flash page data. Flash page erase retains
the temporary buffer; page write clears it. EEPROM address/mode writes are
blocked while programming. EEDR remains a software register; the controller
latches its original program payload at EEPE.

## Timing and unsupported behavior

`nvm_datasheet_timing(0)` selects the documented Flash minimum (3.7 ms),
`nvm_datasheet_timing(1)` its maximum (4.5 ms), separately per erase/write.
Both select EEPROM's published 3.4 ms atomic and 1.8 ms split-mode values.
Those EEPROM figures are not guaranteed timing bounds. Override the explicit
nanosecond parameters for a calibrated operating-condition model; this
module does not derive oscillator accuracy from VCC/temperature/OSCCAL.

The device instruction summary leaves SPM timing blank; the instruction
manual makes it device dependent. The module does not invent a fixed SPM
buffer-load, clear-buffer, or disabled-instruction cycle count. The CPU
integration must resolve these separately and must not charge page-program
latency twice.

Protection windows expire at the end edge: a write at cycle t arms [t,t+4)
for EEPE/SPM or [t,t+3) for fuse LPM. Use a consistent I/O effect edge.

Unsupported/undefined firmware sequences latch `faults`: reserved EEPROM
mode, write-only EEPROM on a non-erased byte, duplicate buffer-word load,
non-erased Flash page write, nonzero non-page Z bits for PGWRT, unsupported
fuse address, or reversed time. The CPU integration should stop and report
those conditions; no valid hardware result is claimed for them.

External ISP/high-voltage serial programming, wear, retention, power-failure
corruption and debugWIRE are outside this firmware controller. Lock bits
constrain external programmers on this chip; they are not invented as an
extra SPM protection mechanism. Fuses/lock are supplied configuration, not
firmware-writable registers. The controller has no automatic chip-erase API.

## Validation

Run from either the main checkout or a task worktree:

```powershell
node --test web-player/tests/nvm.test.mjs
```

The test driver locates the main checkout's bundled clang or uses EMSDK/CLANG,
compiles the controller and C assertions to ignored `build/nvm-tests/`, and
runs them in WASM. The module must have zero imports. Tests cover timed
boundaries, stalls, latched data, mode/address busy locks, SBI/CBI masks,
ready IRQ, independent programming time, long counters, Flash pages, dirty
generation, fuse gating, interlocks, undefined sequences and resets.
