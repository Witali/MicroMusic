# Current baseline repeat-mask1 survey

The [fixed protocol](PROTOCOL.md) is complete: all **104 current baseline chains /
242 unique reset streams** passed exact serialized byte and independent raw
parameter round trips. Counted experimental lengths equal the in-memory V6
serialization. There was one corpus attempt, followed by a separately recorded
read-only replay and export; all three processes exited 0.

This measures complete stored data, including headers, selectors and independent
reset padding. Program Flash, linked metadata, SRAM, stack, native PCM/PWM and
IRQ behavior remain unmeasured. The production decoder was unchanged.

## Data-only results

| Data category | Chains | Original bytes | Hypothetical V6 bytes | Saved bytes |
| --- | ---: | ---: | ---: | ---: |
| ROM-data-eligible | 102 | 373,737 | 371,170 | 2,567 |
| SPI-required on data alone | 2 | 501,656 | 493,209 | 8,447 |
| Benchmark total | 104 | 875,393 | 864,379 | 11,014 |

103 chains shrink; one is unchanged. The per-chain saving ranges from 0 to
5,368 B, median 19 B. Speech medians are 24 B for profile 4 and 12 B for profile 6.
These corpus sums are benchmark totals, not a decoder-code allowance for one
image. ROM-data eligibility means only that encoded data fits within 32 KiB;
complete firmware fit is unproven.

The two full long SPI chains retain all 60 resets each: profile 4 data changes
202,600 -> 197,232 B; profile 6 changes 299,056 -> 295,977 B. Their audio data is
external, so those 8,447 saved bytes do not reduce MCU program Flash. Actual
linked code/layout costs are null in the reports. The source-level 4N ROM / 6N
SPI table spans are labelled unlinked, unchanged layout counts. Historical
45–47 B decoder growth is never used as a current subtraction constant.

## Largest ROM data opportunities

These are saved-row projections for possible future complete-cost validation,
not adopted formats or verified firmware savings. Both original complete data
totals fit 32 KiB on data alone, and all proposed reset spans fit uint16.

| Anonymous chain | Profile / samples / resets | Original data | Hypothetical data | Data saved |
| --- | --- | ---: | ---: | ---: |
| chain-043, speech | 4 / 281,632 / 5 | 16,141 B | 15,995 B | 146 B |
| chain-102, nonspeech | 6 / 41,600 / 1 | 3,178 B | 3,074 B | 104 B |

[Largest three per profile](largest-rom-data-savings.json) retain the corresponding
data-only bounds. Complete linked image fit and net MCU saving remain unmeasured.

## Preservation and scope

The survey reused the exact old audited `repeat-mask1` counter and both retained
raw-bit adapters, checked against their original software-source receipts. All
242 current streams also match the existing V5 serializer byte for byte. Pure
contracts separately protect nonminimal Rice spans, forced extras, legal
zero-amplitude markers and every raw scale value in both profiles.

All 81,140 stored tuples remain charged, including 158 unplayed tail tuples,
6,465 zero-gain tuples and 4,865 lag changes at zero gain. The 183 stored raw
scale codes 0..5 and 1,520 codes 6..9 retain their original aliases. Histograms
keep stored/audible counts and reset histories separate. No experimental stream
or source audio was copied into the evidence package.

Runtime guards recorded zero forbidden-operation attempts during the study and
replay. There were zero waveform syntheses, quality metrics, fits, native builds,
target jobs or simulations. Serialized reversibility is not native/target
PCM/PWM validation. No decoder materializer, firmware port or source guard was
changed. Further native or target work is not authorized by this result.

## Evidence and reproduction

[Summary](summary.json), [whole chains](chains.json), [segments](segments.json),
[histograms](histograms.json), [artifact checks](artifact-check.json),
[contracts](tests.json), [execution recipe](run-recipe.json) and
[software sources](reproduction/sources.json) are anonymous projections. Original
baseline identities, level/reference descriptors, stream/experimental hashes,
first-attempt/replay bindings and logs remain in ignored private storage.
The measured run body, after module import, took 33.62 s wall / 31.83 s CPU.
The frozen executing source is
`70a7afb75c6c26e9328ca3910402ac30478aa91a`, based on `4a01ec6f`.

Run from the repository root with existing codec Python dependencies and no
Python optimization flag. Supply the fixed original baseline binding locally:

```sh
python Codecs/LPX/research/v6-repeat-current-scan-2026-11-01/reproduction/test_serialized.py
python Codecs/LPX/research/v6-repeat-current-scan-2026-11-01/reproduction/scan.py \
  run --baselines "$BASELINES" \
  --source-commit "$SOURCE_COMMIT" --output build/repeat-current/scan-v1
python Codecs/LPX/research/v6-repeat-current-scan-2026-11-01/reproduction/scan.py \
  audit --study build/repeat-current/scan-v1
python Codecs/LPX/research/v6-repeat-current-scan-2026-11-01/reproduction/scan.py \
  publish --study build/repeat-current/scan-v1
```

Use a fresh ignored output for any independently authorized reproduction. The
recorded single-thread numerical-library settings are in the execution recipe.
