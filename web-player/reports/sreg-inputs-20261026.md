# Rejected: remove unused SREG input dependencies

Decision: keep the production compiler from b8c34de4. The candidate preserves
behavior and shrinks generated WASM, but two paired timing screens establish
no execution gain and retain possible slowdowns. The earlier correction that
commits only documented SREG bits remains in production. No runtime/library,
native binary, vendor definition or default engine change is retained here.

## Candidate and correctness

The masked-retirement identity is:

```text
(current & ~M) | (((old & ~M) | computed) & M)
    = (current & ~M) | (computed & M)
```

The candidate therefore builds only written flag bits in individual resumable
ALU bodies and omits the initial SREG load when the operation has no flag input.
ADC/ROR retain C, SBC/SBCI/CPC retain C/Z, BLD retains T and BRxx retain their
condition. SET retains its old T for the existing work-loss diagnostic. Safe
blocks and cyclic regions retain their original complete-flag handling; this
is not the earlier rejected symbolic constant-folding pass.

A structural fixture checks 17 instruction forms in compatible, full-context
resumable and live-local modes. Baseline passes one/fails two optimization
checks; candidate passes all three. Its direct SREG loads drop from two to one
for ADD/INC and other no-input writers, retaining the final merge read. Consumers
keep their operand reads. All 2325 candidate default/shared-tool tests pass,
including the 296 official-mask/phase/IRQ/RESET checks. This is a software result,
not new physical-device validation. See the
[official mask audit](sreg-retirement-20261026.md).

Across nine catalog firmwares and four policies, all 36 modules validate.
The 18 legacy/full-compatible artifacts stay byte-identical to baseline.
Resumable artifacts shrink 1730–2798 bytes (0.469–0.725%); bounded-region/live-local
artifacts shrink 5450–9123 bytes (2.012–3.138%). Both timing screens reproduce
the same artifact hashes. Private flag spill contents may differ; public
architectural state, time and output stay exact.

## Execution measurement

AMD Ryzen 5 5600X, Windows 10.0.26300 x64, Node 22.22.3, V8 12.4.254.21-node.56.
Native WASM remains 119010 bytes, SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`.
Each pair constructs fresh chips, warms both for 1024 frames, then measures
4096 frames at 48 kHz. Capture calls are timed in 256-frame chunks; construction,
hashing, state comparison and explicit pin draining are excluded. Pin collection
inside the native capture path is included. All six pins are retained.

All runs are serial on the main thread. Side order and identity-control order
are balanced; there are no Workers or overlapping teardown. Heavy tests finished
before timing began. The initial screen has six actual and six baseline/baseline
identity pairs per case; the isolated confirmation has four of each. These
are coupled CPU/peripheral/pin timings, not exclusive subsystem measurements.

Values below are paired median baseline/candidate ratios; greater than one
would favor the candidate. Identity columns compare two copies of baseline.

| Firmware/policy | Initial | Identity | Confirmation | Identity |
| --- | ---: | ---: | ---: | ---: |
| rhythmic / verification | 0.9613 | 0.9966 | 0.9950 | 1.0406 |
| rhythmic / bounded phase locals | 0.9971 | 1.0086 | 0.9897 | 0.9691 |
| lumiere-stereo / verification | 0.9575 | 0.9891 | 0.9891 | 1.0101 |
| lumiere-stereo / bounded phase locals | 0.9796 | 1.0005 | 0.9361 | 1.0531 |

All eight actual medians are below one, with substantial run/control spread.
The first lumiere verification screen is slower in all six pairs. Its exact
loss does not reproduce across screens, so no universal slowdown percentage
is claimed. No stable elapsed benefit supports retaining this optimization;
the cause of the timing differences is not established.

Every warmup and measured pair retains exact PCM, timestamped pins and CPU/
data/EEPROM/Flash/native diagnostic snapshots at each chunk. All measured spans
have active IRQs. There are 160 measured chip captures across 80 pairs, plus 160
warmups. This does not establish browser real-time or underrun acceptance.

## Evidence and replay

[Initial screen](sreg-inputs-20261026.json) and
[isolated confirmation](sreg-inputs-20261026-confirm.json) retain individual
timings, hashes, identity controls and candidate-suite counts. The
[initial harness](sreg-inputs-20261026/initial-harness.mjs) is the exact archived
source used for the first screen. The [structural fixture](sreg-inputs-20261026/structural-check.mjs)
is archived source copied into isolated test locations, not a default test or
standalone entry point. The [candidate patch](sreg-inputs-20261026/candidate.patch)
includes its generated compiler identity for exact reconstruction.

```text
node web-player/scripts/verify-sreg-inputs.mjs --repeats 6 --output build/sreg-input-replay.json
node web-player/scripts/generate-avr-cache-identity.mjs --check
git diff --exit-code b8c34de4 -- web-player/lib web-player/wasm
```

The replay driver materializes baseline and candidate sources under ignored
`build/`, checks the patch, and applies it only to that candidate directory.
Production files are not edited. The restored source graph has compiler ID
`88eaad819aeb1e5ef35029276a0caa4c59724f4fa29b998076e8fdccc06a43b2`, matching
the previously verified 2322-case production checkpoint. No additional full
production rerun is claimed after exact restoration.

The broad register-traffic and exclusive-profiling items remain open. Do not
retry this same transformation as an unmeasured pending optimization. A future
revision needs separate evidence that its generated execution improves. The
overall plan remains 23/30, seven open.
