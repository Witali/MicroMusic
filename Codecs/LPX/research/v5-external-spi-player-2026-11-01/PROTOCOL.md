# External SPI player: finite full-length validation

This isolated stage uses optional sequential input and the existing arithmetic
backends. It changes no frozen matched-CPU source, old decoder protocol, default
ROM player, prior proof or corpus selection. It performs no fitting/refinement,
cap search, audio trimming or subjective adoption. The earlier target A/B result
remains inconclusive.

## Exact prospective work

Consume the final 248-arm / 312-helper / 744-cap-view matched-search study and
its exact 104 common canonical100 baselines. Select only the full long nonspeech
source context already fixed by that study, profiles 4 and 6. Include both common
baselines and every changed automatically selected full ordered tuple. Verify
each final automatic decision, original declared-level/reference provenance,
ordered bytes, segment profile/offset/length and complete samples. Deduplicate
actual byte tuples, preserving all arm/tier/cap contexts. No new search occurs.

The accepted finite set is six long chains: two common baselines and four
changed selections, three chains per profile. Each preserves 60 resets and
3,786,111 samples. Stored data ranges from 202,600 to 299,058 B. Each chain has
normal and +100-cycle IRQ ASM images: 12 long rows and 45,433,332 physical samples.
No full long AVR-C real-time run is required or implied.

Construct one deterministic 160-sample synthetic stream per profile without
fitting. For each, explicitly select C and ASM arithmetic at both IRQ loads:
eight bounded SPI rows. Since all samples fit in the initial prefill, these
check AVR C/ASM build and output parity without asserting sustainable C 8 kHz.
Build and validate eight matched short ROM controls under the same backend/IRQ
flags for exact linked program-cost comparison. Total: exactly 28 image rows.
No extra per-cap image, retry, alternative profile or quality-driven expansion
is permitted. Preserve failed or incomplete attempts and actual process handles.

## Source, storage and timing

Bind callback source 8854d2ce by actual source bytes, irrespective of the
cherry-pick commit ID. The callback is an explicit input opt-in; arithmetic ASM
enable remains separate. Parent verification established 199 current tests,
including eight input checks, and five historical prototype checks against the
unchanged frozen source separately. Four callback-disabled AVR objects matched
the frozen default bytes, common/v5-only times C/ASM. The frozen-source guard
remains enforced; a changed-source historical prototype was correctly rejected.

The codec-independent reader owns ATmega328P SPI and CS exclusively in the
foreground. Use vendor avr/io.h register/pin macros, Mode 0, MSB first, F_CPU/2,
16 MHz CPU / 8 MHz SPI. Every seek sends 0x0b, 24 address bits and one dummy byte.
Offsets and bounded reader lengths are 32 bit. Only segment offsets/uint16 sizes
remain in PROGMEM; all encoded audio is in an immutable exact 16 MiB external
file, beginning above 64 KiB to exercise actual three-byte addressing.

Use the audited read-only QEMU-derived W25Q128 model; keep its input image
constant and require unsupported_commands==0. The model advances only on a
completed emulated SPI byte. The original simavr1.6 module's fixed 100 us delay
is unsuitable here. A separate source-pinned correction schedules 8*divisor CPU
cycles from actual SPR/SPI2X bits and explicitly replaces only the existing
SPDR write handler. Preserve the IO list, IRQs, input/read handlers and installed
library. Its real NOP-cycle unit checks all eight divisors and 48 protocol bytes;
the fastest byte completes after 16 cycles. Instruction dispatch lateness and
foreground/IRQ software gaps are observed separately, never treated as zero.

The observer's 64-bit limit is based on full expected samples, not the old
2-billion-cycle short-run limit. Long runs may execute as independent isolated
processes, at most four concurrently, after bounded parity and immutable gates.
Use sorted complete-chain index modulo four, retaining both IRQ loads together:
the four workers own 4, 4, 2 and 2 rows. Aggregate the identical fixed 12-row set.
Report the first observed runtime. Do not restart an unobserved live process.

## Acceptance and costs

Verify model, common/v5-only native ROM and callback PCM16/PWM for the exact
ordered streams. Derive the expected number of callback-requested bytes per
reset independently. A valid final partial-frame packet may leave stored bytes
unread. Do not force them through SPI: close and explicitly seek the next reset.

Every admitted image must match every physical PWM byte, full sample count,
produced/played totals, timer ticks/events, EOF, decoder error zero, final queue
empty, timing bounds, stack and zero underruns. An observer exit alone is
insufficient. Check SPI completed/started bytes, 16 scheduled cycles per byte,
bounded dispatch lateness, actual software gaps and active interrupts. Command,
address, dummy and CS-edge counts must respectively equal resets, 3*resets,
resets and one assertion/deassertion per reset. Payload must equal independently
observed callback requests, which can be below stored bytes.

Charge actual linked .text+.data, all driver/header/segment metadata and static
SRAM; report stack margin. External bytes and 16 MiB image capacity are separate
from program Flash. Compare exact matched short ROM/SPI program costs. Full long
ROM embedding is device no-fit; its unavailable linked program size is never
replaced with an invented universal constant or a claimed full firmware saving.

Reopen all image/source/compiler/header/runtime/model/output proofs after the
terminal workers. Commit only source-bound anonymous measurements after staged
privacy inspection. Input/source identities, media and encoded data, external
images, target/PCM/stream/firmware fingerprints, generated files and logs stay
private under ignored build storage. No push, physical-board/electrical timing
claim or larger-format/trajectory production adoption is part of this stage.
