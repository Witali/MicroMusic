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
#ifdef __cplusplus
}
#endif
