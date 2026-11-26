# LP20 techniques compared with current LPX

Source review, 2026-11-26. The current native LPX baseline used here is `644e19d0`;
the task worktree starts at `50f7a8c6`, which adds the concluded optional
local-noise experiment. No archived program was executed and no new LPX
quality, bitrate or MCU-cycle improvement is claimed by this review.

## Check novelty before adding another search

The recovered LP20 code supports moving expensive decisions to the encoding
host. That principle is already used extensively in LPX:

- `01_ACTIVE_Q0_CODEC/tools/joint_rate.py::trellis` carries LPC/deemphasis,
  brightness, pitch recursion, sparse counts and real bit costs through scalar
  alternatives. `beam_excitation_pcm16.py::optimize` retains equal-length token
  alternatives and uses complete native replay and full-output admission.
- `tools/speech_objective.py` has source-frozen LPC weighting and branch-owned
  weighting histories. `refine_speech_perceptual.py` keeps raw versus protected
  outputs and preserves independent complete PCM/PWM guards.
- `tools/refine_speech_trajectory.py` already keeps exact decoder histories
  through adjacent P4/P6 frames, including joint LSF/pitch/scale decisions.
- [The November 2 beam protocol](../../LPX/research/low-bitrate-speech-2026-11-02/BEAM_PROTOCOL.md)
  and its `beam_innovations.py::search_beam` already keep exact LPC history,
  a 256-code excitation ring, `dd` and `cc`, across continuous legal P4/sparse80
  innovations. This crosses metadata and packet boundaries.
- [Its retained outcomes](../../LPX/research/low-bitrate-speech-2026-11-02/CAMPAIGN_RESULTS.md)
  admit 5/27 changes at 2 kbit/s and 1/27 at 3 kbit/s for the beam round.
  Held-out mean PWM STOI changes were +0.000511/+0.000598 and summed-energy
  PWM SER changes +0.02515/+0.01245 dB. These were below the registered material
  thresholds. They are earlier formats/workloads, not gains on the current
  calls4 eight-file corpus, and do not establish audible preference.
- [The October trajectory pilot](../../LPX/research/encoder-trajectory-pilot-2026-10-28/README.md)
  and its lambda sweep also limit expectations: delayed raw objective gains
  were often rejected, and changing a rate price did not improve the retained
  size/SSE frontier.

Thus a native port or P6 coverage extension of an old LPX search must be described
as such. State diversity, another beam width or another weighted objective alone
does not establish a new useful transfer from LP20.

## Narrow candidates

| Candidate | Actual recovered source | Difference to check | Decoder implication |
| --- | --- | --- | --- |
| Exhaustive small pulse neighborhood | [v48 `quad48.py::quad`](snapshots/v49/LP20-v48/quad48.py) enumerates all 3⁴ neighboring output choices and their interactions | Try four existing current-P6 pulse symbols with three fixed legal finalists each, evaluating all 81 leaves without partial-path pruning. Compare with the same candidate pool in the old exact-state beam and current native pair search. This is a topology/coverage test, not a new beam principle | Existing V9 symbols and complete byte count can remain fixed; only encoding-host work changes |
| Source-envelope + temporal error differences | Inherited v9 `feedback_v7.py::trellis` and `study.py::encode_trial` inside [v52 sources](snapshots/v52/LP20-v52-Z80/sources/) use `w*e² + wd*(e-e_prev)²` | Current LPX already has LPC/perceptual and spectral/temporal objectives. This particular local waveform-error derivative and source normalization differs, but old rejected perceptual searches are mandatory controls | One previous-error value belongs to each host search state; no new MCU state if final choices remain ordinary existing symbols |
| Categorical metric-gradient proposals | Inherited `feedback_v7.py::gradient_stoi/grad_pwm`, `local_pareto.py::sweep`, `refine_joint.py::physical_grad` | Recruit a small legal candidate set using a checked metric sensitivity, then re-render exactly. A differentiable shortcut through integer clipping/quantization is not a valid exact model | Encoder-only if it selects existing pulses/parameters; no decoder gradient or learned table |
| Existing-Rice-priced LSF proposal DP | [v45 `rd44.py::choose/search_frame/allocate`](snapshots/v45/LP20-v45/rd44.py) counts real residual syntax and predecessor scale costs | LPX already has actual-bit Pareto/DP allocation and greedy LSF merges/refits. Only a precisely defined ordered-LSF/native-Rice proposal generator could be a different experiment | Existing decoder syntax can stay; stability, interpolation, actual complete packing and refitted output must all pass |
| Shifted pairs or reverse region visitation | [v48 `quad48.py::run`](snapshots/v49/LP20-v48/quad48.py), [v49 `viterbi49.py::optimize`](snapshots/v49/LP20-v49/viterbi49.py) | An inexpensive order/budget control. The old continuous 20-sample LPX beam already crosses 40-sample pair boundaries, so this is not an unexplored dependency | Encoder-only; synthesize forward from the real current prefix, never run the IIR backward |

The smallest justified next step is a synthetic mechanism check: construct or
find a legal current-P6 four-pulse case for which the existing restricted
pair/finite-beam operators miss a better complete leaf. Check all 81 choices
with independently reconstructed true states and native serialized decode.
Only a demonstrated gap justifies a fixed-budget corpus pilot. Keep the old
whole stream independently of pruning. This review does not launch that pilot
or assert that the gap will occur often enough to matter.

## Respect the actual decoder state

LP20 v49's finite-memory Viterbi operates on fixed output-pattern responses
through a linear model. Current LPX's `LpxAdaptiveDsp.cpp::advance` has ten LPC
histories, a 256-entry pitch/excitation ring, de-emphasis/brightness state,
time-varying coefficients, integer rounding, clipping and nonlinear PWM duty
quantization. Equal recent pulse symbols do not imply equal future output.

Every survivor must retain the real future-relevant state, position and selected
symbols. Coarsely grouping states is a heuristic; exact merging requires equal
future-relevant states. LP20 impulse-response cross terms may help propose
finalists, but cannot replace exact LPX replay. A larger beam can also be worse
under a fixed CPU budget because it visits fewer windows. Measure complete host
time and actual work, including finalist generation, prefix recovery and full
admission; equal trial labels alone are insufficient.

For a new current-LPX candidate, preserve all non-pulse fields when testing a
pulse operator, exact complete bytes and legal P4/P6 symbols. Compare PCM with
its own fresh PCM baseline and PWM with its own PWM baseline. Require native/model
identity, complete continuation, stability, safe level/spectrum, active SSE/STOI,
old-noise, full-band, pitch/clipping and complete-quality admission. Retain raw
and protected results separately. Metrics do not guarantee an audible preference;
use level-preserved listening and unseen speech before a sound-quality claim.

Changing only host search adds no algorithm or table to ATtiny88/ATmega328P.
For changed bitstreams, identical size alone does not prove identical runtime
cycles: any performance/support claim still needs full decoder/interrupt/output
timing validation. This study makes no new AVR timing or hardware-support claim.

## What should stay a separate codec/output experiment

LP20 learned/context dictionaries, pre-expanded gain vectors, sample morphing,
phase/DDS synthesis, adaptive DCT blocks, Huffman/rANS containers and extra
correction layers alter the representation or output stage. Current LPX already
has pitch reuse and scalar pulses. A decoder-free LP20 dictionary improvement
means an unchanged *LP20* dictionary interpreter, not an unchanged LPX receiver.
Count all learned tables and code, especially against ATtiny88 Flash/SRAM.

LP20 v51's 255 PWM patterns and gamma grid are specific to its eight periods per
sample at 7,812.5 Hz and Z80 instruction schedule. Current LPX PWM scoring is the
static integer `pwm()` duty-amplitude transfer; its PCM target excludes PWM.
An optional carrier/filter-aware host scorer is conceivable only after defining
the actual AVR timer/output/filter model. Copying Z80 patterns is not that model.

## Why the historical quality numbers cannot be copied

The v51 source render uses four bin averages per PWM carrier period, 250 kHz,
resampling to 48 kHz and a zero-phase 7 kHz filter. `peak_audit.py` additionally
filters to 3.5 kHz, removes DC, fits global delay (±16 samples at 48 kHz) and
gain, and excludes 10 ms endpoints. The two selected fitted gains are about
1.149 and 1.037. These are modeled, fitted comparisons, not physical analog
recordings or the fixed-reference LPX PCM/PWM metric.

v51 uses two historical examples and per-recording sample books; reported
cross-recording training is not independent multi-speaker validation. Its final
selection uses SNR, rate and peak thresholds while allowing a historical v39
STOI loss. Direct 34 dB output-index Viterbi trajectories are unconstrained,
whereas about 25 dB/6 kbit/s applies to PC-decoded LP4V excluding common tables.

v52 `make_release.py` host-decodes LP4V into one PWM index per sample for preview
ROMs: 62.5 kbit/s. Its standalone index player is 5,027 B; PCM10 player 6,145 B.
The 1,024 B compact-table figure is data-only. Separate old native LPC63 programs
are 16,357/16,298 B, excluding audio; native255 grows to 20,584/20,525 B and its
stored SNR falls. The complete 6 kbit/s LP4V native decoder remains unimplemented.
Supplied emulator tests check a defined opcode subset and modeled port edges;
no physical-board, WAIT/NMI or active-interrupt result was reproduced here.

These boundaries are visible in the original source/README and anonymous tables,
not inferred from a headline. They are the main reason to preserve the history
alongside both the successful and rejected experiments.
