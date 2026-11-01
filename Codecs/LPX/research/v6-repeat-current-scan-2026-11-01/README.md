# Current baseline repeat-mask1 survey

The [fixed protocol](PROTOCOL.md) counts complete stored bytes for the original
104 current baseline chains. It reuses the audited cost counter and two retained
raw-bit adapters. This stage performs no audio synthesis or firmware work and
does not establish net complete-Flash savings or native/target output equality.

Run the pure contracts, then freeze the source commit before the corpus command:

```sh
python reproduction/test_serialized.py
python reproduction/scan.py run --baselines "$BASELINES" \
  --source-commit "$SOURCE_COMMIT" --output build/repeat-current/scan-v1
python reproduction/scan.py audit --study build/repeat-current/scan-v1
python reproduction/scan.py publish --study build/repeat-current/scan-v1
```

Paths to this package are relative to the repository root in actual commands.
Supply Python with the existing codec NumPy/Numba dependencies; there is no
download, native build or external program during serialized analysis.
