# Independent saved-output postcheck

This post-outcome code is separate from the frozen seven-file producing recipe.
It performs no DP, model decoding, quality measurement or native execution.
It reopens input/artifact/source bindings, validates every complete tuple's
integer costs, all original and added whole gates, all 180 decisions, exact
new-study cache keys/creating events, native/model coverage counts and both
within-arm and context-union results. It relies on the producer's fresh native
checks; it does not independently replay them.

```text
python -m unittest test_chain_saved_audit
python audit_saved.py --root PRODUCER_ROOT --prepared PRIVATE_PREPARATION --run PRIVATE_RUN --output PRIVATE_AUDIT --public ANONYMOUS_EVIDENCE
```

Outputs must be fresh. Only anonymous metrics/classifications and source-code
hashes enter the public evidence directory. Input/stream/native bindings and
their fingerprints remain in the private postcheck receipt.
