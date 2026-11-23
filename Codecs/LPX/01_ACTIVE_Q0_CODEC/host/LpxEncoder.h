#pragma once
#include <stdint.h>

// One encoder instance per process/WASM instance. Call reserve before writing
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
#ifdef __cplusplus
}
#endif
