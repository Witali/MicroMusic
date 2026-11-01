# Saved V1 fixed-pool chain allocation

This package prepares a separate experiment described by [PROTOCOL.md](PROTOCOL.md).
No mixture outcomes are present. Integration review is required before native
preflight or real DP/whole metrics. Metadata-only preparation is permitted after
the recipe is committed; it performs no decoder or allocator calls.

Run the pure synthetic/mocked contracts with this directory and the active
codec tools directory on `PYTHONPATH`:

```text
python -m unittest test_chain_rate_study
```

Use argument-supplied local paths, fresh ignored build outputs and single-thread
numeric libraries. The original V1 root supplies its immutable `export-v1`, both
terminal profile workers and their original receipts. It does not supply newer
anchor-study pools.

```text
python prepare_chain_study.py --source-root PRODUCER654 --v1-root ORIGINAL_V1_RESEARCH_ROOT --v1-export CLOSED_V1_EXPORT --native-cases ORIGINAL_NATIVE_CASES --output PRIVATE_PREPARATION
python run_chain_study.py preflight --manifest PRIVATE_PREPARATION/manifest-private.json --output PRIVATE_PREFLIGHT
python run_chain_study.py run --manifest PRIVATE_PREPARATION/manifest-private.json --preflight PRIVATE_PREFLIGHT --output PRIVATE_RUN
```

The source/model/native bridge is explicit and source-stable. The run forbids
encoding/refinement, new v5 packing, native builds and subprocess launches.
Synthetic preflight constructs tiny fixed fixtures before this guard; it uses no
corpus input and is separately charged. Deterministic decoder LPC interpolation
for fresh model checks is allowed; coefficient fitting/search is forbidden.

The original five recipes remain protected. Every arm calls exact DP once at B
and contributes at most three complete tuples. On a resource limit, retained
callback cap winners remain visible with nonexact labels. All added tuples must
pass fresh complete-record native/model/quality checks. The data/score optimum
does not imply a whole-admissible, audible or firmware-size optimum.

`summary.json` and `rows.json` contain anonymous numeric results in private build
output for review. Bindings, input paths/hashes, retained ID recipes and cache
provenance use `*-private.json`; do not stage them. There is no automatic public
export or target-image action. A failed attempt is preserved and never restarted
silently under the same path.
