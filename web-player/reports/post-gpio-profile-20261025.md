# Sampling after settled-GPIO dispatch

Twelve fresh-state profiles of `fc40b21a` retain 12,383 samples beneath the
public capturePhysical call. The three physical music cases still spend about
72–73% of inclusive samples in the native phase-clock bridge and its descendants.
The large recurring scheduler path remains the next target; these percentages
are not exact exclusive CPU/peripheral costs or speed measurements.

Native runtime: 118,946 bytes, SHA
`1fe4bef5bdc458bb8ca2a65636221e4b5ed87a4d5003eca6b60532c4baf45b9f`.
Each symbolic rebuild byte-matches production before diagnostic names are added
only as a custom section. All 12 named/profiled runs match their uninstrumented
reference on complete public/diagnostic state, data/Flash/EEPROM/IRQ and PCM.
There are no production instrumentation, host callbacks or runtime changes.

The profiler uses the control benchmark's input, fuse/NVM and fastIdle settings.
Music captures 48,000 frames; the CLKI 20 MHz /1 kernel captures 4,800, at 48 kHz.
Each has three sequential profiles, requested interval 1 ms. Construction,
warmup, hashing and comparison are outside sampling. Host: Windows/Ryzen 5 5600X,
Node 22.22.3/V8 12.4, Clang 24/Binaryen 133. Load, clock frequency, GC, sampling
gaps and JIT tiers are uncontrolled. No balanced elapsed-time comparison is made.

| Case | Work samples | next_event_scan self | ratio self | duration self | phase-clock inclusive |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rhythmic physical | 3,353 | 8.26% | 7.87% | 8.23% | 73.28% |
| Lumière physical | 3,337 | 7.52% | 7.97% | 7.49% | 72.22% |
| HQ4 physical (`hq4-chego-tiny`) | 3,367 | 6.77% | 6.92% | 8.02% | 72.71% |
| CLKI 20 MHz /1 kernel | 2,326 | 6.41% | 2.11% | no leaf observed | 89.55% |

The CLKI kernel's largest surviving leaf is native.device.service, 11.91%;
it includes inlined work. Inclusive shares overlap and must not be added.
Unobserved leaves do not prove that a function was never called. Source ownership
describes optimized bodies, not pure subsystem cost; no exact exclusive timing
item closes. The previous source-entry trace establishes work removal separately,
and its different queued-input convention must not be used to assign these costs.

This supports moving to the plan's adaptive bounded-region instruction budgets,
which can reduce per-instruction native barriers while remaining strictly before
the earliest peripheral/input and caller deadlines. Evaluate that generator
change independently against an identical native runtime; keep pending IRQ,
partial-instruction, clock-before-commit and external-entry fallbacks. CLKI's
necessary physical phases remain outside positive region budgets. No browser
real-time/default-engine or hardware-validation claim follows from this profile.
The hardware plan remains 21/30, with nine open items.

All raw profiles are preserved as gzip in the [evidence folder](post-gpio-profile-20261025/),
with both original summaries, pooled analysis, native function inventories and
tool snapshots. The verifier checks pinned source identities, raw profile hashes,
sample ancestry and every retained self/inclusive count and pooled percentage.

```sh
node web-player/reports/post-gpio-profile-20261025/replay.mjs
node web-player/scripts/profile-device.mjs --clock physical --benchmark-controls --firmware rhythmic,lumiere-stereo,hq4-chego-auto --frames 48000 --repeats 3 --out-dir build/profiles/post-gpio-music
node web-player/scripts/profile-device.mjs --kernel --clock clki --benchmark-controls --frames 4800 --repeats 3 --out-dir build/profiles/post-gpio-clki
```

These commands describe the recorded clean `fc40b21a` sources; later generator
experiments require their own identity. Official semantics remain
[Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
and the [WebAssembly binary specification](https://webassembly.github.io/spec/core/binary/instructions.html).
