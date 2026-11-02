# LPX 2/3 kbit/s successive quality rounds

Three registered rounds completed on the established 27-clip corpus at both exact complete-file caps: 54 jobs per round, 162 final PASS receipts. Each round used its immediate predecessor's complete selected streams. No additional search round was inferred from compilation, infrastructure checks or reference replay.

All three rounds fell below the prospective per-round heldout thresholds: +0.01 mean PWM STOI, +0.3 dB summed-energy PWM SER, or +5 percentage points source-period coverage. The actual consecutive-no-clear counter reached three. Smaller admitted numerical gains remain selected.

| Round | Operator | Cap, kbit/s | Changed / 27 | Heldout Δ STOI | Heldout Δ PWM SER, dB | Heldout Δ period coverage, pp |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | pitch_proposals | 2 | 2 | +0.000303 | +0.01839 | +0.214 |
| 1 | pitch_proposals | 3 | 1 | +0.000692 | +0.00986 | +1.282 |
| 2 | spectral_round | 2 | 7 | +0.001761 | +0.00046 | +0.427 |
| 2 | spectral_round | 3 | 9 | +0.000979 | +0.01425 | +0.427 |
| 3 | beam_innovations | 2 | 5 | +0.000511 | +0.02515 | +0.000 |
| 3 | beam_innovations | 3 | 1 | +0.000598 | +0.01245 | +0.427 |

## Final selected streams versus round0 selected streams

| Cap, kbit/s | Changed / 27 | Mean heldout PWM STOI | Aggregate heldout PWM SER, dB | Heldout period counts / source windows |
| ---: | ---: | --- | --- | --- |
| 2 | 12 | 0.707266 → 0.709840 | 3.93068 → 3.97469 | 208 → 211 / 468 |
| 3 | 11 | 0.732917 → 0.735186 | 6.34998 → 6.38653 | 265 → 275 / 468 |

The heldout subset contains ten speech clips at each budget, including its registered quiet/noisy derivatives. STOI membership is fixed from round0; newly missing scores were not dropped. SER uses summed reference/error energy, not an average of decibels. Source-period coverage retains the same source-window denominator; unknown source windows are reported separately in the numeric evidence. The public 2.4-second listening example is excluded from these confirming aggregates.

Per-clip numeric changes, tuning/heldout/negative-control groups, actual byte totals and named operation counters are retained in [the anonymous JSON](campaign-results.json). The score and guards are numerical proxies, not calibrated audibility, perceived-quality percentages or complete pitch preservation.

The decoder arithmetic, rate, sample count, declared target gain, formats and exact byte caps remained fixed. Formats are sparse80 version8/mode15 at 2 kbit/s and v5/P4 at 3 kbit/s. Every selected full output passed the model and both common/v5-only native PCM/PWM checks. Final private sidecars were also replayed through both frozen native receivers.

A private manifest contains all 54 exact final streams, targets and expected PCM/PWM. The subsequent [complete firmware admission](CAMPAIGN_FINAL_FIRMWARE.md) passed all 54: 23 changed streams were freshly linked and simulated, and 31 unchanged streams reused evidence only after full image and timing-context verification. Every complete 32,000-sample output matched its PWM oracle with active interrupts and zero underruns. Host/native PASS alone was not used as an AVR real-time guarantee.

No listening preference or physical-board result is claimed here. No audio, private source identities, paths or fingerprints are included in this report. Publication and main-branch integration remain separate.

[Registered operators and stopping rule](ITERATION_PROTOCOL.md).
