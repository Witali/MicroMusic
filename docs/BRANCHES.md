# Branch catalog

Local snapshot: 2026-11-26. Covers local branches and remote-tracking refs already present in this clone; no network refresh was performed.

Descriptions state the branch purpose when recorded. Other initial descriptions name the latest recorded work; refine them when resuming that branch. Availability in `origin` means a local remote-tracking ref exists and does not certify current server state. A listed branch may be an experiment or retained history; this table does not assert merge or release status.

Refresh from the main worktree with `python tools/update-branch-catalog.py --date YYYY-MM-DD`. Edited descriptions are preserved. Update this catalog when branches are created, renamed, deleted or repurposed, and commit the documentation separately.

Branches: 229. Symbolic aliases such as `origin/HEAD` are excluded.

| Branch | Available refs | Short description |
| --- | --- | --- |
| `main` | local, origin | Integrated project baseline and GitHub Pages source. |
| `codex/add-i8080-schematic` | local, origin | Latest recorded work: Document Intel 8080 tester schematic |
| `codex/arduino-nano-lpx-page` | local, origin | Latest recorded work: Document speech assets and reproducible compression recipes |
| `codex/arduino-speech-player` | local, origin | Latest recorded work: Add Arduino speech selection and firmware downloads |
| `codex/attiny13a-analog` | local, origin | Latest recorded work: Add ATtiny13A comparator and in-WASM ADC trigger routing |
| `codex/attiny13a-analog-deadline` | local, origin | Latest recorded work: Test analog input deadlines across generated CPU blocks |
| `codex/attiny13a-deadline-cache` | local, origin | Latest recorded work: Measure deadline cache against actual device baseline |
| `codex/attiny13a-device` | local, origin | Latest recorded work: Design conservative same-state scheduler deadline caching |
| `codex/attiny13a-device-build` | local, origin | Latest recorded work: Use official ATtiny13A symbols in stereo firmware tooling |
| `codex/attiny13a-device-system-tests` | local, origin | Latest recorded work: Verify asynchronous reset aborts an in-flight OUT |
| `codex/attiny13a-nvm` | local, origin | Latest recorded work: Add ATtiny13A EEPROM and self-programming Flash controller |
| `codex/attiny13a-package` | local, origin | Latest recorded work: Package ATtiny13A firmware and WASM with integrity checks |
| `codex/attiny13a-power-device` | local, origin | Latest recorded work: Integrate explicit supply profiles with ATtiny13A scheduling |
| `codex/attiny13a-power-reset` | local, origin | Latest recorded work: Model ATtiny13A power-on and brown-out reset events |
| `codex/attiny13a-system` | local, origin | Latest recorded work: Model ATtiny13A sleep domains and wake deadlines |
| `codex/attiny13a-timer0` | local, origin | Latest recorded work: Add event-scheduled ATtiny13A Timer0 peripheral |
| `codex/attiny88-board` | local, origin | Latest recorded work: Merge current main with ATtiny88 Micronucleus board support |
| `codex/attiny88-music` | local, origin | Latest recorded work: Correct PWM initialization and ATtiny13A stereo register mapping |
| `codex/attiny88-universal` | local, origin | Latest recorded work: Use verified universal ATtiny88 images in the web player |
| `codex/attiny88-universal-all` | local, origin | Latest recorded work: Sync independent main changes before UM88 integration |
| `codex/avr-audit` | local, origin | Latest recorded work: Merge current main and preserve AVR synthesis extensions in the audited core |
| `codex/avr-execution` | local, origin | Latest recorded work: Refresh AVR benchmarks for merged six-channel firmware |
| `codex/avr-optimization-tests` | local, origin | Latest recorded work: Verify AVR optimization candidates and long-run timing |
| `codex/avr-speed-study` | local, origin | Latest recorded work: Record verified AVR integration with current main |
| `codex/avr-to-wasm` | local, origin | Latest recorded work: Preserve historical report replay after metadata redaction |
| `codex/avr-wasm` | local, origin | Latest recorded work: Add verified portable Windows development toolchain setup |
| `codex/background-playback` | local, origin | Latest recorded work: Allow player audio to continue in background tabs |
| `codex/background-playback-publish` | local, origin | Latest recorded work: Allow player audio to continue in background tabs |
| `codex/cancion-del-mariachi` | local, origin | Latest recorded work: Link the home page to the minute Mariachi arrangement |
| `codex/cleanup-reflog-clki-input-364c26e7b980` | local | Latest recorded work: Add timestamped ATtiny13A CLKI input queue |
| `codex/cleanup-reflog-import-lpx-7b28e110` | local, origin | Latest recorded work: Restore missing synthetic LPX4 regression fixtures |
| `codex/cleanup-reflog-lpx-attiny88-audio-02561c5a` | local, origin | Latest recorded work: Record LPX SRAM tradeoffs and the selected 512-byte profile |
| `codex/cleanup-reflog-lpx-attiny88-audio-89d67a33` | local, origin | Latest recorded work: Record LPX SRAM tradeoffs and the selected 512-byte profile |
| `codex/cleanup-reflog-lpx-nano-combined-ee67c2a55afd` | local | Latest recorded work: Add normalized Nano LPX dialogue with timed pauses |
| `codex/cleanup-reflog-lpx-speech-4-6-8-263c15c59eed` | local | Latest recorded work: test(lpx): record smaller program Flash builds and IRQ validation |
| `codex/cleanup-reflog-lpx-speech-4-6-8-8ca865aa7c06` | local | Latest recorded work: feat(lpx): add explicit compact-only Flash size profile |
| `codex/cleanup-reflog-lpx-speech-4-6-8-bd4680aa2f1f` | local | Latest recorded work: docs(lpx): plan program Flash size optimization |
| `codex/cleanup-reflog-lpx-v5-encoder-quality-9460195b` | local, origin | Latest recorded work: Record v5 encoder baseline and implementation progress |
| `codex/cleanup-reflog-lpx-v5-grid-cosine-a58f4592c8f4` | local | Latest recorded work: Select admitted256-slot v5 player FIFO |
| `codex/cleanup-reflog-lpx-v5-grid-cosine-fd84279e5b89` | local | Latest recorded work: Add bounded whole-reference non-speech trajectory study |
| `codex/cleanup-reflog-lpx-v5-rollback-integration-a09eaa7f` | local, origin | Latest recorded work: Record rollback gain and current packing validation plan |
| `codex/cleanup-reflog-lpx-v5-spi-player-56e49cefcd63` | local | Latest recorded work: Add reusable ATmega328P SPI Flash reader |
| `codex/cleanup-reflog-micromusic-youtube-6fc4c10dc648` | local | Latest recorded work: Add timed English subtitles to MicroMusic preview |
| `codex/cleanup-reflog-speex-noise-shifts-efd89659` | local, origin | Latest recorded work: Admit exact noise shifts with active IRQ and SPI output |
| `codex/clki-design` | local, origin | Latest recorded work: Document timestamped CLKI and resumable CPU contract |
| `codex/clki-input` | local, origin | Latest recorded work: Add exact fixed-frequency switched clock mapper |
| `codex/codec-corpus-quality` | local, origin | Latest recorded work: Merge LPX quiet-speech fixes with verified encoder acceleration |
| `codex/common-avr` | local, origin | Latest recorded work: Preserve AVR profile and instruction observation verification recipe |
| `codex/cpu-phase-runtime` | local, origin | Latest recorded work: Advance sleep wake counters in constant-time clock batches |
| `codex/engine-selector` | local, origin | Latest recorded work: Use WASM playback engine by default |
| `codex/firmware-native-volume` | local, origin | Latest recorded work: Maximize speech firmware output with bounded fractional gain |
| `codex/github-markdown-links` | local, origin | Latest recorded work: Open site Markdown documents on GitHub |
| `codex/home-player-card` | local, origin | Latest recorded work: Restore music player card and align action buttons |
| `codex/hq4-auto-encoder` | local, origin | Latest recorded work: Expose automatic speech profiles in the web player |
| `codex/hq4-public-site` | local, origin | Latest recorded work: Refresh cached player entry point for public HQ4 |
| `codex/hq4-quality` | local, origin | Latest recorded work: Add HQ4-T playback with matched comparison levels |
| `codex/i8080-music-pwm` | local, origin | Latest recorded work: Raise FluidR3 music PWM and sample rate with uniform 99T slots |
| `codex/import-codec2-history` | local, origin | Latest recorded work: Profile inlined stages of the unchanged Codec2 AVR decoder |
| `codex/import-lpx` | local, origin | Latest recorded work: Retain LPX byte-product multiplication recipe |
| `codex/import-sound-codecs` | local, origin | Latest recorded work: Clarify published source import contents |
| `codex/lpx-1500` | local | Latest recorded work: Reduce exact universal LPX decoder work on AVR25 |
| `codex/lpx-accuracy-levels` | local | Latest recorded work: Account for first correction flags within LPX precision budgets |
| `codex/lpx-adaptive-order` | local | Adaptive LPC order, coefficient precision and compact storage experiments with AVR constraints. |
| `codex/lpx-analysis-cache` | local | Latest recorded work: Measure LPX analysis and backend options and refresh web assets |
| `codex/lpx-attiny88-audio` | local, origin | Latest recorded work: Archive the measured optional S15 target parser and replay tools |
| `codex/lpx-auto-sample-rate` | local, origin | Latest recorded work: Rebuild WebUI LPX images with compact three-rate player |
| `codex/lpx-avr-deadline` | local, origin | Latest recorded work: Retain exact LPX Q12 dot and history fusion technique |
| `codex/lpx-bfp-trajectories` | local | Experimental shared-exponent groups and logarithmic trajectories; compare size, quality and full AVR cost. |
| `codex/lpx-compact-format` | local | Latest recorded work: Add smaller lossless LPX v9 playback for Tiny88 |
| `codex/lpx-cuda-encoder` | local | Latest recorded work: Record CUDA corpus speedups and exact output validation |
| `codex/lpx-decoder-refactor` | local, origin | Latest recorded work: Reduce LPX Flash with shared readers and LPC conversion |
| `codex/lpx-encoder-unification` | local | Latest recorded work: Refresh LPX browser asset versions for the unified encoder |
| `codex/lpx-exact-search` | local | Latest recorded work: Record exact LPX speedups and refresh web encoder assets |
| `codex/lpx-fidelity-improvements` | local | Latest recorded work: Record delayed-search results and preserve AVR scope for the bitrate target |
| `codex/lpx-fixed-rate` | local | Latest recorded work: Rebuild WebUI LPX firmware for fixed 8 kHz playback |
| `codex/lpx-global-rate` | local, origin | Latest recorded work: Retain LPX entropy cost and Q12 refinement lessons |
| `codex/lpx-headroom-quality` | local, origin | Latest recorded work: Retain LPX static anchor caching and compact loop measurements |
| `codex/lpx-local-noise` | local | Experimental source-frozen excitation noise ranking; paired PCM/PWM comparison found no admitted gain. |
| `codex/lpx-lossless-compression` | local, origin | Latest recorded work: Record LPX compression tradeoffs and complete five-step validation |
| `codex/lpx-lowrate-avr25` | local, origin | Latest recorded work: Refresh Nano LPX release provenance after codec integration |
| `codex/lpx-lowrate-decode-budget` | local, origin | Latest recorded work: Preserve bounded LPX decoder trials and rejection evidence |
| `codex/lpx-lowrate-quality` | local, origin | Latest recorded work: Audit completed LPX speed loop and selectable AVR backends |
| `codex/lpx-lowrate-quality-final` | local, origin | Latest recorded work: Clarify LPX decoder tradeoffs and isolated reproduction branches |
| `codex/lpx-lowrate-quality-next` | local | Latest recorded work: Record guarded LPX quality corpus and firmware validation |
| `codex/lpx-lowrate-v9` | local, origin | Latest recorded work: Use bounded hardware products for AVR5 LSF conversion |
| `codex/lpx-lp20-study` | local | Reconstruct LP20 and LPX-Z80 version history from original chat archives; assess quality improvements transferable to current LPX. |
| `codex/lpx-lsf-groups` | local | LSF grouping and packing study, AVR tuning checks, and initial Z80 transfer review. |
| `codex/lpx-m4a-streaming` | local | Latest recorded work: Encode long recordings through continuous bounded search windows |
| `codex/lpx-main-merge` | local, origin | Latest recorded work: Merge verified LPX speech profiles and compact packing |
| `codex/lpx-main-release-nov17` | local | Latest recorded work: Merge optimized LPX v9 firmware into WebUI release |
| `codex/lpx-main-successful` | local, origin | Latest recorded work: Document validated LPX main integration and historical tool scope |
| `codex/lpx-mega-webui-v9` | local | Latest recorded work: Use universal LPX v9 in Nano speech and dialogue firmware |
| `codex/lpx-nano-3k` | local | Latest recorded work: Rebuild WebUI LPX images with compact three-rate player |
| `codex/lpx-nano-combined` | local, origin | Latest recorded work: Add Nano dialogue to the shared speech firmware catalog |
| `codex/lpx-nomul` | local, origin | Latest recorded work: Support real-time LPX playback on AVR25 without MUL |
| `codex/lpx-pcm-quality` | local | Selectable PCM or PWM encoder quality target, with unchanged LPX format and decoder. |
| `codex/lpx-period-excitation` | local, origin | Latest recorded work: Evaluate LPX size growth against quality gains |
| `codex/lpx-prefix-search` | local | Latest recorded work: Record LPX prefix speedups and refresh web assets |
| `codex/lpx-profile-development` | local, origin | Latest recorded work: Record selected LPX profiles, exact encoder speed and full AVR admission |
| `codex/lpx-quality-all-modes` | local | Latest recorded work: Run LPX quality regressions on repository changes |
| `codex/lpx-russian-voice` | local, origin | Latest recorded work: Record quiet-speech quality, AVR admission and rejected levels |
| `codex/lpx-shared-encoder` | local | Latest recorded work: Enable shared adaptive quality encoding in the LPX Web UI |
| `codex/lpx-simd-search` | local | Latest recorded work: Record exact pulse SIMD speedups and backend guarantees |
| `codex/lpx-speech-4-6-8` | local, origin | Latest recorded work: test(lpx): record full shared-corpus quality and AVR admission |
| `codex/lpx-sram512-profile` | local, origin | Latest recorded work: Merge current main into the separate SRAM512 profile branch |
| `codex/lpx-standard-comparison` | local, origin | Latest recorded work: Scope LPX compact AVR support to measured workloads |
| `codex/lpx-streaming-encoder` | local | Latest recorded work: Encode long recordings through continuous bounded search windows |
| `codex/lpx-timbre` | local | Latest recorded work: Update LPX Web UI for wider-band continuous encoding |
| `codex/lpx-tiny88-12k` | local, origin | Latest recorded work: Accelerate Tiny88 Q14 filtering and record wideband IRQ results |
| `codex/lpx-tiny88-size` | local, origin | Latest recorded work: Trim the bounded AVR25 converter cosine table |
| `codex/lpx-tiny88-sram` | local, origin | Latest recorded work: Expose Tiny88 HEX downloads and synchronized controller URLs |
| `codex/lpx-tiny88-webui-v9` | local | Latest recorded work: Rebuild Tiny88 WebUI with the smaller universal LPX v9 core |
| `codex/lpx-universal-size` | local | Latest recorded work: Rebuild LPX speech firmware with compact state reset |
| `codex/lpx-universal-tiny88` | local | Latest recorded work: Add universal runtime-header LPX playback for Tiny88 |
| `codex/lpx-v5-anchor-study` | local, origin | Latest recorded work: Record frozen anchor ordering outcomes and limits |
| `codex/lpx-v5-causal-pulse-probe` | local, origin | Latest recorded work: Record synthetic same-byte causal cancellation counterexample |
| `codex/lpx-v5-chain-rate` | local, origin | Latest recorded work: Allocate exact whole-chain SSE and bytes over fixed reset pools |
| `codex/lpx-v5-chain-study` | local, origin | Latest recorded work: Record exact fixed-pool allocation results and prior-union limits |
| `codex/lpx-v5-combined-study` | local, origin | Latest recorded work: Record full combined v5 corpus study and player admission |
| `codex/lpx-v5-compact-state` | local, origin | Latest recorded work: Share compact speech profile and extra pulse flags |
| `codex/lpx-v5-decode-simplify` | local, origin | Latest recorded work: Record integrated decoder simplification results |
| `codex/lpx-v5-development` | local, origin | Latest recorded work: Record v5-only corpus and firmware measurements |
| `codex/lpx-v5-encoder-integration` | local, origin | Latest recorded work: Save paused scale repeat player pilot evidence |
| `codex/lpx-v5-encoder-paths` | local, origin | Latest recorded work: Admit evaluation and additional pools on AVR player |
| `codex/lpx-v5-encoder-quality` | local, origin | Latest recorded work: Admit encoder candidates on complete AVR release player |
| `codex/lpx-v5-exact-cleanup` | local, origin | Latest recorded work: Save paused exact-cleanup research checkpoint |
| `codex/lpx-v5-external-spi` | local, origin | Latest recorded work: Record completed search comparison and external SPI plan |
| `codex/lpx-v5-extra-integration` | local, origin | Latest recorded work: Record extra-pass result and plan whole-chain rollback search |
| `codex/lpx-v5-extra-refit` | local, origin | Latest recorded work: Refine existing P4 extras across complete recordings with checkpoints |
| `codex/lpx-v5-extra-refit-study` | local, origin | Latest recorded work: Record negative full-coverage extra-pass corpus result |
| `codex/lpx-v5-extra-rollback` | local, origin | Latest recorded work: Restore protected extra blocks without refunding search progress |
| `codex/lpx-v5-extra-rollback-study` | local, origin | Latest recorded work: Record same-size conditional gain from whole-chain rollback |
| `codex/lpx-v5-fold-poly` | local, origin | Latest recorded work: Record bounded pulse insertion size tradeoffs |
| `codex/lpx-v5-grid-cosine` | local, origin | Latest recorded work: Skip redundant v5 second-half spectrum copies |
| `codex/lpx-v5-joint-budget` | local, origin | Latest recorded work: Record joint search and full firmware budget results |
| `codex/lpx-v5-joint-rate` | local, origin | Latest recorded work: Propose separate same-seed useful anchor ordering pilot |
| `codex/lpx-v5-marginal-bits` | local, origin | Latest recorded work: Record complete adaptive selection player admission |
| `codex/lpx-v5-measurement-runtime` | local, origin | Latest recorded work: Record complete host timing and paired v5 evidence |
| `codex/lpx-v5-next-plan` | local, origin | Latest recorded work: Plan next v5 optimizations and characterize tail boundaries |
| `codex/lpx-v5-nonspeech-robustness` | local, origin | Latest recorded work: Record all non-speech new-encoder robustness checks |
| `codex/lpx-v5-perceptual-objective` | local, origin | Latest recorded work: Admit held-out v5 Pareto point on complete player |
| `codex/lpx-v5-plan-execution` | local, origin | Latest recorded work: Complete the v5 source optimization plan and record final admission |
| `codex/lpx-v5-quiet-search` | local, origin | Latest recorded work: Record audited adaptive corpus and paired effort outcomes |
| `codex/lpx-v5-quiet-voice` | local, origin | Latest recorded work: Record strong targeted listening preference and quiet level choice |
| `codex/lpx-v5-rate-frontier` | local, origin | Latest recorded work: Add bounded cross-rate v5 extra allocation frontier |
| `codex/lpx-v5-rate-priority` | local, origin | Latest recorded work: Record exact allocation limit and full-record excitation follow-up |
| `codex/lpx-v5-rate-study` | local, origin | Latest recorded work: Propose separate same-seed useful anchor ordering pilot |
| `codex/lpx-v5-release-player` | local, origin | Latest recorded work: Select admitted 256-slot v5 player FIFO |
| `codex/lpx-v5-retention-corpus` | local, origin | Latest recorded work: Record full-corpus canonical retention regression |
| `codex/lpx-v5-retention-player` | local, origin | Latest recorded work: Record canonical retention player admission |
| `codex/lpx-v5-rollback-integration` | local, origin | Latest recorded work: Record rollback gain and current packing validation plan |
| `codex/lpx-v5-rollback-player` | local, origin | Latest recorded work: Prepare fixed current-source rollback ROM validation |
| `codex/lpx-v5-search-cpu` | local, origin | Latest recorded work: Bound trajectory search with a cooperative CPU quota |
| `codex/lpx-v5-search-cpu-lpc` | local, origin | Latest recorded work: Bound host LPC search with an optional CPU quota |
| `codex/lpx-v5-search-cpu-player` | local, origin | Latest recorded work: Record complete matched-search ROM player results |
| `codex/lpx-v5-search-cpu-protocol` | local, origin | Latest recorded work: Record matched-data CPU corpus comparison and costs |
| `codex/lpx-v5-small-kernels` | local, origin | Latest recorded work: Record final decoder host and sanitizer admission |
| `codex/lpx-v5-spi-cases` | local, origin | Latest recorded work: Verify persisted SPI images and full reference outputs |
| `codex/lpx-v5-spi-model` | local, origin | Latest recorded work: Add portable read-only W25Q128 SPI protocol model |
| `codex/lpx-v5-spi-player` | local, origin | Latest recorded work: Record full-length external SPI player validation |
| `codex/lpx-v5-voice-adaptive` | local, origin | Latest recorded work: Link verified retention and firmware evidence |
| `codex/lpx-v5-voice-analysis` | local, origin | Latest recorded work: Record targeted whole-prefix retention evidence |
| `codex/lpx-v5-voice-retention` | local, origin | Latest recorded work: Record verified whole-chain retention in quality plan |
| `codex/lpx-v6-repeat-current-scan` | local, origin | Latest recorded work: Record current baseline scale-repeat serialized costs |
| `codex/lpx-v9-bitrate-profiles` | local, origin | Latest recorded work: Add shared LPX v9 bitrate presets at 3 and 8 kbps |
| `codex/lpx-v9-next` | local | Latest recorded work: Shrink LPX v9 state and synchronize the portable C reference |
| `codex/lpx-v9-profiles-mainmerge` | local | Latest recorded work: Merge unified LPX v9 bitrate profiles with CUDA native support |
| `codex/lpx-v9-quality-all` | local | Latest recorded work: Record full-band LPX corpus results and scoped firmware validation |
| `codex/lpx-v9-web-player` | local | Latest recorded work: Link the LPX tools and MicroMusic homepage in both directions |
| `codex/lpx-wav-encoder` | local, origin | Latest recorded work: Retain Q0 stability and full-firmware profiling techniques |
| `codex/lpx-web-normalization` | local | Latest recorded work: Normalize input PCM without extending the LPX format |
| `codex/lpx-webgpu` | local | Latest recorded work: Add experimental exact WebGPU LPX search |
| `codex/lpx-webgpu-batch` | local | Latest recorded work: Batch exact LPX WebGPU searches across sequential blocks |
| `codex/lpx-webgpu-notes` | local | Latest recorded work: Document retained LPX WebGPU experiment and SIMD comparison |
| `codex/lpx-webui-rebuild` | local, origin | Latest recorded work: Separate portable C and AVR assembly multiplication backends |
| `codex/lpx-webui-release` | local | Latest recorded work: Validate historical WebUI firmware against its build revisions |
| `codex/lumiere-stereo` | local, origin | Latest recorded work: Open the music homepage in stereo by default |
| `codex/merge-speech-quality` | local, origin | Latest recorded work: Measure lossless Q5 stream packing against the AVR budget |
| `codex/micromusic-youtube` | local, origin | Latest recorded work: Move video production materials to the YouTube archive |
| `codex/micronucleus-emulator` | local, origin | Latest recorded work: Fix AVR bit I/O semantics across emulator backends |
| `codex/mobile-original-audio` | local, origin | Latest recorded work: Use mobile-compatible PCM for original speech playback |
| `codex/music-engine-upgrade` | local, origin | Latest recorded work: Integrate upgraded music firmware into the emulator catalog |
| `codex/music-format-guide` | local, origin | Latest recorded work: Document music storage and playback with illustrated examples |
| `codex/publish-speech-q5` | local, origin | Latest recorded work: Move improved Q5 speech into the version catalog |
| `codex/reset-input-profile` | local, origin | Latest recorded work: Update supply and reset sources atomically |
| `codex/site-home` | local, origin | Latest recorded work: Add shared player homepage and Rudolff project card |
| `codex/sound-hq4-emulator` | local, origin | Latest recorded work: Play verified HQ4 speech with shared JS and WASM engines |
| `codex/speech-bread-profiles` | local | Latest recorded work: Add Speex firmware profiles for the fourth Nano phrase |
| `codex/speech-catalog-trim` | local, origin | Latest recorded work: Keep one balanced HQ4 image per speech phrase |
| `codex/speech-output-range` | local | Latest recorded work: Calibrate LPX and Speex firmware output amplitude |
| `codex/speech-page-lpx-only` | local, origin | Latest recorded work: Round speech-page bitrates to whole kbit values |
| `codex/speech-quality` | local, origin | Latest recorded work: Retain head-Q5 comparison and full speech qualification |
| `codex/speech-release-main` | local, origin | Latest recorded work: Compare original speech and replay completed firmware safely |
| `codex/speech-volume-display` | local | Latest recorded work: Keep speech waveforms independent of listening volume |
| `codex/speex-attiny88` | local, origin | Latest recorded work: Record the isolated Speex ATtiny88 optimization plan |
| `codex/speex-avr` | local, origin | Latest recorded work: Retain fused wideband decoder and PWM admission results |
| `codex/speex-avr-size` | local, origin | Latest recorded work: Admit second Speex Flash cycle with full WB IRQ audit |
| `codex/speex-fold-noise-table` | local, origin | Latest recorded work: Fold the finite noise alphabet before expanding samples |
| `codex/speex-forced-q6` | local, origin | Latest recorded work: Admit bounded forced-pitch math in decoding and playback |
| `codex/speex-forced-zero` | local, origin | Latest recorded work: Record exact zero-prediction timing and output admission |
| `codex/speex-low-rates` | local, origin | Latest recorded work: Play Speex streams from shared SPI Flash with exact PWM admission |
| `codex/speex-lowband-fusion` | local, origin | Latest recorded work: Record low-rate WB fusion timing and output admission |
| `codex/speex-nano-dialogue` | local | Latest recorded work: Add fitting Speex choices for the Nano dialogue |
| `codex/speex-nano-examples` | local, origin | Latest recorded work: Add Speex profiles to the shared Nano speech player |
| `codex/speex-nb-speed` | local, origin | Latest recorded work: Merge current main before grouped Speex IIR integration |
| `codex/speex-nb1-coefficient` | local, origin | Latest recorded work: Record finite NB1 gain timing and loaded playback admission |
| `codex/speex-nb1-prepared-dispatch` | local, origin | Latest recorded work: Record prepared-dispatch ABI and playback admission |
| `codex/speex-nb1-zero-gain` | local, origin | Latest recorded work: Admit exact NB1 zero-gain preparation and playback |
| `codex/speex-nb1-zero-synthesis` | local, origin | Latest recorded work: Admit zero-context synthesis timing and continuous playback |
| `codex/speex-noise-q15` | local, origin | Latest recorded work: Record invariant noise quantization admission and rejected compression |
| `codex/speex-noise-shifts` | local, origin | Latest recorded work: Merge complete WB divider validation |
| `codex/speex-one-tap` | local, origin | Latest recorded work: Record one-tap decoder timing and continuous output evidence |
| `codex/speex-vocoder-mean` | local, origin | Latest recorded work: Admit exact mean with full corpus and active output checks |
| `codex/speex-wb-gain-div` | local, origin | Latest recorded work: Admit bounded division across all five WB profiles |
| `codex/speex-wb-noise-reuse` | local, origin | Latest recorded work: Admit shared noise cache with full IRQ and SPI playback evidence |
| `codex/speex-wb-noise-speed` | local, origin | Latest recorded work: Admit exact RNG speedup with full PCM and active output evidence |
| `codex/speex-wb-refill` | local, origin | Latest recorded work: Record exact NB1 refill timing and output admission |
| `codex/speex-wb-speed` | local, origin | Latest recorded work: Assess wideband filter quality budget and profile reuse |
| `codex/speex-wb-speed-next` | local | Latest recorded work: Measure exact split QMF accumulators and pointer spill tradeoffs |
| `codex/timer0-uncertainty` | local, origin | Latest recorded work: Guard Timer0 pulses when PWM TOP is zero |
| `codex/tiny88-bread-profiles` | local | Latest recorded work: Unify Tiny88 speech choices without experimental S15 |
| `codex/um88-algorithm-review` | local, origin | Latest recorded work: Record full UM88 cycle profile and lossless optimization review |
| `codex/um88-core-size` | local, origin | Latest recorded work: Rebuild UM88 releases with lower PWM interrupt overhead |
| `codex/um88-eight-voices` | local, origin | Latest recorded work: Merge branch 'main' into codex/um88-eight-voices |
| `codex/um88-main-merge` | local, origin | Latest recorded work: Merge optimized UM88 playback and PWM interrupt releases |
| `codex/um88-main-publish` | local, origin | Latest recorded work: Merge optimized UM88 playback and PWM interrupt releases |
| `codex/universal-pipeline` | local, origin | Latest recorded work: Refresh unchanged board images after runtime provenance updates |
| `codex/wasm-phase-compiler` | local, origin | Latest recorded work: Document connected CLKI phases and package v5 |
| `docs/micronucleus-size-recipes` | local, origin | Latest recorded work: Document descriptor replies and merged AVR startup loop |
