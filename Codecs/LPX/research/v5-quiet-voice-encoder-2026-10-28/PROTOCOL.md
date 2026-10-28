# Frozen complete-speech quiet/voice frontend study

Core epoch: `5b4800f7`; production decoder remains `5c7e0592`. This protocol
is committed before preparing or running the study. No core, settings,
thresholds or weights may change during its source-bound execution. The driver
imports the supplied `--source-root`; it does not copy or edit core files.

## Inputs and finite work

Use the frozen `baseline-v2` manifest: all 49 original speech references,
98 profile groups and 118 actual reset segments. Preserve original 8 kHz mono
PCM16 samples, complete lengths and playback levels in the main mode. Original
control streams, saved complete-chain PCM/PWM fingerprints and numerical floors
remain binding. Sources are not asserted to be independent speakers.

Assign each pair of profiles one source ordinal, in first-appearance manifest
order by its private source key. Two shards use source-ordinal parity so both
profiles stay with one worker. The targeted reference identified privately by
the listening handoff marks both of its profile groups as targeted, not
independent held-out evidence for these new choices. Keep split/cohort labels.

For every preserve-mode segment, call the frozen `encode_speech_voice.encode`
with its corresponding original v5 control, the **whole original chain's byte
count B** as `max_bytes`, pre grid `(0,8192,13926)`, the zero/minimum scale opt-in,
original level, speech metrics and both prepared native receivers. This is
118 * 3 = **354 fresh encoder fits**. Per-segment proportional caps are not
substituted for the complete-recording budget.

The optional, separately labeled `auto-quiet` **research** variant covers only
the four whole sources below 256-count AC RMS: eight profile groups, each
currently one reset segment of at most 64,000 samples. Its one whole-source
power-of-two gain is declared; the target waveform is intentionally different
in level. It encodes a fresh legacy control at that declared target plus the
same three candidates, eight * four = **32 fits**. Never compare those as
unchanged-level gains against the original quiet control. The unchanged-level
original remains separately available. Do not activate an amplification default.
Other gain-one auto cases are identity reuse eligible; do not refit or count
them as additional independent signals. A future segmented quiet source must
not receive independent per-segment gains under this protocol.

## Exactly three whole-chain choices at most

Retain the actual original/control chain, concatenation of returned selected
segments, and concatenation of returned raw segments. No combinatorial mixture,
new pre candidate, reoptimization per budget or changed search objective is
introduced. Duplicate byte-identical chains may share verification but retain
their role labels. Missing segment results make that complete chain null.

A transparent common-decoder wrapper forwards every call unchanged and retains
successfully decoded V5 inputs in first-seen order. The first captured V5 is the
actual core control. Check its bytes and decoded metrics, PCM/PWM voice reports
and objective against the core baseline fields, to 1e-12 for finite scalar
roundoff. This retains the fresh auto control without adding a fit or changing
the core return API. All captured trial streams remain private provenance;
they do not silently add whole-chain choices. Guard exact core bytes because
this capture order depends on the declared implementation epoch.

Freshly decode every original and candidate ordered chain through the integer
model and native common/v5-only receivers. Concatenate only at the actual reset
boundaries, retaining every stored packet tail and every played source sample.
Check original decoded PCM/PWM against frozen saved fingerprints. Recompute
whole-target PCM/PWM SSE/STOI, source-bound PCM and PWM voice proxies, direct
target-PWM voice diagnostics, and one frozen whole-reference VoiceObjective.
No local success alone admits a chain.

For each whole chain, conservative eligibility requires original/control
PCM/PWM SSE/STOI floors, both whole PCM/PWM voice-proxy gates, and objective
nonregression. At full B, failed complete-chain admission falls back to the
whole control if it fits. In auto research that control is the fresh declared-
target legacy chain; if no declared-target control/candidate fits, return null,
not the old quiet chain relabeled as amplified output.

At each original cap `floor(B * percent / 100)`, percent 100/95/90, select the
lowest-objective eligible finite chain and retain the lowest-objective fitting
raw tradeoff separately. All headers, segments, extras, stored tails and padding
count. No fit stays null; it is not proof of encoding impossibility. Reduced
cap rows are finite-pool selection only, not additional fitting. Keep failed
floor flags, absent chains and cap failures visible.

## Preparation, caching and scope

Prepare once before either shard: pin the manifest, source/reference files,
ordered original streams, source/driver/protocol/tests, loaded Python/package
versions, native compiler and all actual library bytes. Build generic common
and compact-only native libraries once; shards never race a compilation.
Guards run before and after records and final completion. Per-record caches
are immutable and tied to that full epoch, mode and source/profile ordinal;
verify completion markers, report and output bytes before resuming them.

Keep all media, paths, original/private identifiers, per-recording fingerprints,
libraries and detailed caches only under an owned ignored output directory.
Standard output contains numeric progress and mode labels only. Public evidence
may retain source provenance and anonymous aggregate results, never private
artifacts. No MIDI, firmware simulation, new stream format, analog claim or
default change belongs to this study. Parent-owned application admission is a
separate stage and never promotes a raw quality tradeoff by playback alone.
