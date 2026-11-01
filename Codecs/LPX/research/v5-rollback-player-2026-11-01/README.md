# Current-source rollback target comparison

The [four-row protocol](PROTOCOL.md) and adapter are preparation only. No native
reference, build or simulation has run. Execution waits for explicit integration
confirmation of the final frontier handoff and source review.

Run from the repository root only after that confirmation, using fresh private
outputs and locally supplied toolchain/runtime paths:

```sh
python Codecs/LPX/research/v5-rollback-player-2026-11-01/reproduction/player.py prepare \
  --selection "$USEFUL_TUPLES" --audit-root "$AUDIT_ROOT" \
  --native-cases "$NATIVE_CASES" --source-commit "$ADAPTER_COMMIT" \
  --avr-bin "$AVR_BIN" --observer "$ROM_OBSERVER" \
  --observer-receipt "$ROM_OBSERVER_RECEIPT" --lib "$SIMAVR_LIB" --wsl Ubuntu \
  --output build/rollback-player/prepared-v1
python Codecs/LPX/research/v5-rollback-player-2026-11-01/reproduction/player.py measure \
  --handoff build/rollback-player/prepared-v1/handoff-private.json \
  --output build/rollback-player/measurement-v1
python Codecs/LPX/research/v5-rollback-player-2026-11-01/reproduction/player.py aggregate \
  --handoff build/rollback-player/prepared-v1/handoff-private.json \
  --output build/rollback-player/measurement-v1
```

The adapter uses the existing ROM builder and strict current-source proof
reopener. Historical fixed-study guards remain unchanged. Four new current links
and full IRQ-active runs establish any later target admission; source identity
alone does not. Portable C remains selectable, with no C real-time claim.
