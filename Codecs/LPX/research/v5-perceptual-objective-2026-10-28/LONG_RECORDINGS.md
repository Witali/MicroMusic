# Whole-recording objective length and memory

The former 1,000,000-sample input limit excluded two non-speech corpus
recordings. The objective now scores both in full, with actual decoder reset
geometry and continuous perceptual error history. No truncation, rescaling,
STOI interpretation or audible-quality claim is used.

| Complete recording | Reset segments | Profiles checked | Stored Q12 coefficient rows | Frozen PCM16 reference |
|---|---:|---|---:|---:|
| 3,786,111 samples | 60 × 63,101–63,102 samples | 4 and 6 | 3,787,200 B | 7,572,222 B |
| 3,138,052 samples | 50 × 62,761–62,762 samples | 4 and 6 | 3,139,000 B | 6,276,104 B |

V5's exact model coefficients repeat for each 20-sample subframe. Keeping one
int16 row is lossless; 6,400-sample frame-aligned coefficient generation uses
one preceding LPC frame as context. Thus the longest recording does not need a
303 MB whole-recording int64 coefficient trace or copies of it. The largest
temporary generated trace is 6,560 × 10 int64 coefficients (524,800 B).
Arbitrary dense-constructor traces remain supported, using int16 chunks
without assuming repeated rows. SSE factories validate the full streams and
construct no coefficient matrix.

All four real contexts match an independent SciPy oracle that reconstructs
physical input/output histories at every coefficient change and carries those
histories across every reset boundary. The observed final weighted scores are
equal in this run (relative difference 0); tests allow a numerical tolerance
of 2e-12 for floating-point reductions. Each chunk's damping uses identical
settings, and the minimum equals the whole-segment/whole-seed contraction
solution. All six frozen tuning contexts retain bit-exact effective gamma2.
Fresh common/v5-only native, integer model and frozen PCM/PWM comparison passes
over every segment: 880 native output-domain comparisons across the four
contexts. The complete verification takes 128.359 seconds, mostly independent
SciPy and receiver checks. [Exact anonymous measurements](long-recordings.json).

With Python tracemalloc active, the longest contexts prepare in 2.44–2.84 CPU
seconds and score in 0.078–0.109 CPU seconds. Traced preparation peaks at
15,338,292 B, retained tracked memory at roughly 11.66 MB, and score peaks at
roughly 11.94 MB. These are single warm-run instrumented measurements, not
universal speed or process-RSS claims. They include tracked NumPy buffers but
exclude incoming reference/candidate/seed buffers and untracked native/JIT/
runtime allocations. Exact retained numeric-array byte counts are above;
the JSON separately reports preparation, scoring and SSE memory/time scopes.

The original-count contract extends through uint32 maximum 4,294,967,295.
The largest squared PCM error at that length is
18,446,181,123,756,261,375, exceeding int64. Each 6,400-sample dot is bounded
and exact in int64; Python integers accumulate the total before converting
to the existing scalar-float score API. Perceptual chunk energies use
compensated summation. A full-length 3,786,111-sample extreme PCM test and a
zero-allocation over-uint32 shape rejection exercise these boundaries; the
theoretical maximum's memory/runtime was not measured.

Forty test methods in five modules pass, including independent SciPy and
chunk/state/reset checks, original full-trace comparisons, SSE without unused
LPC, wrapper gates, trajectory and allocator integration, and old perceptual
controls. MCU source and the old weighting helper remain unchanged. Source,
model, native compiler/runtime and driver hashes are pinned in the receipt;
private recording identities, paths and recording/stream/PCM hashes remain
only in ignored build storage.
