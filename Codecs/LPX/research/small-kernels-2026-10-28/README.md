# Small kernel and parser boundaries, 2026-10-28

The fixed source baseline includes the complete-packet tail correction
`b8f473a6` (local cherry-pick `806c8f8f`). One coherent change is selected:
allow the compiler to share the existing Q14 attenuation helper instead of
forcing both postfilter calls inline. No arithmetic, format, state layout,
EOF rule or hardware access changes. C and explicit supported-target ASM remain
selectable; no assembly was added.

## Selected attenuation sharing

`Lpx4Math.h` keeps `static inline` and removes only `always_inline` from
`lpx4AttenuateQ14`. Under the fixed size recipe the automatic and forced-noinline
forms produce identical program binaries in all ten measured images, so the
simpler automatic form is retained. There is no new tuning exception or flag.

ATmega328P / AVR5 GNU ABI, AVR-GCC 7.3.0, 16 MHz / 8 kHz, unroll 1/tuning 0,
`-Os -flto -mcall-prologues -mrelax`, compact-only and explicit ASM. Queue 512,
prefill 384 and LPC segments 2 are unchanged. Ten complete images from five fixed recordings cover both
profiles, normal/quiet/noisy 64000-sample inputs, a short prepared input and a
five-reset long recording. Exact audio arrays and reset geometry stay fixed.
Complete Flash includes shared code, data, tables, reset dispatcher and the
retained profiling harness.

The selected change saves **38 B in all ten full images**, with unchanged
static SRAM. Non-stream program Flash is 4983-5090 -> 4945-5052 B on this screen.
Eight before/after 64000-sample IRQ images cover profiles 4/6 and normal/+100-cycle
IRQ loads: complete model PWM is exact, zero underruns/errors, and observed
stack margin remains 894 B. Decode wall cycles grow 1.63-4.01%, an explicit
size/time tradeoff with measured real-time margin. C arithmetic is numerically
verified; no new real-time admission is claimed for its slower decoder path.

A separately pinned earlier parent LSF/grid snapshot also benefits: 38 B per
single-reset image, 40 B per five-reset image. Its source inventory is retained;
it is not silently treated as the later final LSF implementation. Final combined
source and full selected-image admission remain separate integration checks.

## Independent screens

All patches apply independently to the tail-corrected baseline, not to each other.
Positive Flash deltas are regressions under the present priority.

| Experiment | Full Flash delta on the fixed images | Decision |
|---|---:|---|
| Static/private polynomial factor | 0 B, binary-identical | No-op, leave production unchanged |
| Automatic attenuation sharing | -38 B | Select |
| Forced outlined attenuation | -38 B, identical to automatic | Keep simpler automatic form |
| Signed result/failure-bit Rice | +6 B single / +16 B long | Reject |
| Bool/out Rice | +6 B single / +8 B long | Reject |
| One packed Rice shape argument | +8 B | Reject |
| Narrow transmitted-vector helper, automatic | +8 B single / +4 B long | Reject |
| Same helper, forced outline | +38 B single / +42 B long | Reject |
| Same helper, forced inline | 0 B | No size benefit |
| Shared cached-prefix primitive | +70 B single / +74 B long | Reject |

The narrow helper owns only the ten transmitted coefficients after repeat/delta
markers. Its success contract is coherent; it does not pretend a whole first-half
parse succeeded while depending on a deferred sticky read error. Cached-prefix
sharing retains the distinct protocols: legacy requires a terminator after eight
zeros, compact Rice treats eight zeros as escape. An error already on entry must
still consume the same cached/refill operations; a new early error guard would
change reader state and diagnostic counts.

## Correctness and reproducibility

- 25 focused native tests pass: C math and unsupported-host ASM fallback,
  polynomial/frozen/ordered coefficients, parser/bit traces, half-spectrum
  segments 1/2/4 and bandwidth-expansion controls, tails, copy/restart and reference
  configurations.
- Every Rice interface and the shared-prefix form matches 9,418,752 reader states
  per common/compact and ROM pointer/base-cursor configuration: 37,675,008 per
  variant. The probe checks values/status, sticky error, pointers/remaining bytes,
  bit cache and instrumented read counts, including errors already on entry.
- The three spectrum boundaries and shared-prefix preserve 7,355,956 frozen
  parser states per variant across those four configurations. The shared-prefix
  also matches 4,709,376 legacy unary states over reference/register/nibble modes
  and both reader layouts.
- Fresh AVR C, explicit ASM and forced-generic math builds each pass 5,768,584
  cases with active interrupts, zero arithmetic/r1 errors. These use the standard
  arithmetic-fixture recipe at unroll 1; the separate full-image IRQ comparisons
  use the size recipe above. Neither is a physical-board or startup stack proof.

[Screen rows](screen.csv), [source inventories](sources.json),
[verification](verification.json) and source-only [patches](experiments) retain
positive, negative and no-op results. `reproduction/rice_oracle.cpp` accepts
`RICE_INTERFACE=0/1/2/3` for raw/signed-status/bool-out/shape. Compile it with the
selected source include directory, speech+compact flags, diagnostic costs,
`LPX4_COMPACT_ONLY=0/1` and `LPX4_ROM_POINTER=0/1`; expect 9,418,752 states.
The legacy oracle additionally takes `LPX4_FAST_UNARY=0/1/2`. The existing
`tests/compact_parser.cpp` gives the retained frozen parser digests.

For linked measurements reconstruct a baseline source copy at `b8f473a6`, apply
one patch with `git apply --unidiff-zero` in an ignored build directory, verify its source hashes, then call the
existing `measure_speech_firmware.measure` using the same private selected stream
list and reset geometry. Use `simulate` for IRQ validation. Source audio,
recording identities/paths, stream/PCM fingerprints and generated firmware stay
local; the public numerical evidence uses anonymous IDs only.
