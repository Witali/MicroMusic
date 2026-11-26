#pragma once
#include <stdint.h>

// Compatibility adapter for the default seed context. C++ host callers may
// own independent SeedEncoder contexts (LpxEncoderContext.h). Call reserve before writing
// PCM16 to input; begin then consumes the copied input. Each step encodes one
// 160-sample block. Finish verifies every output sample with Lpx4HybridCore.
// Output remains valid until the next reserve/begin. No files or host callbacks.
#ifdef __cplusplus
extern "C" {
#endif
int enc_reserve(uint32_t samples);
int16_t* enc_input(void);
uint8_t* enc_output(void);
int enc_begin(int samples, int profile, int sampleRate);
int enc_step(void);
int enc_finish(void);
// Explicit native arithmetic backend: 0 portable CPU (default), 1 CUDA.
// Returns 0 on success, a negative value if unsupported/unavailable.
int enc_set_backend(int backend);
const char* enc_backend_error(void);
// Complete-file 3/8 kbit/s presets, currently calibrated for 8000 Hz.
// Read bytes with enc_adaptive_output(); -6 means bounded search found no fit.
int enc_bitrate(int samples, int kbps, int sampleRate, int autoQuiet, int calls);
// Explicit quality policy: PCM computer/I2S/DAC=0, AVR PWM=1. Existing APIs use PWM.
// Invalid qualityTarget values return -1; policy is captured by each encode/session.
enum LpxQualityTarget { LPX_QUALITY_PCM=0, LPX_QUALITY_PWM=1 };
int enc_accuracy_target(int samples,int level,int rate,int calls,int normalize,int target,int maximum,int qualityTarget);
int enc_adaptive_target(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,int qualityTarget);
int enc_adaptive_extended_target(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,int allowancePercent,int qualityTarget);
int enc_adaptive_loudness_target(int samples,int profile,int rate,int maxBytes,int calls,int allowancePercent,int expanded,int qualityTarget);
int enc_adaptive_level_target(int samples,int profile,int rate,int maxBytes,int calls,int allowancePercent,int expanded,int targetLufs,int maxGainDb,int qualityTarget);
int enc_bitrate_target(int samples,int kbps,int rate,int autoQuiet,int calls,int qualityTarget);
int enc_bitrate_loudness_target(int samples,int kbps,int rate,int calls,int qualityTarget);
int enc_bitrate_level_target(int samples,int kbps,int rate,int calls,int targetLufs,int maxGainDb,int qualityTarget);
int enc_stream_create_target(int samples,int profile,int rate,int allowance,int calls,int normalize,int target,int maximum,int qualityTarget);
int enc_stream_create_accuracy_target(int samples,int profile,int rate,int allowance,int calls,int normalize,int target,int maximum,int qualityTarget);
#ifdef __cplusplus
}
#endif
