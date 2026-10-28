# Final host decoder admission, 2026-10-28

The final decoder source at `5c7e0592e0ac01e15551ef93b2e30343fd08f4a8` passed exact host output, fresh whole-chain quality, and bounded sanitizer admission. `verification.json` contains aggregate results and tool hashes; `sources.json` binds the exact nine decoder files, the 208 copied source/model/header/harness files, and the two audit scripts. The source snapshot was checked against the committed bytes after validation. The updated fuzz driver is pinned independently by SHA-256; this receipt does not imply that driver was already part of the decoder source commit.

- Frozen corpus: 181 cases, 306 unique segments, 1,224 baseline/selected stream instances. Both common and compact-only native layouts match the frozen PCM16 and PWM outputs and the model exactly. Each layout/output domain covers 60,752,116 samples.
- Current selection: 49 cases, 98 profile groups and 49 across-profile groups. All 204 distinct case/chain requests retain exact historical whole-chain PCM/PWM hashes and freshly recomputed original-level quality metrics. The audit checks 2,168 stream-file entries and 3,548 historical evaluation bindings, and freshly compares 244 unique streams across both layouts and output domains (976 comparisons).
- ASan and UBSan: 504 generated inputs and 627,570 mutation/reset cases per layout, 1,255,140 cases total. Common layout rejected 163,247 cases; compact-only rejected 602,788. Both report exact reset behavior, zero sample-cap hits and successful sanitizer child exits with recovery disabled. Rejected counts describe the observed malformed or unsupported inputs; they are not a separate proof of equivalent rejection behavior.

The mutation harness limits each decode to 4,096 samples. The generated speech fixtures cover lengths 1, 19, 20, 39, 40, 159, 160, 180, 200, 220, 240, 260, 280, 300, 319, 320, 321, 500, 641 and 1,024, for both profiles and plain/enhanced compact forms. The new 180–300 and 500 tail fixtures are included. Passing this bounded mutation run is not a claim of exhaustive malformed-input coverage.

## Reproduction and provenance

Use an isolated checkout/snapshot with the decoder inventory in `sources.json`, not a moving working tree. Copy or verify the recorded model, native wrapper, test driver and harness sources before running. The original run checked all 208 copied source files and both audit scripts before and after each process, then repeated those guards and compared the decoder bytes with the source commit. Native libraries and sanitizer executable hashes are retained in the receipt.

From the active codec directory, run the current hash-matched `tests/verify_fuzz.py` under CPython 3.12 with the following arguments, using Linux GCC directly or `--wsl Ubuntu` on Windows. The second command selects the compact-only layout:

```text
python tests/verify_fuzz.py <output-common> --wsl Ubuntu --v3-features 124 --speech --speech-compact
python tests/verify_fuzz.py <output-compact> --wsl Ubuntu --v3-features 124 --speech --speech-compact --compact-only
```

The recorded sanitizer compiler is Ubuntu GCC 13.3.0, with `-O1 -g -std=c++11 -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all` and the feature defines listed in the receipt. Native corpus libraries use the batch-decoder recipe (`-O3 -fPIC -shared -std=c++11` and the same feature defines). The local executable named `g++` actually identifies itself as Clang 24 targeting `x86_64-pc-windows-msvc`; the native results must not be described as GCC results. Python/package/compiler versions and hashes are recorded explicitly.

The frozen-corpus and selected-chain audit scripts are pinned by hash. Repeating their exact totals additionally requires the external private corpus, its frozen output/segment manifest, and the historical selection/cost inventories. The former checks every ordered baseline/selected segment and complete joined output; the latter accepts the local historical study directory, verifies its references and evaluation bindings, and recomputes whole-chain metrics. Those media, private paths, recording identities, and recording/stream/PCM fingerprints are deliberately excluded from these public receipts. This folder is an auditable anonymous result, not a self-contained public copy of the corpus.

## Bounded ring/linear timing evidence

`ring-linear-screen.json` preserves the separate eight-image AVR simulator screen that informed the final compact-only default. It compares two fixed 64,000-sample real controls, one per profile, chosen by the largest prior normal 160-sample conversion window; both ring and linear sources use those identical streams at IRQ loads 0 and +100. The source hashes are specific to those two candidate snapshots. The final header keeps the common layout on ring history, so the screen snapshots must not be presented as identical to the final source inventory.

All eight images play the complete model-exact PWM stream with zero underruns/errors, full timing coverage and queue minimum 386. Linear history saves 8 bytes of full Flash and 20 bytes of static SRAM in each paired image; measured stack margin rises from 920 to 940 bytes. It increases mean wall cycles by 2.85–3.03% and maximum 160-sample window cycles by 2.38–3.11%; the largest linear window is 162,695 cycles. These are measurements from the pinned simulator/runtime recipe and two selected controls, not a whole-corpus timing proof or a physical-board result. Final full diagnostic and production-player admission is maintained separately.

No firmware size improvement, hardware support or audio-quality gain is inferred from the host sanitizer checks. Historical Flash costs are explicitly not reused as costs of the changed decoder.
