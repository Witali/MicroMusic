# Synthetic mechanism validation

This records the initial synthetic validation stage on 2026-11-26, before the
speech comparison authorized in [SPEECH_PROTOCOL.md](SPEECH_PROTOCOL.md).
The frozen four-pulse operator passed three synthetic tests. This stage did
not run speech search or an audible-quality comparison. The protocol remains at SHA256
`400f4202fd0080fa4fb7f7a716b0420ef4045394ba8336ca13ece4874d334e5b`.

A deterministic adversarial source uses a generated 1,281-sample decoder trace
whose first 320 samples are replaced with the incumbent trace. This deliberately
creates disagreement between prefix and unchanged-tail loss; it is not a speech
model. Seed 0 yields the following frozen pools for frame 0:

| Pulse | Seven-bit wire symbols |
| --- | --- |
| 0 | 118, 116, 119 |
| 1 | 32, 19, 33 |
| 2 | 19, 27, 18 |
| 3 | 4, 6, 5 |

The exhaustive restricted-pool winner is `(116, 33, 18, 4)`, with complete PCM
SSE 117,833,156. Same-pool prefix greedy, width 2 and width 4 all discard this
leaf and finish at `(118, 32, 19, 4)`, with SSE 399,466,972. This establishes one
real recurrence example of lost combinations after prefix pruning. The controls
rank prefixes while the exhaustive operator ranks complete unchanged suffixes:
this combines search topology and objective/lookahead, and does not isolate the
benefit of removing pruning alone. It does not establish a global optimum or a
useful quality gain for speech.

Across the four complete frames, all 324 leaves were independently decoded by
the full model. The 320 unique changed streams plus the baseline were checked
against BOTH fixed C native reference receivers for complete PCM and PWM. The
receivers use the explicitly labeled existing v8-to-v5/P6 bridge and validate
native EOF, counts and errors. They do not directly parse Sparse80.

The other tests cover deliberately nonminimal legal Rice spectrum spelling,
all original non-pulse bits, protected partial final frames, a real final
one-sample tail, nonzero brightness, changing pitch feedback, clipping and
invalid reference/oracle failure. A generated changed raw proposal remains
available even when the protected baseline has zero loss. Entirely partial
streams of 1, 79, 80, 81 and 319 samples produce no editable region.

The run used Python 3.12.10 and NumPy 2.5.4, completed in 5.531 seconds, and
made 974 PCM/PWM requests to each unchanged native receiver. Full counters and
source hashes are retained locally under ignored
`build/compact-quality/sparse2/mechanism-tests.json`. Timing includes this small
synthetic suite only and cannot predict speech encoding time or MCU load.

Reproduce after explicitly building the reference servers described in
`README.md`, with the already available codec dependencies:

```powershell
python Codecs/LPX/experimental/compact-quality/sparse2/test_mechanism.py --packages C:/Work/MicroMusic/build/codec-python
```

## Predecessor binding limitation

The original November 2 campaign is still retained locally: 27 declared
32,000-sample targets, 54 initial streams and 162 round best pointers. All 162
pointer hashes and admitted metadata checks passed, including 81 Sparse80
pointers across the three rounds. Source and prepared-target hash checks against
all 38 tracked public WAVs found no match. No private source identity, path,
fingerprint or target is included here.

The public Chego fixture is independently bound to its existing sidecar:
307-byte v8 stream, 9,831 samples, declared preserve-level source recipe.
The public Bread low15 stream is 417 bytes for 19,200 samples, but its playback
manifest alone does not prove the encoder's target normalization recipe.
Neither is described as the campaign's final round-3 best. This initially
identified public-source gap is not a restriction on already authorized local
private research. [SPEECH_PROTOCOL.md](SPEECH_PROTOCOL.md) resolves the comparison
by using the exact saved final round-3 strict2k streams and their pinned integer
targets locally. Private source names, hashes, paths and payloads stay ignored;
retained results use anonymous ordinals and numerical summaries. No alternate
public-only or fresh round-0 baseline replaces those stronger predecessors.
