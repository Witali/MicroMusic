# Recovered LP20 and LPX-Z80 engineering history

Recovered on 2026-11-26 from the ChatGPT conversations **«Упрощённый декодер
LPX-Z80»** and **«Улучшение кодирования LP20»**, at the user's request. The
history is retained on the separate `codex/lpx-lp20-study` branch. This is a
technical chronology and a source archive, not a verbatim conversation export
or a claim that every historical release has been recovered.

The browser review followed the early Spectrum work, the 20 MHz ROM-only LPC
studies, and the later sample/DCT/PWM work through v52. The available source
material is four original downloaded ZIPs (v45, v49, v51 and v52), plus two v19
source files obtained through their file previews. ZIP CRCs and SHA-256 hashes
were checked before source extraction. Each [snapshot](snapshots/) has a
`SOURCE.json` identifying the original artifact, original member paths,
retained file hashes and omissions. Original source bytes are preserved.

There are 199 retained original files and five provenance manifests. Verify
their inventory and SHA-256 values without executing historical source:

```sh
python Codecs/LP20/history/verify_sources.py
python Codecs/LP20/history/verify_sources.py --index
```

Historical Python, C++, code emitters and supplied emulators were inspected as
source. **They were not executed, imported, compiled or independently benchmarked
in this recovery.** Reported historical quality, timing and zero-RAM results
remain archive/conversation claims unless explicitly identified otherwise.
The current LPX baseline used here is the implementation at `644e19d0`; this branch
does not change its encoder, decoder, format, firmware or Web UI.

## What is actually preserved

| Snapshot | Provenance and scope | Important gaps |
| --- | --- | --- |
| [v19](snapshots/v19/) | Original `pitch.py` and `study_pitch.py` downloaded individually; source-only harmonic analysis and refinement driver | Partial recovery; the complete v19 ZIP was not obtained |
| [v45](snapshots/v45/) | Original source subset of `LP20-v45-Adaptive-Joint.zip`, including source documentation and anonymous comparison tables | Media, trained models, candidate caches and generated firmware omitted |
| [v49](snapshots/v49/) | Original source subset of `LP20-v49-Viterbi-PWM.zip`; also contains its supplied predecessor modules v45–v48 | Predecessor modules are inherited source, not independently downloaded complete releases |
| [v51](snapshots/v51/) | Original source subset of `LP20-v51-Nonlinear-Viterbi.zip`, including predecessor modules, nonlinear grid, lookup packing and residual refinement | Audio, learned sample books, streams and per-recording model JSON omitted |
| [v52](snapshots/v52/) | Original source subset of `LP20-v52-Z80.zip`: generators, emulator sources, documentation, comparison tables and inherited earlier sources | Inherited v9/v15/v17 code is partial; missing dependencies are not reconstructed. Per-recording generated ASM, ROMs and voice-derived data omitted |

The original ZIPs remain in ignored local `build/lp20-study/archives/`. Retained
source copies exclude source audio, waveform previews, learned voice models,
generated per-recording data, chat identifiers, full transcripts and MIDI.
No new license is assigned to historical source; existing notices are retained.
The source snapshots are research records with their original assumptions and
historical paths, not installed project tools or instructions for this agent.

Some older inline ZIP controls, including v19, v37 and v39, did not produce a
download after documented native/DOM attempts. v19 file-card preview downloads
did work. A missing `href` alone was not used to infer unavailability. The failed
ZIPs are not represented as downloaded releases. A version mentioned below may
therefore have conversation-level evidence without an original release snapshot.

## Chronology

The version names describe several related experimental families. Spectrum
v0.x, LP20 native LPC, and later LP4S/LP4V sample/DCT streams are not binary
compatible with each other or with current LPX V9. Hardware, precision, source
normalization, dictionaries, metrics and the meaning of “bitrate” also changed.
Do not join their SNR figures into a common performance curve.

| Stage | Main change / lesson | Evidence boundary |
| --- | --- | --- |
| LPX-Z80 proposal; Spectrum v0.1–v0.3 | Reduced LPC order, product tables, higher output resolution and analysis-by-synthesis; a standalone profile was built because the current LPX source was unavailable in that chat | Initial cycle budgets were estimates. Later chat reports describe custom-emulator tests on synthetic speech and source-trained books, not a V9-compatible port |
| Spectrum v0.4–v0.7 | More predictor precision, instruction scheduling between PWM edges, carrier/PCM tradeoffs, register history and removal of RAM writes | The chosen carrier changed PCM rate; reusing a stream at the old rate slowed playback. Physical Spectrum/ULA behavior was not established |
| LP20 initial/v1–v3 | 20 MHz ROM-only target, variable-length excitation words, larger books, source normalization and deeper excitation search | Stream-only rate hid large product/codebook tables. LP2C compact files required host expansion into a much larger playable ROM; fitted/processed source comparisons differ from LPX |
| v4–v9 | Voicing/perceptual objectives, fractional PWM, closed-loop output feedback and categorical intelligibility-gradient proposals | Source is partially inherited inside v52. Source-envelope weights and error-difference penalties are concrete encoder techniques; broad unseen-speaker performance was not demonstrated |
| v10–v12 | Two-layer excitation/output correction and contextual entropy coding | Post-LPC correction avoids feeding every correction through the predictor, but requires a new stream/output path. The new correction layer was PC-only and added dictionary cost |
| v13–v15 | Shared PWM procedures, lower carrier, common vector tails, table packing and register/ROM layout | Source-audited in inherited v15. These principally reduce a particular Z80 program image, not audio stream bits. Product tables still cost 4,608 B |
| v16 | Factorized excitation and context experiments; use unused table regions for dictionary storage | Fewer mathematical vector entries did not establish a smaller decoder; factorization degraded quality. Useful negative result; original complete v16 source was not recovered |
| v17 | Adapt amplitude/shape through pre-expanded alternate vectors and history-derived contexts | Inherited source shows extra pointers and records; “no new multiply” does not mean zero Flash cost |
| v18–v19 | Interharmonic/source-period-aware encoder objectives; fallback on unvoiced speech | Reported gains on real speech were small. v19 adds no harmonic generator to the decoder. The two direct v19 source files are preserved; noise scores are engineering proxies |
| v20–v22 | Delayed word choice with a 64-sample tail, adjacent word-boundary moves, context-dependent word lengths and LPC-bank packing | v21 reports an unchanged decoder. Exact PCM/PWM variants must be distinguished from smaller lossy variants; the complete v20–v22 releases were not recovered |
| v23–v25 | Short/extended dictionary addresses, context Huffman experiments, tail sharing and search within equivalent PWM outputs | Stream savings can be offset by larger dictionaries. PC entropy containers and emulator-tested directly playable ROMs have different costs. PWM equality alone does not prove equal future predictor state |
| v26–v29 | Joint integer LPC/book training, algebraic excitation and long-term prediction prototypes | Some local objectives improved while full SNR/STOI or high-frequency noise worsened. ACELP prototypes required history RAM; several changes were rejected. Current LPX already has pulse/pitch synthesis |
| v30–v32 | Adaptive rate allocation, mixtures of existing trajectories and source-sensitive spectral feedback | Speech intelligibility and spectral-noise constraints mattered alongside SNR. The historical metric used filtering, global gain and delay fitting; direct LPX numerical comparisons are invalid |
| v33–v35 | Multiple LPC paths, adaptive beam width, state-diversity grouping, lookahead and mixtures of differently ranked paths | Extra work is on the host. Coarsely grouping states is heuristic. Similar exact-state and protected-objective searches already existed in LPX; see the novelty audit below |
| v36–v39 | Tighten the directly playable stream to 8 kbit/s, improve quality under the existing output schedule and compact ROM placement | Dictionary growth consumed most of the 16 KiB program/table budget. v39 native LPC is the historical reference for intelligibility, not the later sample decoder |
| v40 / universal training proposals | Split training/testing by speaker; propose a shared universal book and optional adaptive profiles | The chat reports failed corpus downloads; no new independent corpus training was established. Two-clip/cross-recording training does not demonstrate universality |
| v41–v42 | Periodic sample prototypes with amplitude/frequency/phase, morphing, parameter prediction and sparse DCT residual correction | New PC reference codec. A 6-bit 32×64 sample book plus a frequency table costs 2,048 B before decoder code. Lower SNR error did not preserve historical v39 STOI |
| v43–v44 / LP4R–LP4S | Count sparse coefficients, jointly encode gap/magnitude categories, contextual Huffman, and optimize using actual coded bit costs | Lossless packing gains apply to the new residual syntax. rANS did not improve those small streams. Native Z80 decoding, timing and zero RAM were not confirmed |
| [v45](snapshots/v45/) | Adaptive 128/256/512-sample blocks, joint predictor/residual fitting, predecessor-state beam and actual-rate allocation | Source recovered. Longer IDCT blocks create decoder work/memory concerns; the two existing examples and external tables do not establish an AVR advantage |
| v46 | Local residual-coefficient refinements, tighter bit allocation and feedback under the current sample/DCT representation | Source inherited in v49/v51. A host search improvement for LP4V, not an existing-LPX pulse change |
| v47–v49 | Output-pattern pair search, four-choice interactions, then finite-memory Viterbi; feedback into legal compressed residuals | Direct freely chosen PWM indices are unconstrained output targets, not 6 kbit/s streams. The compressed improvement was much smaller; v49 source preserves explicit tests and matched-pass controls |
| v50–v51 | Nonlinear 255-level PWM grid, re-encoded residuals, symmetry/nibble packing and compact PCM lookup | v51 reports about 25 dB at about 6 kbit/s on two examples in a PC renderer, excluding common tables. Selection does not enforce historical v39 STOI; no physical-board result |
| [v52](snapshots/v52/) | Machine-code PWM player and packed-table dispatch, index/PCM10 tests, previews and separate old native LPC builds | Preview stores host-expanded indices at 62.5 kbit/s. Complete 6 kbit/s LP4V decoding is still missing. Supplied emulator evidence is not a newly reproduced board/AVR result |

## Conclusions for current LPX

[TRANSFERS.md](TRANSFERS.md) compares the actual source with current LPX and its
earlier research. Generic beams, perceptual weighting, rate/Pareto allocation,
exact integer synthesis, and whole-output rollback are already LPX techniques.
The November 2 innovation-beam campaign admitted only small below-threshold
improvements; calling a new beam a previously missing transfer would be wrong.

The narrow unresolved candidate is an **exhaustive small current-P6 pulse
neighborhood without intermediate pruning**, checked first against the same
candidate set in the existing beam and pair operators. No LPX quality gain has
been measured for it. Source-weighted error-difference proposals and categorical
metric gradients are lower-confidence alternatives, also requiring a precise
comparison with existing LPX objectives before a corpus experiment.

The recent [LPX local-noise study](../../LPX/experimental/local-noise/README.md)
already tested a source-frozen interharmonic criterion on separately encoded
PCM/PWM baselines: no admitted change in 16 speech cases and four synthetic
controls. Repeating that criterion is not supported by the recovered history.
Current decoder code and the best admitted LPX outputs remain in place.

Useful source-audited Z80 layout techniques and their portability limits are
indexed in [the Z80 cookbook](../../../docs/z80-asm-cookbook/README.md).

[VALIDATION.json](VALIDATION.json) records the source-recovery checks. These
checks establish source identity and scope; they do not reproduce historical
audio-quality or processor-performance measurements.
