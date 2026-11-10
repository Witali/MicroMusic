/* MicroMusic: host-only LPC batch decoding entry point.
   This translation unit is NEVER included in the ATmega328P firmware.
   The decoding algorithm is the same portable Lpx4HybridCore as in firmware.
   Build: g++ -O3 -fPIC -shared -std=c++11 -Isrc
          src/Lpx4HybridCore.cpp src/native_batch_decoder.cpp -o liblpx4batch.so
*/
#include "Lpx4HybridCore.h"
#include <stdint.h>

extern "C" uint32_t lpx4_batch_compact_version(){return LPX4_COMPACT_VERSION;}
// Numeric mode is independent of the serialized compact format.
extern "C" uint32_t lpx4_batch_numeric_mode(){return LPX4_FLOAT_SYNTHESIS;}

extern "C" int lpx4_batch_decode(
  const uint8_t* concatenated,
  const uint32_t* offsets,
  const uint32_t* sizes,
  uint32_t count,
  uint8_t* pcm,
  uint32_t pcm_stride,
  uint32_t expected_samples,
  int32_t* statuses) {
  if (!concatenated || !offsets || !sizes || !pcm || !statuses ||
      count > 512 || pcm_stride < expected_samples || expected_samples > 1000000)
    return -1;
  for (uint32_t i = 0; i < count; ++i) {
    statuses[i] = 0;
    if (sizes[i] < (LPX4_COMPACT_VERSION==9?13u:20u) || sizes[i] > 65535) { statuses[i] = -2; continue; }
    Lpx4HybridCore core;
    if (!core.begin(concatenated + offsets[i], (uint16_t)sizes[i]) ||
        core.samples() != expected_samples) { statuses[i] = -3; continue; }
    uint32_t pos = 0;
    uint8_t s;
    while (pos < expected_samples && core.next(s)) {
      pcm[i*pcm_stride+pos] = s;
      ++pos;
    }
    // Drain once more so v9 validates EOF even at a partial sample tail.
    if (pos != expected_samples || core.next(s) || core.error() || !core.finished()) statuses[i] = -4;
  }
  return 0;
}

// Host-only signed 16-bit output. No PWM gain / 8-bit rounding.
// This ABI uses samples (not bytes) for stride and count, and remains separate
// from lpx4_batch_decode, preserving the previous 8-bit batch API.
extern "C" int lpx4_batch_decode_s16(
  const uint8_t* concatenated,
  const uint32_t* offsets,
  const uint32_t* sizes,
  uint32_t count,
  int16_t* pcm,
  uint32_t pcm_stride,
  uint32_t expected_samples,
  int32_t* statuses) {
  if (!concatenated || !offsets || !sizes || !pcm || !statuses ||
      count > 512 || pcm_stride < expected_samples || expected_samples > 1000000)
    return -1;
  for (uint32_t i=0; i<count; ++i) {
    statuses[i]=0;
    if (sizes[i]<(LPX4_COMPACT_VERSION==9?13u:20u) || sizes[i]>65535) {statuses[i]=-2; continue;}
    Lpx4HybridCore core;
    if(!core.begin(concatenated+offsets[i],(uint16_t)sizes[i]) ||
       core.samples()!=expected_samples){statuses[i]=-3;continue;}
    uint32_t p=0;
    int16_t s=0;
    while(p<expected_samples && core.nextS16(s)){
       pcm[i*pcm_stride+p]=s;
       ++p;
    }
    if(p!=expected_samples || core.nextS16(s) || core.error() || !core.finished())statuses[i]=-4;
  }
  return 0;
}

// Direct normalized binary64 output. No PCM16/PWM adapter or intermediate
// quantization is called. Stride and count are in double samples, not bytes.
extern "C" int lpx4_batch_decode_f64(
  const uint8_t* concatenated,
  const uint32_t* offsets,
  const uint32_t* sizes,
  uint32_t count,
  double* pcm,
  uint32_t pcm_stride,
  uint32_t expected_samples,
  int32_t* statuses) {
#if !LPX4_FLOAT_SYNTHESIS
  return -5; // Fixed synthesis cannot supply unquantized floating samples.
#else
  if (!concatenated || !offsets || !sizes || !pcm || !statuses ||
      count > 512 || pcm_stride < expected_samples || expected_samples > 1000000)
    return -1;
  for (uint32_t i=0; i<count; ++i) {
    statuses[i]=0;
    if (sizes[i]<(LPX4_COMPACT_VERSION==9?13u:20u) || sizes[i]>65535) {statuses[i]=-2; continue;}
    Lpx4HybridCore core;
    if(!core.begin(concatenated+offsets[i],(uint16_t)sizes[i]) ||
       core.samples()!=expected_samples){statuses[i]=-3;continue;}
    uint32_t p=0;
    double s=0;
    while(p<expected_samples && core.nextFloat(s)){
      pcm[i*pcm_stride+p]=s;
      ++p;
    }
    if(p!=expected_samples || core.nextFloat(s) || core.error() || !core.finished())statuses[i]=-4;
  }
  return 0;
#endif
}
