# Canonical retained-prefix corpus regression

This package replays the canonical `adaptive_speech_chain.select_candidates`
API over the fixed 118 saved V2 records. It performs no fresh encoding or
refinement. The [protocol](PROTOCOL.md) fixes source levels, common-depth
histories, previous incumbents, full whole-record gates, the three original
byte caps, and the separate complete-player evidence requirement.

`saved_corpus.py` binds private markers, actual streams and immutable local
reports. `contract_saved.py` validates all 118 records and paired prefix1 bytes
without model decoding or whole metrics. `replay_corpus.py` loads frozen V2
primitives from an explicit source root, then only the two promoted canonical
modules from an explicitly committed integration root. It calls the canonical
selector once per record and derives all three cap decisions from those rows.

The driver patches fitting/refinement/build entry points to fail closed. Its
instrumentation only counts calls around the original whole-measurement and
model functions. Each distinct ordered whole chain gets fresh full metrics;
the canonical reset-byte cache avoids repeated native/model verification
within a record. The complete source target is preserved for long nonspeech,
with unsearched resets fixed to baseline.

Use the same pinned Python/package/compiler runtime and single-thread settings
as the original V2 binding. Add the package directory to `PYTHONPATH` if using
a generic `runpy` launcher. The CLI accepts private paths explicitly; no
private paths or stream fingerprints belong in committed example commands.

```text
python -m unittest discover -s <package> -p test_saved_corpus.py -v
python <package>/contract_saved.py --source-root <frozen-root> --study <study>
  --audit <independent-audit> --auditor <frozen-auditor.py> --output <fresh-build-output>
python <package>/replay_corpus.py --source-root <frozen-root> --study <study>
  --audit <independent-audit> --auditor <frozen-auditor.py>
  --selector-root <canonical-root> --selector-commit <explicit-commit>
  --contract <passed-contract-directory> --union-handoff <old-final-handoff>
  --union-proof <old-complete-player-receipt> --shard <0-or-1>
  --output <fresh-build-output>
```

Each parity shard retains both profiles and disjoint records. Attempts, logs,
ordered stream artifacts and detailed results remain private in ignored build
storage. A new selected chain outside the prior fixed union is reported for
separate actual Flash/playback verification; this replay does not assign it a
firmware admission or claim audible improvement.
