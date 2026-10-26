# Verified persistent translation cache, 2026-10-26

The full ATtiny13A renderer now reuses generated WASM across Worker restarts.
Warm construction improves by paired median3.13x/3.10x on the two measured
firmwares, with full Worker readiness improving1.49x/1.48x. Initial misses
cost extra validation and storage. This changes startup only; execution speed,
peripheral timing, native bytecode and the simplified site's default engine
remain unchanged. The combined persistent/region-cache plan item stays open
because region-level retranslation is still missing:22/30 items, eight open.

## Format and correctness

The accepted record contains generated binary bytes and small identity
metadata. The key binds initial Flash/EEPROM, compiler/host source graph,
native runtime bytes, normalized hardware configuration and compiler policy.
Hits retain the complete package executable checks, all512 mapped Flash words,
embedded manifest, memory/table/signature checks and instantiated native ABI.
All inputs are snapshotted before asynchronous work. Each hit creates a fresh
chip; no live memory, queues or self-programmed image is persisted.
Storage failures fall back to ordinary full-device construction. No instruction
or peripheral event calls IndexedDB. See the [full contract](../lib/avr-persistent-cache.README.md).

The first prototype stored a complete JSON package. Its warm lookup was slower
than uncached construction, so it was rejected. The binary record removes
duplicated runtime/firmware/base64/envelope work while reusing the same
executable validator. This is not a relaxed validation or model.

## Controlled construction measurement

In-app Chrome156, Windows10.0.26300, AMD Ryzen5 5600X. No test suite or profiling
ran alongside either timing experiment. After four discarded warmups per
firmware, eight balanced Williams four-position trials use oldA/oldB/newA/newB.
All64 observations per experiment run sequentially in fresh Workers.
Old is ordinary construction through `new Renderer`, with its in-process
translation cache retained. New is a warm persistent lookup through the
production `createDeviceRenderer` factory. The full nominal physical/resumable
verification configuration and conservative CPU policy are identical.

Construction timing starts after module imports; total `readyMs` also includes
Worker startup and imports. Snapshot/hash verification occurs outside the
construction timer. Every observation agrees on native and generated WASM
hashes and full initial state, SRAM/Flash/EEPROM, private native-state view and
pending pin trace. New observations must actually hit persistent storage.
The summarizer independently checks recorded order, all output hashes and hit
activation before calculating paired geometric old/new ratios. Host scheduling,
frequency, JIT and GC remain uncontrolled; no cross-browser guarantee follows.

|Format / firmware|Ordinary median ms|Persistent median ms|Paired construction ratio|Pair range|Whole Worker ratio|
|---|---:|---:|---:|---:|---:|
|Rejected JSON / rhythmic|45.25|83.55|0.535x|0.473–0.583|0.702x|
|Rejected JSON / lumiere-stereo|46.50|90.50|0.521x|0.424–0.582|0.729x|
|Accepted binary / rhythmic|44.00|14.25|3.130x|2.826–3.323|1.487x|
|Accepted binary / lumiere-stereo|45.95|14.65|3.100x|2.704–3.877|1.483x|

Ratios are medians of paired trial ratios, not independently selected medians.
Same-version controls and every individual observation remain in the raw
reports. First-use overhead is visible in the accepted rhythmic warmup:
ordinary50.30ms versus cache miss100.10ms; total Worker107.20→152.80ms.
These are single discarded diagnostics, not a controlled cold-start estimate.
The accepted Lumiere warmups already hit the record seeded by functional tests.
No audio playback throughput or real-time acceptance is claimed.

## Sources, evidence and reproduction

Baseline before this change:`710549d0`. Final compiler graph identity:
`12ec9823263ff26d21081d4fdcebcda86b38be134cc3a96019e29cab647434e9`.
The native runtime remains119010bytes, SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`.
No vendor, firmware or native C/WASM bytes change.
Retained text hashes normalize CRLF to LF; ZIP/native hashes cover raw bytes.

- [Accepted64 observations](persistent-cache-20261026/binary-benchmark.json)
  and [verified paired summary](persistent-cache-20261026/binary-summary.json).
- [Rejected64 observations](persistent-cache-20261026/rejected-json-benchmark.json)
  and [summary](persistent-cache-20261026/rejected-json-summary.json).
- [Rejected source overlay](persistent-cache-20261026/rejected-json-source.zip)
  contains17 source files and `snapshot.json`, pinned to baseline710549d0.
  Extract over a separate checkout of that baseline; normalized file hashes and
  generated compiler identity are retained. It is historical source, not the
  accepted implementation. No MIDI or generated firmware is included.
- [Eight actual browser checks](persistent-cache-20261026/browser.json),
  [test totals](persistent-cache-20261026/test-summary.txt) and
  [source/evidence hashes](persistent-cache-20261026/validation.json).

All1933 default/shared-tool tests pass, no failures or skips. New tests cover
key partitioning, corruption/repair, wrong-image and wrong-policy bytecode with
valid hashes, denied/quota/timeout storage, copied inputs, fresh instances and
actual generated SPM erase/write after hits under compatible, physical and
external CLKI clocks. Browser tests add real binary structured cloning,
LRU/byte limits across connections, concurrent transactions and Worker restarts.
The production Worker runs4096 stereo frames past oscillator startup:
819199.5CPU cycles,798IRQs, zero device faults. Both runs agree on complete
hardware state, muted PCM and nonconstant physical pin audio. These functional
timings overlapped other testing and are not performance evidence. No chip was
programmed or physically measured.

```text
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/*.test.mjs tools/music-startup.test.mjs tools/avr-music-target-core.test.mjs
node web-player/scripts/serve.mjs 8133
```

After tests finish, open `http://127.0.0.1:8133/web-player/tests/persistent-cache-browser.html`
in the in-app browser for functional checks, then
`http://127.0.0.1:8133/web-player/tests/persistent-cache-benchmark.html` for the
sequential timing experiment. Save the visible `#report` JSON after PASS.
Recompute the checked summary:

```text
node web-player/scripts/summarize-avr-cache-benchmark.mjs web-player/reports/persistent-cache-20261026/binary-benchmark.json build/cache-summary.json
```

See primary [HTML storage](https://html.spec.whatwg.org/multipage/webstorage.html#the-storage-interface),
[IndexedDB](https://www.w3.org/TR/IndexedDB-3/) and
[WebAssembly serialization](https://www.w3.org/TR/wasm-web-api-2/#serialization)
documentation for the API choice. IndexedDB supports Workers, transactions and
binary values; `localStorage` is a synchronous Window/string API. Persist bytes:
the current WebAssembly specification rejects storage-cloning a Module.
