# Reduce common binary factors in wide clock ratios

The native ATtiny13A clock helper now reduces a shared power of two before
wide multiply/divide, restoring the exact original numerator remainder. Two
separate 20 MHz unbounded direct-kernel screens measure paired median
**1.169x / 1.232x**, with all **16/16** pairs faster. This is a scoped full-device
runtime gain. Music/audio-capture gains remain unproven, and small capture
losses remain possible. No hardware checklist item closes: **24/31, seven open**.

## Change and preserved behavior

Only `device_clock.h` changes among native inputs. After its original
native-width fast path, the helper computes `s=ctz(b|d)` and splits off the
low `s` carry bits. Quotient overflow admission stays exact; the reduced
remainder is scaled back with those bits. The generic wide fallback remains.
The [cookbook proof](../../docs/avr-asm-cookbook/clock-power2-reduction.md)
covers shifts 0/63, improper carries, reconstruction bounds and failed outputs.
The baseline in Git and independent BigInt tests remain reference oracles.

This changes native time conversion, preserving CPU instructions, cycles,
phases, event ordering and all pin transitions. It adds no state, host callback,
device behavior or ABI. The browser loader URL and generated persistent-cache
identity are refreshed. All generated CPU byte hashes match across the captures
and final replay after that refresh. The site model and legacy native artifact
are unchanged; no browser real-time audio gate is claimed.

The candidate rebuild is byte-exact. Static comparison finds 216 identical
function bodies and exactly two changed bodies: `ratio` 464→522 bytes and
`duration` 526→577. Runtime grows **109 bytes**, 124,505→124,614; it retains
17 C sources, 117 function exports, no host imports and fixed two-page memory.
SHA-256: `b9a8fa14a971fd5f82f8175f978e9a0b1e03f31fc8612a6892d202d7f93635a1`.
No working-memory saving is claimed.

## Why the matched workload matters

The saved [native sample replay](native-function-containers-20261030.md)
identified `ratio`. Inspection of the actual TurboFan instruction offsets
places many observations in its long division loop, before its first recorded
source position. Such gaps include arithmetic, not just the function prologue.
Instruction-counted `run()` repeatedly converts `UINT64_MAX-1` for its unbounded
deadline; this can require a wide intermediate. Its finite-timeline capacity
check remains. The arithmetic reduction needs no deadline cache or invalidation.

The first screen's direct kernel used 9.6 MHz and found only **1.008x** (5/8
positive). A newly explicit 20 MHz direct fixture matches the profiled rate:
both matched screens run 10,000,000 instructions at divisor 1. This is an
explicit synthetic software oscillator profile, with silicon RC calibration
still unmeasured. Sparse sampled PCs do not prove a causal timing breakdown.

## Serial measurements and limits

Windows/Ryzen 5 5600X, Node 22.22.3/V8 12.4.254.21-node.56, pinned
Clang 24/Binaryen 133 SDK. Each case uses eight four-label balanced trials and
four full-workload warmups per label. Identity pairs share a native Module;
each construction has fresh state and a fresh generated CPU Module. Setup,
compilation, snapshots and hashing remain outside execution timers. No other
test/profiler workload was launched alongside these timings. Host background
load, CPU frequency, GC and affinity are uncontrolled.

| Expanded control | Old identity | New identity | Old/new median | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| rhythmic compatible | 1.018 | 1.038 | 1.044x | 5/8 |
| rhythmic physical | 1.005 | 0.968 | 0.999x | 4/8 |
| Lumiere stereo physical | 0.995 | 0.999 | 1.009x | 6/8 |
| HQ4 physical | 1.019 | 0.922 | 0.983x | 4/8 |
| CLKI 20 MHz /1 | 1.026 | 1.028 | 1.057x | 6/8 |
| CLKI 20 MHz /256 | 1.056 | 1.016 | 1.039x | 8/8 |
| Internal 20 MHz capture | 0.959 | 0.957 | 0.978x | 3/8 |
| Internal 20 MHz direct | 0.984 | 1.017 | **1.232x** | **8/8** |
| Internal ADC active | 1.011 | 0.998 | 0.983x | 3/8 |
| CLKI ADC active | 0.963 | 1.028 | 0.985x | 3/8 |
| Internal watchdog active | 0.866 | 1.063 | 1.051x | 5/8 |
| CLKI watchdog active | 1.025 | 0.997 | 1.019x | 5/8 |

Music uses 12,000 frames at 48 kHz; kernel capture controls use 2,400 frames.
The initial HQ4 screen has median 0.971x, 3/8 positive, also establishing no
music gain. The first matched 20 MHz screen is 1.169x, range 1.064–1.663; its old
identity range reaches 2.014x. The repeat is 1.232x, range 1.161–1.262. Keep every
trial, including the large outlier. Do not generalize the direct-kernel gain to
capture, real firmware, other clock rates or browser throughput. Possible
roughly 2% capture losses remain a limitation under the observed host variation.

Across the three timing batches: **480 timed executions, 240 warmups and 3948
exact checkpoint comparisons**. Initial 15-case and final 16-case untimed parity
replays retain exact PCM, complete public/CPU/memory/IRQ state and pin tails;
enabled ADC/watchdog controls assert actual conversions/IRQs. The final replay
also covers the added direct fixture with the refreshed loader/cache identity.

## Correctness and reproduction

**2642/2642 default/shared checks pass** (2581 player + 61 shared music/startup).
The additional clock test covers 13,200 calls across every shared binary factor,
full-width operands, improper carries, failure-output preservation and real
model rate/horizon factors. The 41-scenario virtual-event replay still compares
17,890 events with maximum 1 ps difference against its ideal rational fixtures,
within the verification-only 10 ns bound. These are software/profile results;
silicon calibration and unresolved Timer0/RESET/debugWIRE modes stay open.

```text
node web-player/scripts/build-device-wasm.mjs
node web-player/scripts/generate-avr-cache-identity.mjs
node --test web-player/tests/*.test.mjs
node --test tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
node web-player/scripts/benchmark-runtime-controls.mjs --baseline-ref ef369a09 --change-set clock-power2 --trials 8 --warmups 4 --instructions 10000000 --case kernel-internal-20m-div1-direct --out build/clock-power2-20261030/matched-screen.json
node web-player/scripts/verify-clock-power2.mjs --output web-player/reports/clock-power2-20261030.json
```

The [JSON evidence](clock-power2-20261030.json) retains all individual durations,
identity/cross ratios, workload/options, exact-output digests, compiler/source/
native identities and input/TAP hashes. Its collector requires the original
ignored capture files, validates their sources and recomputes ratios. It also
reconstructs the initial harness by removing only the later direct fixture.
The initial interrupted test launch before cache-identity regeneration is
excluded; the full passing TAP comes from the final generated identity.
Raw captures, disassembly, intermediate builds and full TAP remain in ignored
`build/clock-power2-20261030/`. No new external download was needed.
