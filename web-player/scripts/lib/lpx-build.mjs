// Shared codec composition and numeric contract. Platform-specific ABI, linker,
// ISA flags and API exports stay in their respective native/WASM build helpers.
const base='Codecs/LPX/01_ACTIVE_Q0_CODEC';
const host=names=>names.map(name=>`${base}/host/${name}`);
export const buildConfigPath='web-player/scripts/lib/lpx-build.mjs';
export const coreSource=`${base}/src/Lpx4HybridCore.cpp`;
export const seedSources=[coreSource,...host(['LpxEncoder.cpp'])];
export const wasmRuntimeSources=host(['LpxWasmMemory.cpp']);
export const hostSources=host([
  'LpxAdaptiveDsp.cpp','LpxAccuracy.cpp','LpxPacking.cpp','LpxStreaming.cpp',
  'LpxQuality.cpp','LpxStoi.cpp','LpxCandidateEvaluation.cpp','LpxRefinement.cpp',
  'LpxAdaptiveController.cpp','LpxLoudness.cpp','LpxBitrateProfiles.cpp',
  'LpxProfileQuality.cpp','LpxPulseLookahead.cpp','LpxFullBand.cpp',
  'LpxSpectralPulses.cpp','LpxLpcRefine.cpp','LpxPitchGuard.cpp'
]);
export const nativeEntry=host(['encode_lpx.cpp'])[0];
export const wasmApiSources=host(['LpxAdaptiveApi.cpp','LpxStreamingApi.cpp']);
export const coreInputs=['Lpx4HybridCore.h','Lpx4Math.h','Lpx4MemoryProfiles.h',
  'Lpx4MultiplyC.h','cos_table.inc','scale_table.inc'].map(name=>`${base}/src/${name}`);
export const workspaceHeader=`${base}/host/LpxHostWorkspace.h`;
export const seedInputs=host(['LpxEncoder.h','LpxEncoderContext.h','LpxEncoderOptions.h',
  'LpxEncoderSimd.h','LpxSeed.h','LpxSpectrumQuantizer.h','LpxLpcStability.h']);
export const hostInputs=host([
  'LpxAdaptive.h','LpxAccuracy.h','LpxEncodingPolicy.h','LpxCandidateEvaluation.h',
  'LpxPacking.h','LpxStreaming.h','LpxQuality.h','LpxRefinement.h','LpxAdaptiveController.h',
  'LpxLoudness.h','LpxBitrateProfiles.h','LpxProfileQuality.h','LpxPulseLookahead.h',
  'LpxFullBand.h','LpxSpectralPulses.h','LpxLpcRefine.h','LpxPitchGuard.h',
  'stoi-resample.inc','stoi-resample-12k.inc','stoi-resample-16k.inc',
  'quality-resample-12k.inc','quality-resample-16k.inc','LICENSE-pystoi.txt','LICENSE-libebur128.txt'
]);
export const portableDefines=['LPX4_ENABLE_ASM=0','LPX4_FLOAT_SYNTHESIS=0','LPX4_ENABLE_SPEECH=1',
  'LPX4_ENABLE_SPEECH_COMPACT=1','LPX4_COMPACT_ONLY=1','LPX4_COMPACT_VERSION=9',
  'LPX4_SAMPLE_RATE=0','LPX4_EXTENDED_SAMPLE_RATES=1','LPX4_ENABLE_WIDE_V9=1'];
export const includes=[`${base}/src`,`${base}/host`];
export const floatingPoint=Object.freeze({clang:'-ffp-contract=off',msvc:'/fp:strict',cuda:'--fmad=false'});
