# Current baseline scale-repeat serialized-cost survey

This is a metadata/serialized-bit study, starting from integration `4a01ec6f`.
It leaves all production and previous research epochs unchanged. Its sole method
is the previously nominated `repeat-mask1`: first scale/lag/gain tuple absolute;
later scale gets one repeat/change bit and five raw bits only on change. Lag and
gain codes stay absolute. Charge the existing 22-byte header, one selector byte
per reset and independent final padding. No dual-format minimum envelope is used.

## Fixed population

Use exactly the 104 complete strongest canonical/matched-CPU100 baseline chains
in the original, terminal `lpx-joint-rate-baselines-private-v1` binding supplied
through `--baselines`, with its adjacent completion marker. This is the unchanged
pre-pilot population, including both profiles, declared preserve/auto-quiet level
contexts and full nonspeech reset chains. Preserve its order, complete stored
segments, starts, profiles, sample counts and bytes. Do not choose new frontier
points or replace a baseline using this survey. Bind every used stream by its
recorded hash/size and the entire original baseline binding by its actual hash.
Reference/target/level descriptors stay private; no audio file needs to be opened.

## Source and operations

Freeze this driver/protocol/contracts before the corpus pass. Hash-check current
production/tools and the retained raw-bit adapters against the explicit source
commit. Require `speech_parameter_costs.py` and its histogram helper to match the
old audited source-runtime receipt, and both converter/reference files to match
the frozen scale-repeat pilot source receipt. Import them from this worktree.

Reuse the actual audited counter's `inspect_stream` and `stream_cost`, only
`METHODS[0]`. Compare counted bytes with an in-memory forward conversion, exact
V5 -> experimental V6 -> V5 bytes, and a second indexed-bit reverse adapter.
Do not write experimental streams. Preserve all raw scale aliases, lag at zero
gain, nonminimal spectral Rice choices, extras flags/zero-amplitude markers and
mandatory unplayed tuples. If a valid byte stream cannot be preserved, retain a
failure receipt and report it; do not normalize or loosen a guard.

This permits only header/bit parsing, counting, integer histograms and reversible
serialization. Runtime guards reject synthesis, model/quality metrics, encoder
search/fitting, subprocesses and native-library loading during the actual pass.
No native builds, materializer, decoder/firmware port, target image, simulation,
PCM/PWM synthesis or audibility test is allowed. Pure serialized contracts use
hand-authored fields, not a fitted encoder or sound fixture.

## Reporting and admission limits

Report every segment and complete chain, signed stored-byte savings, exact bit
and padding counts, raw parameter/repeat histograms, unplayed/gain-zero cases and
uint16 segment bounds. Distinguish 32 KiB data-alone eligibility from firmware
fit. Separate ROM-data-eligible and SPI-required-by-data chains and both profiles.
For SPI, encoded audio occupies external storage; its saved bytes do not reduce
MCU program Flash. Source-level directory spans (4N ROM / 6N SPI on AVR5) are
labelled unlinked layout counts. Program cost, linked layout, net complete Flash,
SRAM, stack and IRQ admission are all unmeasured/null. Never subtract historical
45–47 B overhead or claim complete-Flash or output-quality improvement.

Keep original baseline IDs, references, levels, paths, input/stream/experimental
fingerprints and attempt logs private under ignored `build/`. Publish only
anonymous costs/histograms and verified software-source hashes. Preserve a real
started/failed/terminal attempt and its ordered events; never resume by silently
overwriting an attempt. A read-only audit/export is a separately labelled replay
of this serialized evidence, with zero model/metric/native/target operations.
