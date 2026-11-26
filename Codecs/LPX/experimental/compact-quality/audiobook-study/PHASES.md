# Development first, held-out data locked

Registered 2026-11-26 before any audiobook encoder outcome. This orchestration
addendum complements the source/test-bound `PROTOCOL.md`; it changes no codec
equation, guard, candidate, byte allowance or data-preparation rule.

The prepared cohort contains twenty distinct 20-second waveforms, each with
160,000 mono PCM16 samples at 8 kHz. Preparation considered all twenty-one
available media files, removed exact prepared-waveform duplicates if present,
and selected the first twenty distinct waveforms in the fixed source sort.
Original-file hashes and normalized title/chapter aliases define groups.
The seeded source-only split has twelve development and eight held-out cases,
six/four respectively from each of the two source categories. This establishes
recording/title-group separation, not narrator or underlying-book independence.
All bindings, titles, exclusions, fingerprints and exact preparation commands
remain in the ignored private manifest; originals remain unchanged.

1. Pass the independent Long/composition and source-binding gates. Freeze
   sources, software, options, protocol and test fingerprints.
2. Use the first development case in ordinal order as an infrastructure pilot.
   Audit its immutable native/model/byte/EOF evidence. Reuse that exact pilot
   once; do not rerun it or count it as an additional case.
3. Process all twelve development cases with the same initial Long-enabled
   policy and one joint PCM/PWM encoding target per case. Keep the original
   complete baseline B0, raw return, selected output and all failures.
4. Inspect the complete development result. The eight held-out cases remain
   locked until root explicitly declares the final candidate policy frozen.
   No criterion, weight, threshold or membership change is permitted in the
   registered initial arm. If an additional bounded encoder policy is useful,
   register it separately before implementation/evaluation, retain all initial
   arm outcomes and tests, and label its development evidence as seen data.
5. Freeze the final tested policy, then process each of the eight held-out
   cases once. Do not tune from held-out outcomes, repeat failed scores away,
   substitute sources or merge development and held-out means.

Use at most two separate native worker processes. A codec process owns its
global context; no concurrent threads share an encoder or cold FFT tables.
Use one whole baseline encode and one optional helper invocation per case,
with the independently proved reset-prefix composition. All twenty seconds
remain one continuous Long stream, without independent reset chunks.

The user's requested local listening previews may contain these prepared
source excerpts and their encoded/decoded comparisons in this chat. Generated
WAVs and all media bindings remain ignored; no audio, transcript, identifying
metadata or private payload is committed or publicly uploaded. Local previews
are posthoc demonstrations, not blind listening or independent test samples.

The storage preferences in `STORAGE_GUIDANCE.md` are nonbinding orientations.
They do not add a 128-KiB rejection, widen an existing input API or establish
GiB-scale/AVR playback support. Encoder fitting, decoder differential checks
and possible optimization are engineering work; no trainable decoder model
is invented or claimed by calling this a development corpus.
