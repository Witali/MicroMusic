# Full tuning-pool AVR release admission

All **250 freshly built production images pass** complete playback validation:
exact model-derived PWM, useful sample counts, timer events/ticks and terminal
EOF, with zero underruns, decoder errors or observer errors. The batch covers
all completed expanded-legacy tuning control assets at 100/95/90% budgets.
Passing playback does not adopt raw quality tradeoffs.

The input has 40 tuning profile groups: 20 speech and 20 regression groups.
Each group contributes its immutable original baseline and any source-selected
or raw alternative at the three byte caps. This gives **155 bindings** to
**125 distinct exact ordered stream chains**, each tested at normal and
+100 cycles per audio IRQ. Deduplication compares the actual ordered byte
streams. In this set every chain has one reset segment and 32,000–64,000
samples. Unique normal chains cover 5,983,712 samples; both IRQ loads cover
**11,967,424 exact sample checks**. The same underlying references appear with
several encoded alternatives, so this is not that many independent recordings.

## Budget and quality labels

| Complete-byte cap | Source-selected bindings | Raw bindings | Source pool reports no fit |
| --- | ---: | ---: | ---: |
| 100% | 40 | 40 | 0 |
| 95% | 0 | 28 | 12 |
| 90% | 0 | 7 | 33 |

All original baselines are retained as controls. Their eligibility at each
lower cap is explicitly labeled in the group receipt. Raw lower-cap points
remain `quality_adopted=false`, even when their playback passes. At 95/90%
there is no conservative selection under the incoming whole-reference floors.
`no_pool_combination_fits` preserves the source finite-pool result; it is not
an encoding impossibility proof and has no generated candidate image.

Source-selected 100% points save 0–2 bytes of actual paired full Flash versus
their original baseline at the same profile/IRQ recipe. The raw 95% points
save 92–350 bytes; raw 90% points save 182–390 bytes. Those latter savings
belong to explicit quality tradeoffs. They are measured from complete linked
images, including any alignment/linker effect, rather than inferred only from
stream percentages. STOI and other numerical labels do not establish listening
or music-quality improvements.

## Production recipe and complete-image costs

ATmega328P / AVR5, 16 MHz / 8 kHz, unchanged v5 decoder `5c7e0592`, selected
release player/config from `22e50e01`, explicit ASM, LPC segments 2, queue 256 /
prefill 192. AVR-GCC 7.3.0 uses `-Os -flto -mcall-prologues -mrelax`, unroll 1 /
tuning 0. Full `.text + .data`, exact embedded arrays, generated ELF/HEX and
separate external-observer evidence are retained privately. This batch imports
no historical diagnostic cost and reuses none of the earlier eight artifacts.

| IRQ load | Full Flash per image | Program excluding exact streams | Static SRAM |
| --- | ---: | ---: | ---: |
| Normal | 6,208–9,834 B | 4,573–4,576 B | 756 B |
| +100 cycles | 6,216–9,842 B | 4,581–4,584 B | 756 B |

Encoded stream bytes span 1,634–5,258. `.data` is zero, so `.text` equals full
Flash; `.bss` and static SRAM are 756 bytes throughout. Program size retains
decoder, tables, player and stream/reset metadata. It is not a library-only
footprint or a build containing the entire corpus. Each actual byte array and
its unique binary range are proved before subtracting audio data.

The established external observer validates vendor-derived unlinked metadata
against the device model and ELF state. Every image observes an empty queue at
successful EOF, minimum queue 192 before producer EOF, and minimum stack margin
**1,231 bytes**, with startup/prefill and playback reported separately. PWM
intervals span 1,995–2,005 cycles around the 2,000-cycle timer period; maximum
observed IRQ duration is 68 cycles normal / 168 cycles under the added load.
These are observations on the declared simulator workload, not universal bounds.

All completed artifacts share the exact MCU source, player, settings,
toolchain/vendor header dependencies and loaded host validation runtime.
The collector independently rechecks these identities across every image.
Portable C remains selectable; this active-IRQ timing admission applies to
explicit ASM on the stated target. No physical-board, analog or audibility
claim is made.

## Anonymous evidence

- [Source-bound summary, recipe, budget labels and ranges](summary.json).
- [All 250 actual image costs and playback/stack observations](images.json).
- [All 40 groups, 155 bindings, caps, source metrics, selected/raw labels and paired full-Flash differences](groups.json).

Anonymous group/chain/image IDs join the public receipts. Original private
IDs and paths, source media, expected/actual PWM, ELF/HEX/maps and media-derived
fingerprints remain in ignored build storage. Native/model checks and quality
labels come from the completed frozen expanded-legacy control; this report adds
the actual full production image and interrupt-active playback admission.
