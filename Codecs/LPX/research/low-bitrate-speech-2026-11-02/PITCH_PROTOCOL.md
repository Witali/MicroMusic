# Source-period proposal round

Registered before candidate evaluation. This is a separate experiment after
the frozen initial 27-clip search. It does not change that search, its source
bindings, the sparse80/v5 syntax or decoder arithmetic. The saved best complete
stream is the protected incumbent at the same actual 2/3 kbit/s byte cap.

Use the original source's existing YIN diagnostic with its established
640-sample windows, 160-sample hop and fixed settings. For each metadata block
(320 samples for sparse80, 160 for v5/P4), choose the nearest source window
center. A pitch proposal is allowed only when that window is marked voiced,
confidence is at least .85, its center is at most 160 samples away, and the
rounded period lies in the codec's legal lag range 18..145. The mask is fixed
from the source before looking at any candidate's pitch. Unknown or out-of-
range periods do not become guessed voiced targets. The diagnostic is not
claimed to be a true-F0 oracle.

There are exactly three new complete candidates, corresponding to legal
gain floors 8, 10 and 12. At each masked block test the source-period integer
lag and its legal neighbors -1/+1, the original scale plus/minus two legal
codes, and every legal gain from the chosen floor through 14 in steps of two.
This is at most 60 parameter fits per masked block. Each fit exhaustively
chooses the existing position/sign innovations through the unchanged exact
integer closed loop, with the initial round's clipping-aware proposal loss.
Replay the winning block and count that additional work. Keep the incumbent
parameters and innovations for unmasked blocks, replaying them with the real
incoming state. Keep spectra and header filters fixed. This round requires
brightness zero, as in the frozen initial search.

Serialize and save every complete contender before the next one. Reconstruct
it independently through both native C receivers using the exact v5/P6
sparse80 bridge when needed, and compare all native/model PCM/PWM samples.
The actual complete file must fit the original cap; no length, source level,
playback rate or output normalization changes are allowed.

Score complete PCM/PWM with the same source-frozen voice/noise objective and
the same nonregression guards relative to the saved incumbent: full SSE,
STOI, fixed-source period tolerance counts and clipped sample count. The
incumbent remains available even if every pitch-constrained contender fails.
Save the raw results and their rejection reasons; a better period count alone
does not prove better sound. Report numerical gains separately from listening
and full active-IRQ firmware admission. Do not relax the guards after seeing
the round's results.

Evaluate the public example first as tuning, then the same frozen corpus.
Do not adjust the mask or gain floors in response to heldout results. This
round is not another decoder mode or a new default. Its acceptance and whether
it counts as a clear improvement belong to the parent study, not a boolean
claim based only on changed bytes.
