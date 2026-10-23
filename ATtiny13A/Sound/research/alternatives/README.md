# Auxiliary historical source sets

These are distinct research inputs found during a final archive coverage audit.
They supplement the main chronological snapshots; they do not replace the active
HQ4 codec. SOURCE_MAP.json links each set to its original archive and related
development commit. Runtime dependencies, synthetic fixtures and frozen training
parameters are retained; generated firmware, audio and HTML are excluded.

- native-profiles-demo: standalone synthetic source used by the public demo.
- hq3-synthetic-demo: standalone synthetic checks for the decoder-size experiment.
- hq4-alternative-fit: a distinct HQ4 fitting pipeline, including its research results.
- hq3-corrected-rebuild: the fixed rebuild helper recovered outside the release ZIP.

Training these older alternatives was not rerun during import. The source integrity
audit parses their Python and checks their preserved bytes. Use the active codec's
frozen verifier for the current HQ4 firmware.
