# Full-length external SPI player results

All 28 predeclared case/configuration rows passed. Six full long chains, each
3,786,111 samples with 60 resets, played through hardware SPI in the ATmega328P
model with normal and +100-cycle audio IRQ loads. The 12 long rows verified
45,433,332 physical PWM samples with zero underruns. This is simulator evidence;
physical-board timing and electrical behavior remain unverified.

## Complete MCU cost

| Workload/backend | Program Flash, normal / +100 IRQ | Static SRAM | Segment metadata |
| --- | ---: | ---: | ---: |
| Full long SPI, ASM | 5,308 / 5,316 B | 764 B | 360 B |
| Matched short SPI, ASM | 4,954 / 4,962 B | 764 B | 6 B |
| Matched short ROM, ASM, excluding encoded data | 4,573 / 4,581 B | 756 B | Included |
| Matched short SPI, C | 5,128 / 5,136 B | 764 B | 6 B |
| Matched short ROM, C, excluding encoded data | 4,745 / 4,753 B | 756 B | Included |

These are actual linked `.text + .data` costs. Exact matched short controls
measure +381 B of MCU program Flash for ASM and +383 B for C, with +8 B static
SRAM. Both profiles give the same program deltas. The full long program includes
all reader/callback code and 60 offset/size entries; its larger metadata table
adds 354 B relative to the one-reset SPI controls.

Full long encoded streams occupy 202,600–299,058 B in separate 16 MiB external
images. They exceed the MCU's internal Flash capacity on data alone. No linked
long-ROM image or universal subtraction is invented. External capacity, stored
data and program Flash are separate quantities. The minimum observed stack
margin was 1,223 B across long rows and 1,220 B across all rows.

Builds used AVR GCC 7.3.0 / avr-libc 2.0.0, `-mmcu=atmega328p -Os
-std=gnu++11 -flto -mcall-prologues -mrelax -fno-exceptions -fno-rtti`, compact-only
speech, dot unroll 1, function tuning 0, queue 256 and prefill 192. Callback input
and arithmetic backend are separately explicit defines. The bound builder
retains the complete compiler/link recipe and vendor-header inventory.

## Output, source and timing checks

The fixed scope was 12 long SPI ASM, eight bounded SPI C/ASM and eight matched
short ROM configurations. All 28 builds and simulations ran once; their outputs
contained 22 distinct ELF/program byte contents. The aggregate checked
45,435,892 physical samples in total, exact produced/played counts, EOF, decoder
error zero, empty final queue, timer/tick bounds, stack and zero underruns.
The 160-sample C cases fit within prefill and establish explicit AVR C output
parity, without establishing sustainable C playback at 8 kHz.

Native preparation independently compared model, common/v5-only ROM and callback
PCM/PWM domains for 130 unique reset streams. All 520 callback prefix-cutoff
checks retained identical output. Final partial-frame packets may leave valid
stored tails unread: long requested payload totals were 201,990–298,131 B.
The images retain every stored byte, and each reset explicitly closes/seeks its
own complete span. The observer checked payload against those native counts,
one command/dummy/assert/deassert per reset, three address bytes per reset and
zero unsupported commands.

At a 16 MHz CPU, Mode 0 hardware SPI schedules each byte for 16 CPU cycles
(8 MHz). All eight divisor unit checks passed before target jobs. Long runs
observed at most two cycles of instruction-boundary dispatch lateness, within
the prospectively fixed four-cycle bound; 4,849 completions occurred during the
audio ISR. The maximum measured foreground/IRQ gap between transfers was
80,372 cycles, reported separately from hardware byte duration. Long simulation
wall times ranged from 230.44 to 352.36 seconds per row.

The isolated simavr1.6 correction replaces its fixed 100 us SPI delay with the
actual divisor-derived delay; installed libraries and old observers remain
unchanged. The pinned core does not charge IRQ-entry cycles. That limitation is
retained: +100 IRQ stress supplies extra margin, without repairing general
simulator interrupt timing. See the [AVR cookbook](../../../../docs/avr-asm-cookbook/lpx-external-spi.md)
and [host timing provenance](../../validation/atmega328p/spi/PROVENANCE.json).

## Artifact and reproduction provenance

The original bounded worker saved all 16 positive physical proofs, then failed
its final in-memory reopen because a JSON round trip changed a tuple into a
list. Its failed attempt and receipts remain preserved. A separately sourced
[read-only admission](reproduction/admit_bounded.py) strictly reopened the saved
JSON rows and admitted them before any long row launched. It performed zero
builds or simulations and did not relabel the original worker as successful.

All 28 image/source/recipe/compiler/header/runtime/model/output proofs were
strictly reopened by the terminal aggregate and again by the
[exporter](reproduction/export_results.py). [Artifact checks](artifact-check.json)
and [source receipts](reproduction/sources.json) bind this anonymous projection.
All 155 measured source-inventory files match immutable Git ref `8c680fcf`
byte for byte, equivalent to the executed `a61ca39e` source. The separately
identified integration repair `9a896163` reloads persisted JSON before the
bounded gate for fresh reproduction; it changes no measured MCU source or
flags and was not consumed by these jobs.

Parent callback validation passed 199 current tests, including eight input
checks; five historical prototype checks passed separately against the pinned
unchanged source. Four callback-disabled AVR core objects were byte-exact
before/after the optional input addition, common/v5-only times C/ASM. The source
guard remained intact when a changed-source historical prototype was rejected.

No fitting, repeated simulation, new quality selection or perceptual adoption
occurred here. Earlier listening feedback remains inconclusive. Private media,
ordered streams, images, output fingerprints, source identities and runtime logs
remain excluded from this public evidence.
