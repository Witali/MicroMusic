# Evaluation and additional-pool AVR release admission

All **406 final production images pass** complete playback validation: exact
full model-derived PWM, useful sample counts, timer events/ticks and terminal
EOF, with zero underruns, decoder errors or observer errors. This completes the
remaining 58 profile groups from the expanded evaluation/additional controls.
No audible improvement is claimed.

The source has 40 evaluation groups and 18 additional groups: 20 speech,
20 regression, 10 phrase and eight independent profile groups. Original
baselines plus selected/raw alternatives at 100/95/90% create **248 bindings**
to **203 distinct exact ordered chains** in this batch. Every chain is tested
with normal and +100-cycle audio IRQs, for **21,790,882 exact sample checks**.
The original references range from 8,000 to 281,632 samples. The long chains
are checked to their complete length, without a 64,000-sample output cap.

| Actual segments per chain | Distinct ordered chains | Final images |
| --- | ---: | ---: |
| 1 | 169 | 338 |
| 2 | 15 | 30 |
| 3 | 13 | 26 |
| 5 | 6 | 12 |

The decoder resets at each actual encoded segment; the player concatenates
all queued samples without inserted silence. Expected PWM is built from the
same complete ordered reset geometry. Code and decoder tables are linked
once per image, with every segment's full header/payload counted once and
pointer/size metadata retained in program cost.

## Source selection and byte caps

| Complete-byte cap | Source-selected bindings | Raw bindings | Source pool reports no fit |
| --- | ---: | ---: | ---: |
| 100% | 58 | 58 | 0 |
| 95% | 1 | 50 | 8 |
| 90% | 0 | 23 | 35 |

Raw roles retain `quality_adopted=false` even after playback succeeds.
Original baselines stay available as controls, with lower-cap eligibility
explicitly labeled. `no_pool_combination_fits` retains the bounded source-pool
outcome; no image exists for an absent candidate and no encoding-impossibility
claim follows. Source-selected labels represent numerical whole-reference
floors, without a listening or music-intelligibility conclusion.

The one selected 95% regression point saves **100 B of actual full Flash**
at each IRQ load. The raw 95% points save 26–1,344 B; raw 90% points save
52–826 B. Raw roles keep their recorded metric/floor labels and are not independently
adopted by playback; the conservative point is identified separately. Savings compare
each complete linked candidate image with its corresponding baseline at the
same profile/reset geometry/IRQ recipe, including linker and alignment effects.

## Production recipe and measured resources

ATmega328P / AVR5, 16 MHz / 8 kHz, unchanged decoder `5c7e0592`, selected
release player/config from `22e50e01`, explicit ASM, LPC segments 2, queue 256 /
prefill 192. AVR-GCC 7.3.0 uses `-Os -flto -mcall-prologues -mrelax`, unroll 1 /
tuning 0. The separate external observer uses vendor-derived unlinked metadata
and actual playback state. Production ELFs contain no profiling globals.

| IRQ load | Full Flash per image | Program excluding exact streams | Static SRAM |
| --- | ---: | ---: | ---: |
| Normal | 5,042–27,850 B | 4,573–4,592 B | 756 B |
| +100 cycles | 5,050–27,858 B | 4,581–4,600 B | 756 B |

Complete stream bytes span 468–23,259. `.data` is zero, so `.text` equals
full Flash; `.bss` and static SRAM are 756 B throughout. Each image contains
one complete ordered audio chain, rather than the whole corpus. Program size
includes decoder, tables, player and all reset-chain metadata; it is not an
independently linked library footprint.

Every final image reports an empty queue at successful EOF, minimum observed
queue 192 before producer EOF, and **1,231 B minimum stack margin**, with
startup/prefill and playback coverage reported separately. PWM intervals are
1,995–2,005 CPU cycles around the 2,000-cycle timer period. Maximum observed
IRQ duration is 68 cycles normal / 168 cycles under the added load. These are
observations on this declared simulator workload, not universal worst-case bounds.

## Independent artifact audit

After playback, a fresh process reconstructed all ordered streams from the
immutable control receipts and independently checked every final image:

- Current complete build environment and loaded validation runtime match the
  recorded source, flags, toolchain/vendor dependencies and model/Python inputs.
- ELF, Flash binary and HEX hashes match the private receipts; `avr-nm` proves
  exact embedded segment bytes/ranges and excludes diagnostic-only state.
- A fresh `avr-size` invocation confirms `.text`, `.data`, `.bss`, full Flash,
  program/data subtraction and static SRAM.
- Every actual complete PWM file equals the independently reconstructed model
  output, with matching report hashes, full counters, EOF and zero errors.

Two initial attempts were rejected by the output-directory guard before any
build/playback. Their unchanged absolute paths subsequently passed the same
guard and fresh retries. Both original rejected attempts and retry receipts
are retained; no guard, source or tuning artifact was changed. All 406 final
images passed the post-run audit.

[Summary and public source/toolchain/runtime bindings](summary.json),
[all final image costs/timing/stack observations](images.json), and
[all group/cap/selected/raw/no-fit bindings with source metrics](groups.json)
use anonymous IDs. The completed [250-image tuning batch](../full-tuning-release-2026-10-28/README.md)
is immutable and separate. Together the two batches cover all 98 expanded
profile groups with 656 final image checks and 33,758,306 actual sample checks;
fresh batches are counted as checks, without asserting cross-batch chain uniqueness.

Private original IDs/paths, media, expected/actual PWM, ELF/HEX/maps and
media-derived fingerprints remain in ignored build storage. Portable C remains
selectable; active-IRQ timing here applies to explicit ASM on the stated target.
No physical-board, analog or audibility claim is made.
