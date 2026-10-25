# Rejected straight-line constant folding

The dedicated pass is rejected and removed from production. It is correct under
the tested model, but the small size reduction and noisy timing results do not
justify another browser-side optimizer/dependency. The generator, runtime and
isolated-loader file inventory are restored exactly to `106d92a`. Native WASM
remains SHA-256
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.
The existing optional Binaryen packaging pass remains available.

## Candidate and scope

An experimental `foldBlockConstants` option symbolically evaluates straight-line
generated i32 ALU fragments before block-local index remapping. It tracks local
constants, individual known bits and snapshot identities of the32 register bytes.
This exposes known carry/zero bits without assuming the whole incoming SREG is
known. Register stores are retained. Constant temporary assignments may disappear,
but local5 remains the live SREG output. Facts reset at each block entry.

Only bounded register-file memory accesses are accepted; signed byte reads and
store truncation retain WASM semantics. Unsupported operations, memory targets or
stack shapes return the entire original fragment. Numeric folding uses i32 wrap
and modulo32 shifts. No AVR opcode interpreter, runtime checks, new regions,
function calls or native timing changes are added. This pass parses the generated
ALU byte fragment at translation time; the independent phase-local annotation
pass remains unchanged and does not parse bytecode.

The option enters cache identity and validates precompiled admission. Existing
phase-local liveness, package loading and SPM recompilation were exercised.
Default translation output remains byte-identical to the historical generator.

## Validation and size

All1660 candidate Node tests passed, zero skips (110.57s). New checks compare
665 constant operation/operand combinations plus five EQZ cases against actual
WASM execution, including wrap, signed/unsigned comparisons and shift counts
0/31/32/-1. Signed-byte/alias cases,200 deterministic mixed expression trees,
unsupported shapes and SREG live-out are checked independently of AVR lowering.
CPU checks cover all256 input SREG values, known ADD/ADIW/ASR/SWAP/BST/BLD and
chained SBC/CPC, every half-phase/adjacent1ps deadline, short public exits,
phase-local composition, host edits, cache isolation, package execution and SPM
under a held source.

The13-workload matrix retains26 exact PCM/state/pin runs and168 checkpoints,
including three firmwares, direct kernels, internal/external20MHz, /1,/256 and
active ADC. All static ALU fragments use the supported subset; none fell back
as unsupported. The matrix checks all13 default binaries against `106d92a`.

| Physical firmware | Raw CPU bytes | Folded bytes | Raw/folded code section |
| --- | ---: | ---: | ---: |
| rhythmic | 387264 | 386169 | 334373 / 333130 |
| lumiere-stereo | 391150 | 390015 | 338039 / 336756 |
| hq4-chego-tiny | 406944 | 406153 | 352935 / 351997 |

Whole modules shrink0.19–0.29%. The kernels save four code bytes but grow137
whole-file bytes because of the added diagnostic manifest. This is not a claim
of uniformly smaller modules. Ordinary generation is unchanged. The requested
HQ4 alias resolves to actual `hq4-chego-tiny` with its exact Flash hash recorded.

## Interaction with automatic Binaryen optimization

The same pinned Binaryen133/executable hash and conservative import-preserving
flags optimize both versions independently. No execution timing is mixed into
this static comparison. The resulting code sections differ; the manual pass is
not completely redundant with these Binaryen invocations.

| After `-Oz` | Raw generator + Oz bytes | Manual-fold + Oz bytes | Additional whole-file saving |
| --- | ---: | ---: | ---: |
| rhythmic physical | 115381 | 115329 | 52 |
| lumiere-stereo physical | 117084 | 116712 | 372 |
| HQ4 physical | 127338 | 126867 | 471 |

The code sections shrink199/506/634 bytes respectively; manifest differences
remain part of the whole-file figures. O3 comparison also retains exact code
hashes/sizes. This does not prove how V8 optimizes either binary or establish
an execution-speed gain.

## Timing and decision

Eight balanced four-label trials and four warmups per label use one unchanged
native Module and shared CPU Modules within identical-binary pairs. Instances
are fresh. GC runs after construction, outside execution timing; construction,
generation, compilation, snapshots and hashing are excluded.

| Physical case | Old identity median | New identity median | Cross median | Faster trials |
| --- | ---: | ---: | ---: | ---: |
| lumiere-stereo | 0.959 | 0.957 | 1.022x | 7/8 |
| HQ4 | 1.002 | 0.913 | 1.011x | 5/8 |

Ratios above one favor the candidate. Identity variation exceeds the proposed
gains: individual controls span0.833–1.159 for Lumiere and0.769–1.194 for HQ4.
The64 timed runs,32 discarded warmups and1152 exact checkpoints do not prove
a steady speed improvement. The rest of the performance matrix was not run;
`complete:true` describes only the selected two-case screen. No browser,
cold-start, working-memory or audio-underrun improvement is claimed.

The implementation requires a dedicated symbolic optimizer and another loader
dependency for limited savings. Combined with the unproven speed benefit, that
is insufficient reason to retain it in production. This is an engineering
decision, not proof that all constant propagation is useless.

## Restoration and next direction

The compiler/runtime and isolated-loader inventory are restored. Three retained regression checks cover
constant-heavy ALU chains for all256 initial SREG values, exact public/physical
exits and re-entry after host register edits. They use ordinary blocks versus
the unchanged individual-instruction path. All1655 restored tests pass, zero
skips (87.02s). Restoration hashes and full outputs are retained.

Next investigate bounded direct-control-flow regions that amortize register
loads/flushes and native clock calls across loops, with staged register writes
and all flags preserved initially. This is an unimplemented design direction;
it must retain clock-before-commit, external-entry fallback, count/event/phase
guards and exactly-once reset/fault behavior. The full hardware plan remains
21/30 complete with nine open items.

## Reproduce

```sh
node web-player/reports/block-constants-20261025/rebuild-candidate.mjs
node web-player/reports/block-constants-20261025/rebuild-candidate.mjs --with-optimizer
node web-player/reports/block-constants-20261025/verify-evidence.mjs
```

The isolated helper reproduces all13 recorded CPU binaries byte for byte,
without installing the rejected implementation. The second command also
reproduces all six O3/Oz code hashes using the pinned SDK. [Candidate sources](block-constants-20261025/candidate-sources.json),
[timing](block-constants-20261025/screen.json),
[parity](block-constants-20261025/validation.json),
[optimizer comparison](block-constants-20261025/optimizer-comparison.json),
source snapshots, patch and both full-suite logs are archived. The prototype
option is not a current runtime API.

Primary semantics: [WASM numeric operations](https://webassembly.github.io/spec/core/exec/numerics.html),
[WASM instruction execution](https://webassembly.github.io/spec/core/exec/instructions.html),
[AVR manual](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf).
Existing Microchip device definitions, flags and original AVR cycle counts
remain unchanged.
